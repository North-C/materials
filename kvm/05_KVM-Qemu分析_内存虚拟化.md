# 背景

- `Read the fucking source code!`  --By 鲁迅
- `A picture is worth a thousand words.` --By 高尔基

说明：

- KVM版本：5.9.1
- QEMU版本：5.0.0
- 工具：Source Insight 3.5， Visio
- 文章同步在博客园：`https://www.cnblogs.com/LoyenWang/`

# 1. 概述

`《Linux虚拟化KVM-Qemu分析（二）之ARMv8虚拟化》`文中描述过内存虚拟化大体框架，再来回顾一下：

- 非虚拟化下的内存的访问

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107233823163-1248765431.png)

- CPU访问物理内存前，需要先建立页表映射（虚拟地址到物理地址的映射），最终通过查表的方式来完成访问。在ARMv8中，内核页表基地址存放在`TTBR1_EL1`中，用户空间页表基地址存放在`TTBR0_EL0`中；

- 虚拟化下的内存访问

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107233831393-633851095.png)

- 虚拟化情况下，内存的访问会分为两个`Stage`，`Hypervisor`通过`Stage 2`来控制虚拟机的内存视图，控制虚拟机是否可以访问某块物理内存，进而达到隔离的目的；
- `Stage 1`：`VA(Virtual Address)->IPA(Intermediate Physical Address)`，Host的操作系统控制`Stage 1`的转换；
- `Stage 2`：`IPA(Intermediate Physical Address)->PA(Physical Address)`，Hypervisor控制`Stage 2`的转换；

猛一看上边两个图，好像明白了啥，仔细一想，啥也不明白，本文的目标就是将这个过程讲明白。

在开始细节讲解之前，需要先描述几个概念：

```
gva - guest virtual address
gpa - guest physical address
hva - host virtual address
hpa - host physical address

```

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107233844101-140556043.png)

- Guest OS中的虚拟地址到物理地址的映射，就是典型的常规操作，参考之前的内存管理模块系列文章；

铺垫了这么久，来到了本文的两个主题：

- `GPA->HVA`;
- `HVA->HPA`;

开始吧！

# 2. GPA->HVA

还记得上一篇文章`《Linux虚拟化KVM-Qemu分析（四）之CPU虚拟化（2）》`中的Sample Code吗？

KVM-Qemu方案中，GPA->HVA的转换，是通过`ioctl`中的`KVM_SET_USER_MEMORY_REGION`命令来实现的，如下图：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107233855813-554323553.png)

找到了入口，让我们进一步揭开神秘的面纱。

## 2.1 数据结构

关键的数据结构如下：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107233904748-592916078.png)

- 虚拟机使用`slot`来组织物理内存，每个`slot`对应一个`struct kvm_memory_slot`，一个虚拟机的所有`slot`构成了它的物理地址空间；
- 用户态使用`struct kvm_userspace_memory_region`来设置内存`slot`，在内核中使用`struct kvm_memslots`结构来将`kvm_memory_slot`组织起来；
- `struct kvm_userspace_memory_region`结构体中，包含了`slot`的ID号用于查找对应的`slot`，此外还包含了物理内存起始地址及大小，以及HVA地址，HVA地址是在用户进程地址空间中分配的，也就是Qemu进程地址空间中的一段区域；

## 2.2 流程分析

数据结构部分已经罗列了大体的关系，那么在`KVM_SET_USER_MEMORY_REGION`时，围绕的操作就是`slots`的创建、删除，更新等操作，话不多说，来图了：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107233915050-1368514616.png)

- 当用户要设置内存区域时，最终会调用到`__kvm_set_memory_region`函数，在该函数中完成所有的逻辑处理；
- `__kvm_set_memory_region`函数，首先会对传入的`struct kvm_userspace_memory_region`的各个字段进行合法性检测判断，主要是包括了地址的对齐，范围的检测等；
- 根据用户传递的`slot`索引号，去查找虚拟机中对应的`slot`，查找的结果只有两种：1）找到一个现有的slot；2）找不到则新建一个slot；
- 如果传入的参数中`memory_size`为0，那么会将对应`slot`进行删除操作；
- 根据用户传入的参数，设置`slot`的处理方式：`KVM_MR_CREATE`，`KVM_MR_MOVE`，`KVM_MEM_READONLY`；
- 根据用户传递的参数决定是否需要分配脏页的bitmap，标识页是否可用；
- 最终调用`kvm_set_memslot`来设置和更新`slot`信息；

### 2.2.1 kvm_set_memslot

具体的`memslot`的设置在`kvm_set_memslot`函数中完成，`slot`的操作流程如下：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107233927534-60352225.png)

- 首先分配一个新的`memslots`，并将原来的`memslots`内容复制到新的`memslots`中；
- 如果针对`slot`的操作是删除或者移动，首先根据旧的`slot id`号从`memslots`中找到原来的`slot`，将该`slot`设置成不可用状态，再将`memslots`安装回去。这个安装的意思，就是RCU的assignment操作，不理解这个的，建议去看看之前的RCU系列文章。由于`slot`不可用了，需要解除stage2的映射；
- `kvm_arch_prepare_memory_region`函数，用于处理新的`slot`可能跨越多个用户进程VMA区域的问题，如果为设备区域，还需要将该区域映射到`Guest IPA`中；
- `update_memslots`用于更新整个`memslots`，`memslots`基于PFN来进行排序的，添加、删除、移动等操作都是基于这个条件。由于都是有序的，因此可以选择二分法来进行查找操作；
- 将添加新的`slot`后的`memslots`安装回KVM中；
- `kvfree`用于将原来的`memslots`释放掉；

### 2.2.2 kvm_delete_memslot

`kvm_delete_memslot`函数，实际就是调用的`kvm_set_memslot`函数，只是`slot`的操作设置成`KVM_MR_DELETE`而已，不再赘述。

# 3. HVA->HPA

光有了GPA->HVA，似乎还是跟`Hypervisor`没有太大关系，到底是怎么去访问物理内存的呢？貌似也没有看到去建立页表映射啊？

跟我走吧，带着问题出发！

之前内存管理相关文章中提到过，用户态程序中分配虚拟地址vma后，实际与物理内存的映射是在`page fault`时进行的。那么同样的道理，我们可以顺着这个思路去查找是否HVA->HPA的映射也是在异常处理的过程中创建的？答案是显然的。

回顾一下前文`《Linux虚拟化KVM-Qemu分析（四）之CPU虚拟化（2）》`的一张图片：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107233941226-1298320533.png)

- 当用户态触发`kvm_arch_vcpu_ioctl_run`时，会让`Guest OS`去跑在`Hypervisor`上，当`Guest OS`中出现异常退出到`Host`时，此时`handle_exit`将对退出的原因进行处理；

异常处理函数`arm_exit_handlers`如下，具体调用选择哪个处理函数，是根据`ESR_EL2, Exception Syndrome Register(EL2)`中的值来确定的。

```
static exit_handle_fn arm_exit_handlers[] = {
	[0 ... ESR_ELx_EC_MAX]	= kvm_handle_unknown_ec,
	[ESR_ELx_EC_WFx]	= kvm_handle_wfx,
	[ESR_ELx_EC_CP15_32]	= kvm_handle_cp15_32,
	[ESR_ELx_EC_CP15_64]	= kvm_handle_cp15_64,
	[ESR_ELx_EC_CP14_MR]	= kvm_handle_cp14_32,
	[ESR_ELx_EC_CP14_LS]	= kvm_handle_cp14_load_store,
	[ESR_ELx_EC_CP14_64]	= kvm_handle_cp14_64,
	[ESR_ELx_EC_HVC32]	= handle_hvc,
	[ESR_ELx_EC_SMC32]	= handle_smc,
	[ESR_ELx_EC_HVC64]	= handle_hvc,
	[ESR_ELx_EC_SMC64]	= handle_smc,
	[ESR_ELx_EC_SYS64]	= kvm_handle_sys_reg,
	[ESR_ELx_EC_SVE]	= handle_sve,
	[ESR_ELx_EC_IABT_LOW]	= kvm_handle_guest_abort,
	[ESR_ELx_EC_DABT_LOW]	= kvm_handle_guest_abort,
	[ESR_ELx_EC_SOFTSTP_LOW]= kvm_handle_guest_debug,
	[ESR_ELx_EC_WATCHPT_LOW]= kvm_handle_guest_debug,
	[ESR_ELx_EC_BREAKPT_LOW]= kvm_handle_guest_debug,
	[ESR_ELx_EC_BKPT32]	= kvm_handle_guest_debug,
	[ESR_ELx_EC_BRK64]	= kvm_handle_guest_debug,
	[ESR_ELx_EC_FP_ASIMD]	= handle_no_fpsimd,
	[ESR_ELx_EC_PAC]	= kvm_handle_ptrauth,
};

```

用你那双水汪汪的大眼睛扫描一下这个函数表，发现`ESR_ELx_EC_DABT_LOW`和`ESR_ELx_EC_IABT_LOW`两个异常，这不就是指令异常和数据异常吗，我们大胆的猜测，`HVA->HPA`映射的建立就在`kvm_handle_guest_abort`函数中。

## 3.1 `kvm_handle_guest_abort`

先来补充点知识点，可以更方便的理解接下里的内容：

- Guest OS在执行到敏感指令时，产生EL2异常，CPU切换模式并跳转到`EL2`的`el1_sync`（`arch/arm64/kvm/hyp/entry-hyp.S`）异常入口；
- CPU的`ESR_EL2`寄存器记录了异常产生的原因；
- Guest退出到kvm后，kvm根据异常产生的原因进行对应的处理。

简要看一下`ESR_EL2`寄存器：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107233952862-20535881.png)

- `EC`：Exception class，异常类，用于标识异常的原因；
- `ISS`：Instruction Specific Syndrome，ISS域定义了更详细的异常细节；
- 在`kvm_handle_guest_abort`函数中，多处需要对异常进行判断处理；

`kvm_handle_guest_abort`函数，处理地址访问异常，可以分为两类：

- 常规内存访问异常，包括未建立页表映射、读写权限等；
- IO内存访问异常，IO的模拟通常需要Qemu来进行模拟；

先看一下`kvm_handle_guest_abort`函数的注释吧：

```
/**
 * kvm_handle_guest_abort - handles all 2nd stage aborts
 *
 * Any abort that gets to the host is almost guaranteed to be caused by a
 * missing second stage translation table entry, which can mean that either the
 * guest simply needs more memory and we must allocate an appropriate page or it
 * can mean that the guest tried to access I/O memory, which is emulated by user
 * space. The distinction is based on the IPA causing the fault and whether this
 * memory region has been registered as standard RAM by user space.
 */

```

- 到达Host的abort都是由于缺乏Stage 2页表转换条目导致的，这个可能是Guest需要分配更多内存而必须为其分配内存页，或者也可能是Guest尝试去访问IO空间，IO操作由用户空间来模拟的。两者的区别是触发异常的IPA地址是否已经在用户空间中注册为标准的RAM；

调用流程来了：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107234014086-1464598545.png)

- `kvm_vcpu_trap_get_fault_type`用于获取`ESR_EL2`的数据异常和指令异常的`fault status code`，也就是`ESR_EL2`的ISS域；
- `kvm_vcpu_get_fault_ipa`用于获取触发异常的IPA地址；
- `kvm_vcpu_trap_is_iabt`用于获取异常类，也就是`ESR_EL2`的`EC`，并且判断是否为`ESR_ELx_IABT_LOW`，也就是指令异常类型；
- `kvm_vcpu_dabt_isextabt`用于判断是否为同步外部异常，同步外部异常的情况下，如果支持RAS，Host能处理该异常，不需要将异常注入给Guest；
- 异常如果不是`FSC_FAULT`，`FSC_PERM`，`FSC_ACCESS`三种类型的话，直接返回错误；
- `gfn_to_memslot`，`gfn_to_hva_memslot_prot`这两个函数，是根据IPA去获取到对应的memslot和HVA地址，这个地方就对应到了上文中第二章节中地址关系的建立了，由于建立了连接关系，便可以通过IPA去找到对应的HVA；
- 如果注册了RAM，能获取到正确的HVA，如果是IO内存访问，那么HVA将会被设置成`KVM_HVA_ERR_BAD`。`kvm_is_error_hva`或者`(write_fault && !writable)`代表两种错误：1）指令错误，向Guest注入指令异常；2）IO访问错误，IO访问又存在两种情况：2.1）Cache维护指令，则直接跳过该指令；2.2）正常的IO操作指令，调用`io_mem_abort`进行IO模拟操作；
- `handle_access_fault`用于处理访问权限问题，如果内存页无法访问，则对其权限进行更新；
- `user_mem_abort`，用于分配更多的内存，实际上就是完成Stage 2页表映射的建立，根据异常的IPA地址，已经对应的HVA，建立映射，细节的地方就不表了。

来龙去脉摸清楚了，那就草草收场吧，下回见了。

# 参考

`《Arm Architecture Registers Armv8, for Armv8-A architecture profile》`

欢迎关注个人公众号，不定期分享技术文章。

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201107234044212-1724655073.jpg)

    
  作者：[LoyenWang](https://www.cnblogs.com/LoyenWang/)

  出处：https://www.cnblogs.com/LoyenWang/

  公众号：LoyenWang

  版权：本文版权归作者和博客园共有

  转载：欢迎转载，但未经作者同意，必须保留此段声明；必须在文章中给出原文连接；否则必究法律责任

    
    
    <div
