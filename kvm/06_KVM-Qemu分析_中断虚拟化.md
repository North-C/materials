# 背景

- `Read the fucking source code!`  --By 鲁迅
- `A picture is worth a thousand words.` --By 高尔基

说明：

- KVM版本：5.9.1
- QEMU版本：5.0.0
- 工具：Source Insight 3.5， Visio
- 文章同步在博客园：`https://www.cnblogs.com/LoyenWang/`

# 1. 概述

本文会将ARM GICv2中断虚拟化的总体框架和流程讲清楚，这个曾经困扰我好几天的问题在被捋清的那一刻，让我有点`每有会意，欣然忘食`的感觉。

在讲述中断虚拟化之前，我们应该对中断的作用与处理流程有个大致的了解：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200155604-2066331250.png)

- 中断是处理器用于异步处理外围设备请求的一种机制；
- 外设通过硬件管脚连接在中断控制器上，并通过电信号向中断控制器发送请求；
- 中断控制器将外设的中断请求路由到CPU上；
- CPU（以ARM为例）进行模式切换（切换到IRQ/FIQ），保存Context后，根据外设的中断号去查找系统中已经注册好的Handler进行处理，处理完成后再将Context进行恢复，接着之前打断的执行流继续move on；
- 中断的作用不局限于外设的处理，系统的调度，SMP核间交互等，都离不开中断；

 

中断虚拟化，将从中断信号产生到路由到vCPU的角度来展开，包含以下三种情况：

- 物理设备产生中断信号，路由到vCPU；
- 虚拟外设产生中断信号，路由到vCPU；
- Guest OS中CPU之间产生中断信号（IPI中断）；

本文将围绕`ARM-GICv2`来描述，因此也不会涉及到`MSI`以及`ITS`等特性，带着问题出发吧。

# 2. VGIC

- 在讲中断虚拟化之前，有必要先讲一下ARMv8中Hypervisor的架构，因为涉及到不同的Exception Level的切换；
- 在我阅读源代码时，根据代码去匹配某篇Paper中的理论时，出现了一些理解偏差，曾一度困扰了我好几天;

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200207574-301453430.png)

- `Non-VHE`

- Linux ARM架构的Hypervisor在引入时，采用的是左图中的系统架构，以便能充分利用Linux现有的机制，比如scheduler等；
- KVM/ARM的实现采用了`split`模式，分成`Highvisor`和`Lowvisor`，这样可以充分利用ARM处理器不同模式的好处，比如，`Highvisor`可以利用Linux Kernel的现有机制，而`Lowvisor`又可以利用`Hyp Mode`的特权。此外，带来的好处还包含了不需要大量修改Linux内核的代码，这个在刚引入的时候是更容易被社区所接受的；
- `Lowvisor`有三个关键功能：1）对不同的执行Context进行隔离与保护，比如VM之间不会相互影响；2）提供Guest和Host的相互切换，也就是所谓的`world switch`；3）提供一个虚拟化`trap handler`，用于处理trap到Hypervisor的中断和异常；

 

- `VHE`

- `VHE: Virtualization Host Extensions`，用于支持Host OS运行在EL2上，Hypervisor和Host OS都运行在EL2，可以减少Context切换带来的开销；
- 目前`Cortex-A55, Cortex-A75, Cortex-A76`支持VHE，其中VHE的控制是通过`HCR_EL2`寄存器的操作来实现的；

 

再补充一个知识点：

- Host如果运行在EL1时，可以通过`HVC（Hypervisor Call）`指令，主动trap到EL2中，从而由Hypervisor来接管；
- Guest OS可以配置成当有中断或异常时trap到EL2中，在中断或异常产生时，trap到EL2中，从而由Hypervisor来接管；
- EL2可以通过`eret`指令，退回到EL1；

本文的讨论基于`Non-VHE`系统。

## 2.1 GIC虚拟化支持

GICv2硬件支持虚拟化，来一张旧图：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200220232-1786287831.png)

先看一下物理GIC的功能模块：

- GIC分成两部分：`Distributor`和`CPU Interfaces`，`Distributor`和`CPU Interfaces`都是通过MMIO的方式来进行访问；
- `Distributor`用于配置GIC，比如中断的enable与disable，SMP中的IPI中断、CPU affinity，优先级处理等；
- `CPU Interfaces`用于连接CPU，进行中断的ACK（Acknowledge）以及EOI（End-Of-Interrupt）信号处理等，比如当CPU收到中断信号时，会通过`CPU Interfaces`进行ACK回应，并且在处理完中断后写入EOI寄存器，而在写EOI之前将不再收到该中断；

简化图如下：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200241971-808129631.png)

GICv2，提供了硬件上的虚拟化支持，也就是虚拟GIC（VGIC），从而中断的接收不需要通过Hypervisor来软件模拟：

- 针对每个vCPU，VGIC引入了`VGIC CPU Interfaces`和对应的Hypervisor控制接口；
- 可以通过写Hypervisor控制接口中的LR（List Register）寄存器来产生虚拟中断，`VGIC CPU Interface`会将虚拟中断信号送入到Guest中；
- `VGIC CPU Interface`支持`ACK`和`EOI`，因此这些操作也不需要trap到Hypervisor中来通过软件进行模拟，也减少了CPU接收中断的overhead；
- `Distributor`仍然需要trap到Hypervisor中来进行软件模拟，比如，当某个vCPU需要发送虚拟IPI到另一个vCPU时，此时是需要`Distributor`来辅助完成功能的，这个过程就需要trap到Hypervisor；

## 2.2 虚拟中断产生流程

本文开始提到的三种中断信号源，如下图所示：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200253691-1438854555.png)

- ①：物理外设产生虚拟中断流程：

- 外设中断信号（Hypervisor已经将其配置成虚拟中断）到达GIC；
- GIC Distributor将该物理IRQ发送至CPU；
- CPU trap到Hyp模式，此时将会退出Guest OS的运行，并返回到Host OS；
- Host OS将响应该物理中断，也就是Host OS驱动响应外设中断信号；
- Hypervisor往`List Register`写入虚拟中断，Virtual CPU interface将virtual irq信号发送至vCPU；
- CPU将处理该异常，Guest OS会从Virtual CPU Interface读取中断状态进行响应；

 

- ②：虚拟外设产生虚拟中断流程：

- Qemu模拟外设，通过`irqfd`来触发`Hypervisor`进行中断注入；
- Hypervisor往`List Register`写入虚拟中断，Virtual CPU interface将virtual irq信号发送至vCPU；
- CPU将处理该异常，Guest OS会从Virtual CPU Interface读取中断状态进行响应；

 

- ③：vCPU IPI中断流程：

- Guest OS访问Virtual Distributor，触发异常，trap到Hypervisor；
- Hypervisor进行IO异常响应，并最终将虚拟中断写入到List Register中，Virtual CPU interface将virtual irq信号发送至vCPU；
- CPU将处理该异常，Guest OS会从Virtual CPU Interface读取中断状态进行响应；

 

上述描述的流程，实际中需要和虚拟外设去交互，包括虚拟外设框架（比如`VFIO`）等，而本文只是从中断的角度来分析，省去了外设部分。

 

理论部分讲完了，下边就开始从源码中去印证理论了。

# 3. 软件实现流程

## 3.1 VGIC初始化

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200307766-1808434784.png)

- `kvm_init`为总入口，进入`vgic_v2_probe`函数，完成GICv2的初始化操作，此处还会跟`GICV2`内核中的驱动交互，去获取`gic_kvm_info`信息，主要包括基地址信息等，便于后续操作中去进行配置操作；
- 从蓝色部分的函数调用可以看出，初始化完成后，会注册一个`kvm_device_ops`的操作函数集，以便响应用户层的`ioctl`操作；
- 用户层调用`ioctl(vm_fd, KVM_CREATE_DEVICE, 0)`，最终将调用`vgic_create`函数，完成VGIC设备的创建，在该创建函数中也会注册`kvm_device_fops`操作函数集，用于设备属性的设置和获取；
- 用户层通过`ioctl(dev_fd, KVM_SET_DEVICE_ATTR, 0)/ioctl(dev_fd, KVM_GET_DEVICE_ATTR, 0)`来进行属性的设置和获取，最终也会调用`vgic_v2_set_attr/vgic_v2_get_attr`，以便完成对VGIC的设置；

## 3.2 物理外设产生中断

假设你已经看过之前CPU的虚拟化文章了，按照惯例，先上图：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200318540-1278313911.png)

- 先来一个先决条件： `HCR_EL2.IMO`设置为1，所有的IRQ都将trap到Hyp模式，因此，当Guest OS运行在vCPU上时，物理外设触发中断信号时，此时将切换到EL2，然后执行`el1_irq`；
- 在Host中，当用户态通过`KVM_RUN`控制vCPU运行时，在`kvm_call_hyp_ret`将触发Exception Level的切换，切换到Hyp模式并调用`__kvm_vcpu_run_nvhe`，在该函数中`__guest_enter`将切换到Guest OS的context，并最终通过`eret`返回到EL1，Guest OS正式开始运行；
- 中断触发后`el1_irq`将执行`__guest_exit`，这个过程将进行Context切换，也就是跳转到Host切入Guest的那个点，恢复Host的执行。注意了，这里边有个点很迷惑，`el1_irq`和`__guest_exit`的执行都是在EL2中，而Host在EL1执行，之前我一直没有找到`eret`来进行Exception Level的切换，最终发现原来是`kvm_call_hyp_ret`调用时，去异常向量表中找到对应的执行函数，实际会调用`do_el2_call`，在该函数中完成了Exception Level的切换，最终回到了EL1；
- 切回到Host中时，当`local_irq_enable`打开中断后，物理pending的中断就可以被Host欢快的响应了；

 

那虚拟中断是什么时候注入的呢？没错，图中的`kvm_vgic_flush_hwstate`会将虚拟中断注入，并且在`__guest_enter`切换回Guest OS时进行响应：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200329434-105732900.png)

- `vgic_cpu`结构体中的`ap_list_head`链表用于存放Active和Pending状态的中断，这也就是命名为`ap_list_head`的原因；
- `kvm_vgic_flush_hwstate`函数会遍历`ap_list_head`中的中断信息，并填入到`vgic_lr`数组中，最终会通过`vgic_restore_state`函数将数组中的内容更新到GIC的硬件中，也就完成了中断的注入了，当`__guest_enter`执行后，切换到Guest OS，便可以响应虚拟中断了；
- 当从Guest OS退出后，此时需要调用`kvm_vgic_sync_hwstate`，这个操作相当于`kvm_vgic_flush_hwstate`的逆操作，将硬件信息进行保存，并对短期内不会处理的中断进行剔除；

## 3.3 虚拟外设产生中断

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200341899-369635802.png)

- irqfd提供了一种机制用于注入虚拟中断，而这个中断源可以来自虚拟外设；
- irqfd是基于eventfd的机制来实现的，用于用户态与内核态，以及内核态之间的事件通知；
- 事件源可以是虚拟设备，比如VFIO框架等，这个模块还没有去深入了解过，不敢妄言，后续系列会跟进；

 

软件流程如下图：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200350501-1651907069.png)

- 初始化的操作包括两部分：1）设置Routing entry（【a】vgic_init初始化的时候创建默认的entry；【b】：用户层通过KVM_SET_GSI_ROUTING来设置）；2）设置irqfd；
- 初始化设置完成后，系统可以随时响应事件触发了，当事件源触发时，将调度到`irqfd_inject`函数；
- `irqfd_inject`函数完成虚拟中断的注入操作，在该函数中会去回调`set`函数，而`set`函数是在`Routing entry`初始化的时候设置好的；
- 实际的注入操作在`vgic_irqfd_set_irq`函数中完成；
- `kvm_vcpu_kick`函数，将Guest OS切回到Host OS，中断注入后再切回到Guest OS就可以响应了；

## 3.4 vCPU IPI

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200401494-1626123674.png)

- Host对VGIC的`Distributor`进行了模拟，当Guest尝试访问`VGIC Distributor`时，将触发异常操作，trap到Hyp模式；
- Hypervisor对异常进行处理，完成写入操作，并最终切回到Guest OS进行响应；
- 简单来说，Hypervisor就是要对中断进行管理，没错，就是这么强势；

 

软件流程如下：

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200412284-18368414.png)

- 上层调用`ioctl(vcpu_fd, KVM_RUN, 0)`时，最终将调用到`vgic_register_dist_iodev`函数，该函数完成的作用就是将VGIC的`Distributor`注册为IO设备，以便给Guest OS来进行访问；
- `vgic_register_dist_iodev`分为两个功能模块：1）初始化`struct vgic_registers_region`结构体字段和操作函数集；2）注册为MMIO总线设备；
- `struct vgic_registers_region`定义好了不同的寄存器区域，以及相应的读写函数，`vgic_v2_dist_registers`数组最终会提供给`dispach_mmio_read/dispach_mmio_write`函数来查询与调用；
- 当Guest OS访问`Distributor`时，触发IO异常并切换回Host进行处理，`io_mem_abort`会根据总线的类型（MMIO）去查找到对应的读写函数进行操作，也就是图中对应的`dispatch_mmio_read/dispach_mmio_write`函数，最终完成寄存器区域的读写；
- 图中的红色线，代表的就是异常处理的执行流，可以说是一目了然了。

 

耗时耗力耗心血的一篇文章终于写完了，ARMv8 GICv2中断虚拟化的总体框架和流程应该算是理顺了，全网相关主题的文章并不多，希望能给带来点帮助吧。

如果对你有用的话，在看，分享，打赏三连吧。

# 参考

`《arm_gic_architecture_specification》`

`《ARM_Interrupt_Virtualization》`

`《VM-Support-ARM》`

`《CoreLink GIC-400 Generic Interrupt Controller》`

`《Virtualization in the ARM Architecture》`

`https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/commit/?id=721eecbf4fe995ca94a9edec0c9843b1cc0eaaf3`

欢迎关注个人公众号，不定期更新内核相关技术文章

![](https://img2020.cnblogs.com/blog/1771657/202011/1771657-20201121200444299-463596231.jpg)

    
  作者：[LoyenWang](https://www.cnblogs.com/LoyenWang/)

  出处：https://www.cnblogs.com/LoyenWang/

  公众号：LoyenWang

  版权：本文版权归作者和博客园共有

  转载：欢迎转载，但未经作者同意，必须保留此段声明；必须在文章中给出原文连接；否则必究法律责任

    
    
    <div
