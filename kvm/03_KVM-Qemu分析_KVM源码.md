# 背景

- `Read the fucking source code!`  --By 鲁迅
- `A picture is worth a thousand words.` --By 高尔基

说明：

- KVM版本：5.9.1
- QEMU版本：5.0.0
- 工具：Source Insight 3.5， Visio
- 文章同步在博客园：`https://www.cnblogs.com/LoyenWang/`

# 1. 概述

- 从本文开始将开始`source code`的系列分析了；
- `KVM`作为内核模块，可以认为是一个中间层，向上对接用户的控制，向下对接不同架构的硬件虚拟化支持；
- 本文主要介绍体系架构初始化部分，以及向上的框架；

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222650919-1567051347.png)

# 2. KVM初始化

- 贝多芬曾经说过，一旦你找到了代码的入口，你就扼住了软件的咽喉；
- 我们的故事，从`module_init(arm_init)`开始，代码路径：`arch/arm64/kvm/arm.c`；

老规矩，先来一张图（`图片中涉及到的红色框函数，都是会展开描述的`）：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222700148-1239477465.png)

- 内核的功能模块，基本上的套路就是：1）完成模块初始化，向系统注册；2）响应各类请求，这种请求可能来自用户态，也可能来自异常响应等；
- `kvm`的初始化，在`kvm_init`中完成，既包含了体系结构相关的初始化设置，也包含了各类回调函数的设置，资源分配，以及设备注册等，只有当初始化完成后，才能响应各类请求，比如创建虚拟机等；

- 回调函数设置：`cpuhp_setup_state_nocall`与CPU的热插拔相关，`register_reboot_notifer`与系统的重启相关，`register_syscore_ops`与系统的休眠唤醒相关，而这几个模块的回调函数，最终都会去调用体系结构相关的函数去打开或关闭`Hypervisor`；
- 资源分配：`kmem_cache_create_usercopy`与`kvm_async_pf_init`都是创建`slab缓存`，用于内核对象的分配；
- `kvm_vfio_ops_init`：`VFIO`是一个可以安全将设备`I/O`、中断、DMA导出到用户空间的框架，后续在将IO虚拟化时再深入分析；

- 图片中红色的两个函数，是本文分析的内容，其中`kvm_arch_init`与前文`ARMv8`硬件虚拟化支持紧密相关，而`misc_register`与上层操作紧密相关；

## 2.1 `kvm_arch_init`

- `It's a big topic, I'll try to put it in a nutshell.`
- 这部分内容，设计ARMv8体系结构，建议先阅读`《Linux虚拟化KVM-Qemu分析（二）之ARMv8虚拟化》`；
- 红色框的函数是需要进一步展开讲述的；

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222711513-1401018278.png)

- `is_hyp_mode_available`用于判断ARMv8的`Hyp`模式是否可用，实际是通过判断`__boot_cpu_mode`的值来完成，该值是在`arch/arm64/kernel/head.S`中定义，在启动阶段会设置该值：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222721754-393110916.png)

- `is_kernel_in_hyp_mode`，通过读取ARMv8的`CurrentEL`，判断是否为`CurrentEL_EL2`；
- ARM架构中，`SVE`的实现要求`VHE`也要实现，这个可以从`arch/arm64/Kconfig`中看到，`SVE`的模块编译：`depends on !KVM || ARM64_VHE`。`SVE（scalable vector extension）`，是`AArch64`下一代的`SIMD（single instruction multiple data）`指令集，用于加速高性能计算。其中`SIMD`如下：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222731505-94384937.png)

- `init_common_resources`，用于设置`IPA`的地址范围，将其限制在系统能支持的物理地址范围之内。`stage 2`页表依赖于`stage 1`页表代码，需要遵循一个条件：`Stage 1`的页表级数 >= `Stage 2`的页表级数；

### 2.1.1 `init_hyp_mode`

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222742609-1312747583.png)

- 放眼望去，`init_hyp_mode`解决的问题就是各种映射，最终都会调用到`__create_hyp_mappings`，先来解决这个映射问题：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222752878-346094335.png)

- 看过之前内存管理子系统的同学，应该熟悉这个页表映射建立的过程，基本的流程是给定一个虚拟地址区间和物理地址，然后从`pgd`开始逐级往下去建立映射。ARMv8架构在实际映射过程中，`P4D`这一级页表并没有使用。

让我们继续回到`init_hyp_mode`的正题上来，这个函数完成了`PGD`页表的分配，完成了`IDMAP代码段`的映射，完成了其他各种段的映射，完成了异常向量表的映射，等等。此外，再补充几点内容：

- `ARMv8异常向量表`

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222800351-1078869766.png)

- ARMv8架构的AArch64执行态中，每种EL都有16个entry，分为四类：`Synchronous，IRQ，FIQ，SError`。以系统启动时设置hypervisor的异常向量表`__hyp_stub_vectors`为例：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222808849-70054640.png)

- 当从不同的`Exception Level`触发异常时，根据执行状态，去选择对应的`handler`处理，比如上图中只有`el1_sync`有效，也就是在`EL1`状态触发`EL2`时跳转到该函数；

- `pushsection/popsection`

- 在`init_hyp_mode`函数中，完成各种段的映射，段的定义放置在`vmlinux.lds.S`中，比如`hyp.idmap.text`：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222816967-512832387.png)

- 可以通过`pushsection/popsection`来在目标文件中来添加一个段，并指定段的属性，比如"ax"代表可分配和可执行，这个在汇编代码中经常用到，比如`hyp-init.S`中，会将代码都放置在`hyp.idmap.text`中：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222828959-25692944.png)

- 除了`pushsection/popsection`外，通过`#define __hyp_text __section(.hyp.text) notrace __noscs`的形式也能将代码放置在指定的段中；

- `Hypervisor相关寄存器`

- 讲几个关键的相关寄存器：

1）`sctlr_el2(System Control Register)`：可以用于控制EL2的MMU和Cache相关操作；

2）`ttbr0_el2(Translation Table Base Register 0)`：用于存放页表的基地址，上文中提到分配的`hyp_pgd`就需要设置到该寄存器中；

3）`vbar_el2(Vector Base Address Register)`：用于存放异常向量表的基地址；

我们需要先明确几点：

- `Hyp`模式下要执行的代码，需要先建立起映射；
- 映射`IDMAP代码段`和其他代码段，明确这些段中都有哪些函数，这个可以通过`pushsection/popsection`以及`__hyp_text`宏可以看出来；
- 最终的目标是需要建立好页表映射，并安装好异常向量表；

貌似内容比较零碎，最终的串联与谜题留在下一小节来解答。

### 2.1.2 `init_subsystems`

先看一下函数的调用流程：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222841797-249131309.png)

- `VGIC`，`timer`，以及电源管理相关模块在本文中暂且不深入分析了，本节主要关心`cpu_hyp_reinit`的功能；
- 绿色框中的函数，会陷入到`EL2`进行执行；

看图中有好几次异常向量表的设置，此外，还有页表基地址、栈页的获取与设置等，结合上一小节的各类映射，是不是已经有点迷糊了，下边这张图会将这些内容串联起来：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222849648-179677220.png)

- 在整个异常向量表创建的过程中，涉及到三个向量表：`__hyp_stub_vectors`，`__kvm_hyp_init`， `__kvm_call_hyp`，这些代码都是汇编实现；
- 在系统启动过程中(`arch/arm64/kernel/head.S`)，调用到`el2_setup`函数，在该函数中设置了一个临时的异常向量表，也就是先打一个桩，这个从名字也可以看出来，该异常向量表中仅实现了`el2_sync`的`handler`处理函数，可以应对两种异常：1）设置新的异常向量表；2）重置异常向量表，也就是设置回`__hyp_stub_vectors`；
- 在`kvm`初始化时，调用了`__hyp_set_vectors`来设置新的异常向量表：`__kvm_hyp_init`。这个向量表中只实现了`__do_hyp_init`的处理函数，也就是只能用来对`Hyp模式`进行初始化。上文提到过`idmap段`，这个代码就放置在`idmap段`，以前分析内存管理子系统时也提到过`idmap`，为什么需要这个呢？`idmap: identity map`，也就是物理地址和虚拟地址是一一映射的，防止MMU在使能前后代码不能执行；
- `__kvm_call_hyp`函数，用于在`Hyp模式`下执行指定的函数，在`cpu_hyp_reinit`函数中调用了该函数，传递的参数包括了新的异常向量表地址，页表基地址，`Hyp`的栈地址，`per-CPU`偏移等，最终会调用`__do_hyp_init`函数完成相应的设置。

到此，页表和异常向量表的设置算是完成了。

## 2.2 `misc_register`

`misc_register`用于注册字符设备驱动，在`kvm_init`函数中调用此函数完成注册，以便上层应用程序来使用`kvm模块`：

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222902627-2095696577.png)

- 字符设备的注册分为三级，分别代表`kvm`, `vm`, `vcpu`，上层最终使用底层的服务都是通过`ioctl`函数来操作；
- `kvm`：代表kvm内核模块，可以通过`kvm_dev_ioctl`来管理kvm版本信息，以及vm的创建等；
- `vm`：虚拟机实例，可以通过`kvm_vm_ioctl`函数来创建`vcpu`，设置内存区间，分配中断等；
- `vcpu`：代表虚拟的CPU，可以通过`kvm_vcpu_ioctl`来启动或暂停CPU的运行，设置vcpu的寄存器等；

以`Qemu`的使用为例：

- 打开`/dev/kvm`设备文件；
- `ioctl(xx, KVM_CREATE_VM, xx)`创建虚拟机对象；
- `ioctl(xx, KVM_CREATE_VCPU, xx)`为虚拟机创建vcpu对象；
- `ioctl(xx, KVM_RUN, xx)`让vcpu运行起来；

# 3. 总结

本文主要从两个方向来介绍了`kvm_init`：

- 底层的体系结构相关的初始化，主要涉及的就是`EL2`的相关设置，比如各个段的映射，异常向量表的安装，页表基地址的设置等，当把这些准备工作做完后，才能在硬件上去支持虚拟化的服务请求；
- 字符设备注册，设置好各类`ioctl`的函数，上层应用程序可以通过字符设备文件，来操作底层的kvm模块。这部分内容深入的分析，留到后续的文章再展开了；

实际在看代码过程中，一度为很多细节绞尽乳汁，对不起，是绞尽脑汁，每有会意，便欣然忘食，一文也无法覆盖所有内容，草率了。

欢迎关注个人公众号，不定期更新技术文章。

![](https://img2020.cnblogs.com/blog/1771657/202009/1771657-20200912222930460-675524344.jpg)

    
  作者：[LoyenWang](https://www.cnblogs.com/LoyenWang/)

  出处：https://www.cnblogs.com/LoyenWang/

  公众号：LoyenWang

  版权：本文版权归作者和博客园共有

  转载：欢迎转载，但未经作者同意，必须保留此段声明；必须在文章中给出原文连接；否则必究法律责任

    
    
    <div
