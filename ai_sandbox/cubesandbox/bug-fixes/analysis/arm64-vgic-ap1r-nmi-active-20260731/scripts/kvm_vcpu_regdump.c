// kvm_vcpu_regdump.c — 读取另一进程中 KVM vCPU 的关键 ARM64 系统寄存器
//
// 用法: kvm_vcpu_regdump <vmm_pid> [vcpu_fd ...]
//       不带 fd 参数时枚举目标进程全部 anon_inode:kvm-vcpu fd;
//       带 fd 参数时只 dump 指定 fd(可用 /proc/<pid>/fd 里的编号,
//       例如 vcpu 被深阻塞时可跳过它只读另一个 vcpu)。
//
// 两条路径:
//   A) pidfd_open + pidfd_getfd 复制 anon_inode:kvm-vcpu fd,直接 KVM_GET_ONE_REG。
//      —— 仅当本进程与 VMM 同 mm(或 KVM 放开跨进程限制)时可行;
//         跨进程时内核 kvm_vcpu_ioctl 检查 vcpu->kvm->mm != current->mm 返回 -EIO。
//   B) ptrace 注入(实际生效): PTRACE_ATTACH 目标进程一个空闲(S 态)线程,
//      在其 PC 处临时写入 mov x8,#__NR_ioctl; svc #0; brk #0 小桩,在目标进程
//      上下文里执行 ioctl(vcpu_fd, KVM_GET_ONE_REG, &one),再恢复指令与寄存器。
//      attach 期间仅该线程停顿微秒级,其余线程(含 vCPU 线程)不受影响。
//
// 重要限制(KVM 设计): 任何 vcpu ioctl 都要先拿 vcpu->mutex,而该锁在 vcpu 处于
// KVM_RUN 期间一直被其 vCPU 线程持有(包括在 kvm_vcpu_block 里睡死时)。若目标
// vcpu 长时间不退出 KVM_RUN(如深睡无未决中断,或内核态忙转),注入的
// KVM_GET_ONE_REG 会跟着阻塞(D 态),直到该 vcpu 下次回到用户态。本工具对此
// 只警告不中止 —— 中途强退会让目标线程带着残留 stub/脏寄存器恢复执行,有搞崩
// VMM 的风险。要绕开被堵的 vcpu,请用 fd 参数只 dump 其他 vcpu。
//
// 注意: 对运行中的 vCPU,KVM_GET_ONE_REG 返回 VMM 侧缓存值(最近 exit 同步),
// 对判断 guest IRQ 接收路径状态足够,无需 pause VM。
// 单个寄存器读取失败只报告 errno,不中止。

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <unistd.h>
#include <signal.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/ptrace.h>
#include <sys/uio.h>
#include <sys/wait.h>
#include <linux/kvm.h>
#include <asm/kvm.h>

#ifndef __NR_pidfd_open
#define __NR_pidfd_open 434
#endif
#ifndef __NR_pidfd_getfd
#define __NR_pidfd_getfd 438
#endif
#ifndef NT_PRSTATUS
#define NT_PRSTATUS 1
#endif
#ifndef __NR_ioctl
#define __NR_ioctl 29
#endif

// aarch64 用户态寄存器(等价于 <asm/ptrace.h> 的 struct user_pt_regs)
struct user_regs {
    uint64_t x[31];
    uint64_t sp;
    uint64_t pc;
    uint64_t pstate;
};

static int sys_pidfd_open(pid_t pid, unsigned int flags)
{
    return (int)syscall(__NR_pidfd_open, pid, flags);
}

static int sys_pidfd_getfd(int pidfd, int targetfd, unsigned int flags)
{
    return (int)syscall(__NR_pidfd_getfd, pidfd, targetfd, flags);
}

#define SYSREG_ID(op0, op1, crn, crm, op2) \
    (KVM_REG_ARM64 | KVM_REG_SIZE_U64 | KVM_REG_ARM64_SYSREG | \
     ARM64_SYS_REG((op0), (op1), (crn), (crm), (op2)))

#define CORE_REG_ID(member) \
    (KVM_REG_ARM64 | KVM_REG_SIZE_U64 | KVM_REG_ARM_CORE | \
     KVM_REG_ARM_CORE_REG(member))

struct reg_desc {
    const char *name;
    uint64_t id;
};

static const struct reg_desc regs[] = {
    { "MPIDR_EL1",       SYSREG_ID(3, 0, 0, 0, 5) },
    { "PC",              CORE_REG_ID(regs.pc) },
    { "PSTATE",          CORE_REG_ID(regs.pstate) },
    { "SP_EL1",          CORE_REG_ID(sp_el1) },
    { "ELR_EL1",         CORE_REG_ID(elr_el1) },
    { "CNTV_CTL_EL0",    SYSREG_ID(3, 3, 14, 3, 1) },
    { "CNTV_CVAL_EL0",   SYSREG_ID(3, 3, 14, 3, 2) },
    { "CNTVCT_EL0",      SYSREG_ID(3, 3, 14, 0, 2) },
    { "CNTFRQ_EL0",      SYSREG_ID(3, 3, 14, 0, 0) },
    { "ICC_CTLR_EL1",    SYSREG_ID(3, 0, 12, 12, 4) },
    { "ICC_PMR_EL1",     SYSREG_ID(3, 0, 4, 6, 0) },
    { "ICC_IGRPEN1_EL1", SYSREG_ID(3, 0, 12, 12, 7) },
    { "ICC_BPR1_EL1",    SYSREG_ID(3, 0, 12, 12, 3) },
    { "ICC_RPR_EL1",     SYSREG_ID(3, 0, 12, 11, 3) },
};

// ---------------- ptrace 注入执行目标进程内 ioctl ----------------

// 选择一个可 attach 的线程: 主线程可能处于 D 态(如卡在 kvm_vcpu_ioctl 里),
// 对 D 态线程 PTRACE_ATTACH 会一直阻塞。mm 是进程级的,任意线程 attach 后
// 注入的 ioctl 都满足 kvm->mm == current->mm。优先选 S 态空闲线程。
static pid_t pick_attach_tid(pid_t pid)
{
    char path[64];
    snprintf(path, sizeof(path), "/proc/%d/task", pid);
    DIR *d = opendir(path);
    if (!d)
        return pid;
    pid_t best = -1, running = -1;
    struct dirent *de;
    while ((de = readdir(d)) != NULL) {
        if (de->d_name[0] == '.')
            continue;
        pid_t tid = (pid_t)atoi(de->d_name);
        if (tid <= 0)
            continue;
        char sp[96], buf[512];
        snprintf(sp, sizeof(sp), "%s/%s/stat", path, de->d_name);
        FILE *f = fopen(sp, "r");
        if (!f)
            continue;
        if (fgets(buf, sizeof(buf), f)) {
            char *rp = strrchr(buf, ')');
            char state = rp ? rp[2] : '?';
            if (state == 'S' && best < 0)
                best = tid;
            else if (state == 'R' && running < 0)
                running = tid;
        }
        fclose(f);
    }
    closedir(d);
    if (best > 0)
        return best;
    if (running > 0)
        return running;
    return pid;
}

static int ptrace_attached; // 0=未 attach
static int dbg;             // KVM_REGDUMP_DEBUG=1 时打印诊断到 stderr
#define DBG(...) do { if (dbg) fprintf(stderr, __VA_ARGS__); } while (0)

// 远程 ioctl 可能长时间阻塞(vcpu->mutex 被该 vcpu 的 KVM_RUN/kvm_vcpu_block
// 持有,见文件头注释)。阻塞期间本工具绝不能强退: tracee 正停在注入的 svc 里,
// 强退后它恢复执行会踩到残留 stub/脏寄存器,可能把 VMM 搞崩。因此 SIGINT 只
// 打标记: 第一次提示风险并继续等待,第二次才强制 _exit(风险自担)。
static volatile sig_atomic_t got_sigint;
static volatile sig_atomic_t abort_after; // 当前 ioctl 安全返回后停止后续工作

static void on_sigint(int sig)
{
    (void)sig;
    if (got_sigint)
        _exit(3);
    got_sigint = 1;
}

static int target_attach(pid_t pid)
{
    if (ptrace(PTRACE_ATTACH, pid, 0, 0) < 0) {
        fprintf(stderr, "PTRACE_ATTACH(%d): %s\n", pid, strerror(errno));
        return -1;
    }
    int st;
    if (waitpid(pid, &st, 0) < 0 || !WIFSTOPPED(st)) {
        fprintf(stderr, "waitpid after attach failed: %s\n", strerror(errno));
        return -1;
    }
    ptrace_attached = 1;
    return 0;
}

static void target_detach(pid_t pid)
{
    if (ptrace_attached) {
        ptrace(PTRACE_DETACH, pid, 0, 0);
        ptrace_attached = 0;
    }
}

static uint64_t peek(pid_t pid, uint64_t addr)
{
    errno = 0;
    return (uint64_t)ptrace(PTRACE_PEEKDATA, pid, (void *)(uintptr_t)addr, 0);
}

static int poke(pid_t pid, uint64_t addr, uint64_t val)
{
    return ptrace(PTRACE_POKEDATA, pid, (void *)(uintptr_t)addr, (void *)(uintptr_t)val);
}

// 在目标进程上下文执行 ioctl(fd, KVM_GET_ONE_REG, &one{id, &val})
// 成功返回 0 且 *val 有效;失败返回正 errno。
static int remote_get_one_reg(pid_t pid, int fd, uint64_t id, uint64_t *val)
{
    // aarch64 stub: mov x8,#__NR_ioctl ; svc #0 ; brk #0 ; nop
    const uint32_t stub[4] = {
        0xd2800000 | (29 << 5) | 8, // movz x8, #29  (__NR_ioctl)
        0xd4000001,                 // svc #0
        0xd4200000,                 // brk #0
        0xd503201f,                 // nop
    };

    struct user_regs saved, cur;
    struct iovec iov = { &saved, sizeof(saved) };
    if (ptrace(PTRACE_GETREGSET, pid, (void *)(uintptr_t)NT_PRSTATUS, &iov) < 0) {
        DBG("  [dbg] GETREGSET: %s\n", strerror(errno));
        return EIO;
    }

    uint64_t pc = saved.pc;
    uint64_t data = (saved.sp - 512) & ~15UL; // 目标栈上 16B one_reg + 8B value
    DBG("  [dbg] pc=0x%lx sp=0x%lx data=0x%lx\n",
        (unsigned long)pc, (unsigned long)saved.sp, (unsigned long)data);

    uint64_t orig_code[2] = { peek(pid, pc), peek(pid, pc + 8) };
    if (errno) {
        DBG("  [dbg] PEEKDATA pc: %s\n", strerror(errno));
        return EIO;
    }
    DBG("  [dbg] orig_code=%016lx %016lx\n",
        (unsigned long)orig_code[0], (unsigned long)orig_code[1]);

    // 写入 stub 和 struct kvm_one_reg { id, addr }
    uint64_t stubw[2];
    memcpy(stubw, stub, sizeof(stub));
    if (poke(pid, pc, stubw[0]) < 0 || poke(pid, pc + 8, stubw[1]) < 0) {
        DBG("  [dbg] POKE stub: %s\n", strerror(errno));
        goto restore_fail;
    }
    if (poke(pid, data, id) < 0 || poke(pid, data + 8, data + 16) < 0) {
        DBG("  [dbg] POKE data: %s\n", strerror(errno));
        goto restore_fail;
    }

    cur = saved;
    cur.x[0] = (uint64_t)fd;
    cur.x[1] = (uint64_t)KVM_GET_ONE_REG;
    cur.x[2] = data;
    iov.iov_base = &cur;
    if (ptrace(PTRACE_SETREGSET, pid, (void *)(uintptr_t)NT_PRSTATUS, &iov) < 0)
        goto restore_fail;

    // 执行到 brk #0。ioctl 可能阻塞(vcpu->mutex 被持有),用 WNOHANG 轮询,
    // 超过 5s 打警告但继续等 —— 中途放弃不安全(见 got_sigint 注释)。
    int st, sig = 0, tries = 0, waited_ms = 0, warned = 0, sigint_warned = 0;
    for (;;) {
        if (ptrace(PTRACE_CONT, pid, 0, (void *)(uintptr_t)sig) < 0)
            goto restore_fail;
        for (;;) {
            pid_t w = waitpid(pid, &st, WNOHANG);
            if (w == pid)
                break;
            if (w < 0)
                goto restore_fail;
            usleep(20000);
            waited_ms += 20;
            if (!warned && waited_ms >= 5000) {
                warned = 1;
                fprintf(stderr,
                        "  [warn] remote ioctl(fd=%d) 阻塞 >5s: 该 vcpu 的 mutex 正被 "
                        "KVM_RUN/kvm_vcpu_block 持有,继续等待其返回…\n", fd);
            }
            if (got_sigint && !sigint_warned) {
                sigint_warned = 1;
                abort_after = 1;
                fprintf(stderr,
                        "  [warn] 收到 SIGINT,但注入的远程 ioctl 尚未返回。强行终止本工具会在\n"
                        "         目标进程留下残留 stub/脏寄存器,ioctl 返回时可能导致 VMM 崩溃。\n"
                        "         将等该 ioctl 返回后安全退出;再次 Ctrl-C 强制退出(风险自担)。\n");
            }
        }
        if (!WIFSTOPPED(st))
            goto restore_fail;
        sig = WSTOPSIG(st);
        if (sig == SIGTRAP || ++tries > 8)
            break;
    }
    DBG("  [dbg] stopped sig=%d tries=%d\n", sig, tries);

    iov.iov_base = &cur;
    if (ptrace(PTRACE_GETREGSET, pid, (void *)(uintptr_t)NT_PRSTATUS, &iov) < 0)
        goto restore_fail;
    long ret = (long)cur.x[0];
    DBG("  [dbg] after: pc=0x%lx x0=%ld (0x%lx)\n",
        (unsigned long)cur.pc, ret, (unsigned long)cur.x[0]);
    uint64_t out = peek(pid, data + 16);
    if (errno) goto restore_fail;

    // 恢复指令与寄存器
    poke(pid, pc, orig_code[0]);
    poke(pid, pc + 8, orig_code[1]);
    iov.iov_base = &saved;
    ptrace(PTRACE_SETREGSET, pid, (void *)(uintptr_t)NT_PRSTATUS, &iov);

    if (ret < 0 && ret >= -4095)
        return (int)(-ret);
    if (ret != 0)
        return EIO;
    *val = out;
    return 0;

restore_fail:
    poke(pid, pc, orig_code[0]);
    poke(pid, pc + 8, orig_code[1]);
    iov.iov_base = &saved;
    ptrace(PTRACE_SETREGSET, pid, (void *)(uintptr_t)NT_PRSTATUS, &iov);
    return EIO;
}

// ---------------- /proc/<pid>/fd 枚举 ----------------

static int collect_vcpu_fds(pid_t pid, int *out, int max)
{
    char path[64];
    snprintf(path, sizeof(path), "/proc/%d/fd", pid);
    DIR *d = opendir(path);
    if (!d) {
        fprintf(stderr, "opendir %s: %s\n", path, strerror(errno));
        return -1;
    }
    int n = 0;
    struct dirent *de;
    while ((de = readdir(d)) != NULL && n < max) {
        if (de->d_name[0] == '.')
            continue;
        char *end;
        long fdnum = strtol(de->d_name, &end, 10);
        if (*end != '\0')
            continue;
        char linkpath[320], target[256];
        snprintf(linkpath, sizeof(linkpath), "%s/%s", path, de->d_name);
        ssize_t len = readlink(linkpath, target, sizeof(target) - 1);
        if (len < 0)
            continue;
        target[len] = '\0';
        // 实测形态: "anon_inode:kvm-vcpu:0" / "anon_inode:kvm-vcpu:1"
        if (strstr(target, "kvm-vcpu") != NULL)
            out[n++] = (int)fdnum;
    }
    closedir(d);
    return n;
}

static int cmp_int(const void *a, const void *b)
{
    return *(const int *)a - *(const int *)b;
}

// 预检: 统计目标进程中卡在 kvm_vcpu_ioctl(D 态)的线程数并警告。
// 这类线程说明已有 vcpu ioctl 长时间拿不到 vcpu->mutex,本工具的注入也可能阻塞。
static int count_stuck_vcpu_ioctl_threads(pid_t pid)
{
    char path[64];
    snprintf(path, sizeof(path), "/proc/%d/task", pid);
    DIR *d = opendir(path);
    if (!d)
        return 0;
    int stuck = 0;
    struct dirent *de;
    while ((de = readdir(d)) != NULL) {
        if (de->d_name[0] == '.')
            continue;
        pid_t tid = (pid_t)atoi(de->d_name);
        if (tid <= 0)
            continue;
        char sp[320], buf[512];
        snprintf(sp, sizeof(sp), "%s/%s/stat", path, de->d_name);
        FILE *f = fopen(sp, "r");
        if (!f)
            continue;
        char state = '?';
        if (fgets(buf, sizeof(buf), f)) {
            char *rp = strrchr(buf, ')');
            if (rp)
                state = rp[2];
        }
        fclose(f);
        if (state != 'D')
            continue;
        snprintf(sp, sizeof(sp), "%s/%s/wchan", path, de->d_name);
        f = fopen(sp, "r");
        if (!f)
            continue;
        if (fgets(buf, sizeof(buf), f) && strstr(buf, "kvm_vcpu_ioctl"))
            stuck++;
        fclose(f);
    }
    closedir(d);
    return stuck;
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <vmm_pid> [vcpu_fd ...]\n", argv[0]);
        return 2;
    }
    pid_t pid = (pid_t)atoi(argv[1]);
    if (pid <= 0) {
        fprintf(stderr, "invalid pid: %s\n", argv[1]);
        return 2;
    }
    dbg = getenv("KVM_REGDUMP_DEBUG") != NULL;
    signal(SIGINT, on_sigint);
    signal(SIGTERM, on_sigint);

    int stuck = count_stuck_vcpu_ioctl_threads(pid);
    if (stuck > 0)
        fprintf(stderr,
                "warning: 目标进程有 %d 个线程已卡在 kvm_vcpu_ioctl(D 态,拿不到 vcpu->mutex)。\n"
                "         对同一 vcpu 的注入读取也会阻塞,建议用 fd 参数只 dump 其他 vcpu。\n",
                stuck);

    int pidfd = sys_pidfd_open(pid, 0);
    if (pidfd < 0) {
        fprintf(stderr, "pidfd_open(%d): %s\n", pid, strerror(errno));
        return 1;
    }

    int fdnums[256];
    int n;
    if (argc > 2) {
        n = 0;
        for (int i = 2; i < argc && n < 256; i++)
            fdnums[n++] = atoi(argv[i]);
    } else {
        n = collect_vcpu_fds(pid, fdnums, 256);
        if (n < 0)
            return 1;
        if (n == 0) {
            fprintf(stderr, "no kvm-vcpu fds found in /proc/%d/fd\n", pid);
            return 1;
        }
        qsort(fdnums, n, sizeof(int), cmp_int);
    }

    printf("target pid=%d, %d vcpu fd(s)\n", pid, n);

    int use_ptrace = 0;
    pid_t atid = -1; // ptrace 实际 attach 的线程
    for (int i = 0; i < n; i++) {
        int tfd = fdnums[i];
        printf("=== vcpu fd %d ===\n", tfd);

        if (!use_ptrace) {
            // 路径 A: pidfd_getfd 复制 fd 后直接 ioctl(仅同 mm 才可能成功)
            int vfd = sys_pidfd_getfd(pidfd, tfd, 0);
            if (vfd < 0) {
                printf("  pidfd_getfd(%d) failed: %s, falling back to ptrace\n",
                       tfd, strerror(errno));
                use_ptrace = 1;
            } else {
                uint64_t val = 0;
                struct kvm_one_reg one = { regs[0].id, (uint64_t)(uintptr_t)&val };
                if (ioctl(vfd, KVM_GET_ONE_REG, &one) == 0) {
                    printf("  [mode: pidfd_getfd]\n");
                    printf("  %-16s 0x%016lx\n", regs[0].name, (unsigned long)val);
                    for (size_t r = 1; r < sizeof(regs) / sizeof(regs[0]); r++) {
                        val = 0;
                        one.id = regs[r].id;
                        if (ioctl(vfd, KVM_GET_ONE_REG, &one) == 0)
                            printf("  %-16s 0x%016lx\n", regs[r].name, (unsigned long)val);
                        else
                            printf("  %-16s <error: errno=%d (%s)>\n",
                                   regs[r].name, errno, strerror(errno));
                    }
                    close(vfd);
                    continue;
                }
                int e = errno;
                close(vfd);
                if (e == EIO) {
                    printf("  direct ioctl: EIO (KVM 限制跨 mm vcpu ioctl),切到 ptrace 注入\n");
                    use_ptrace = 1;
                } else {
                    printf("  %-16s <error: errno=%d (%s)>\n", regs[0].name, e, strerror(e));
                    continue;
                }
            }
        }

        // 路径 B: ptrace 注入
        if (!ptrace_attached) {
            atid = pick_attach_tid(pid);
            printf("  [attach tid=%d]\n", atid);
            if (target_attach(atid) < 0)
                return 1;
        }
        printf("  [mode: ptrace-inject]\n");
        for (size_t r = 0; r < sizeof(regs) / sizeof(regs[0]); r++) {
            uint64_t val = 0;
            int err = remote_get_one_reg(atid, tfd, regs[r].id, &val);
            if (err == 0)
                printf("  %-16s 0x%016lx\n", regs[r].name, (unsigned long)val);
            else
                printf("  %-16s <error: errno=%d (%s)>\n",
                       regs[r].name, err, strerror(err));
            fflush(stdout);
            if (abort_after)
                break;
        }
        if (abort_after)
            break;
    }
    target_detach(atid > 0 ? atid : pid);
    close(pidfd);
    return 0;
}
