# 背景

- `Read the fucking source code!`  --By 鲁迅
- `A picture is worth a thousand words.` --By 高尔基

说明：

- KVM版本：5.9.1
- QEMU版本：5.0.0
- 工具：Source Insight 3.5， Visio
- 文章同步在博客园：`https://www.cnblogs.com/LoyenWang/`

# 1. 概述

先从操作系统的角度来看一下timer的作用吧：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235145167-121582686.png)

通过timer的中断，OS实现的功能包括但不局限于上图：

- 定时器的维护，包括用户态和内核态，当指定时间段过去后触发事件操作，比如IO操作注册的超时定时器等；
- 更新系统的运行时间、wall time等，此外还保存当前的时间和日期，以便能通过`time()`等接口返回给用户程序，内核中也可以利用其作为文件和网络包的时间戳；
- 调度器在调度任务分配给CPU时，也会去对task的运行时间进行统计计算，比如CFS调度，Round-Robin调度等；
- 资源使用统计，比如系统负载的记录等，此外用户使用top命令也能进行查看；

 

timer就像是系统的脉搏，重要性不言而喻。ARMv8架构处理器提供了一个Generic Timer，与GIC类似，Generic Timer在硬件上也支持了虚拟化，减少了软件模拟带来的overhead。

 

本文将围绕着ARMv8的timer虚拟化来展开。

# 2. ARMv8 Timer虚拟化

## 2.1 Generic Timer

看一下ARMv8架构下的CPU内部图：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235155674-1601941220.png)

- `Generic Timer`提供了一个系统计数器，用于测量真实时间的消逝；
- `Generic Timer`支持虚拟计数器，用于测量虚拟的时间消逝，一个虚拟计数器对应一个虚拟机；
- `Timer`可以在特定的时间消逝后触发事件，可以设置成`count-up`计数或者`count-down`计数；

来看一下`Generic Timer`的简图：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235203044-1599197060.png)

或者这个：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235208470-1804165099.png)

- `System Counter`位于`Always-on`电源域，以固定频率进行系统计数的增加，`System Counter`的值会广播给系统中的所有核，所有核也能有一个共同的基准了，`System Counter`的频率范围为1-50MHZ，系统计数值的位宽在56-64bit之间；
- 每个核有一组timer，这些timer都是一些比较器，与`System Counter`广播过来的系统计数值进行比较，软件可以配置固定时间消逝后触发中断或者触发事件；
- 每个核提供的timer包括：1）`EL1 Physical timer`；2）`EL1 Virtual timer`；此外还有在EL2和EL3下提供的timer，具体取决于ARMv8的版本；
- 有两种方式可以配置和使用一个timer：1）`CVAL(comparatoer)`寄存器，通过设置比较器的值，当`System Count >= CVAL`时满足触发条件；2）`TVAL`寄存器，设置`TVAL`寄存器值后，比较器的值`CVAL = TVAL + System Counter`，当`System Count >= CVAL`时满足触发条件，`TVAL`是一个有符号数，当递减到0时还会继续递减，因此可以记录timer是在多久之前触发的；
- timer的中断是私有中断`PPI`，其中`EL1 Physical Timer`的中断号为30，`EL1 Virtual Timer`的中断号为27；
- timer可以配置成触发事件产生，当CPU通过`WFE`进入低功耗状态时，除了使用`SEV`指令唤醒外，还可以通过`Generic Timer`产生的事件流来唤醒；

## 2.2 虚拟化支持

`Generic Timer`的虚拟化如下图：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235216413-90333420.png)

- 虚拟的timer，同样也有一个count值，计算关系：`Virtual Count = Physical Count - <offset>`，其中offset的值放置在`CNTVOFF`寄存器中，`CNTPCT/CNTVCT`分别用于记录当前物理/虚拟的count值；
- 如果EL2没有实现，则将offset设置为0,，物理的计数器和虚拟的计数器值相等；
- `Physical Timer`直接与`System counter`进行比较，`Virtual Timer`在`Physical Timer`的基础上再减去一个偏移；
- Hypervisor负责为当前调度运行的vCPU指定对应的偏移，这种方式使得虚拟时间只会覆盖vCPU实际运行的那部分时间；

示例如下：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235232851-53486309.png)

- 6ms的时间段里，每个vCPU运行3ms，Hypervisor可以使用偏移寄存器来将vCPU的时间调整为其实际的运行时间；

# 3. 流程分析

## 3.1 初始化

先简单看一下数据结构吧：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235240939-617714506.png)

- 在ARMv8虚拟化中，使用`struct arch_timer_cpu`来描述`Generic Timer`，从结构体中也能很清晰的看到层次结构，创建vcpu时，需要去初始化vcpu架构相关的字段，其中就包含了timer；
- `struct arch_timer_cpu`包含了两个timer，分别对应物理timer和虚拟timer，此外还有一个高精度定时器，用于Guest处在非运行时的计时工作；
- `struct arch_timer_context`用于描述一个timer需要的内容，包括了几个字段用于存储寄存器的值，另外还描述了中断相关的信息；

初始化分为两部分：

- 架构相关的初始化，针对所有的CPU，在kvm初始化时设置：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235248193-159181159.png)

- `kvm_timer_hyp_init`函数完成相应的初始化工作；
- `arch_timer_get_kvm_info`从Host Timer驱动中去获取信息，主要包括了虚拟中断号和物理中断号，以及timecounter信息等；
- vtimer中断设置包括：判断中断的触发方式（只支持电平触发），注册中断处理函数`kvm_arch_timer_handler`，设置中断到vcpu的affinity等；
- ptimer中断设置与vtimer中断设置一样，同时它的中断处理函数也是`kvm_arch_timer_handler`，该处理函数也比较简单，最终会调用`kvm_vgic_inject_irq`函数来完成虚拟中断注入给vcpu；
- `cpuhp_setup_state`用来设置CPU热插拔时timer的响应处理，而在`kvm_timer_starting_cpu/kvm_timer_dying_cpu`两个函数中实现的操作就是中断的打开和关闭，仅此而已；

- vcpu相关的初始化，在创建vcpu时进行初始化设置：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235255363-2105252369.png)

- 针对vcpu的timer相关初始化比较简单，回到上边那张数据结构图看一眼就明白了，所有的初始化工作都围绕着`struct arch_timer_cpu`结构体；
- `vcpu_timer`：用于获取vcpu包含的`struct arch_timer_cpu`结构；
- `vcpu_vtimer/vcpu_ptimer`：用于获取`struct arch_timer_cpu`结构体中的`struct arch_timer_context`，分别对应vtimer和ptimer；
- `update_vtimer_cntvoff`：用于更新vtimer中的cntvoff值，读取物理timer的count值，更新VM中所有vcpu的cntvoff值；
- `hrtimer_init`：用于初始化高精度定时器，包含有三个，`struct arch_timer_cpu`结构中有一个`bg_timer`，vtimer和ptimer所对应的`struct arch_timer_context`中分别对应一个；
- `kvm_bg_timer_expire`：`bg_timer`的到期执行函数，当需要调用`kvm_vcpu_block`让vcpu睡眠时，需要先启动`bg_timer`，`bg_timer`到期时再将vcpu唤醒；
- `kvm_hrtimer_expire`：vtimer和ptimer的到期执行函数，最终通过调用`kvm_timer_update_irq`来向vcpu注入中断；

## 3.2 用户层访问

可以从用户态对vtimer进行读写操作，比如Qemu中，流程如下：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235302190-2105625971.png)

- 用户态创建完vcpu后，可以通过vcpu的文件描述符来进行寄存器的读写操作；
- 以ARM为例，ioctl通过`KVM_SET_ONE_REG/KVM_GET_ONE_REG`将最终触发寄存器的读写；
- 如果操作的是timer的相关寄存器，则通过`kvm_arm_timer_set_reg`和`kvm_arm_timer_get_reg`来完成；
- 读写的寄存器包括虚拟timer的CTL/CVAL，以及物理timer的CTL/CVAL等；

## 3.3 Guest访问

Guest对Timer的访问，涉及到系统寄存器的读写，将触发异常并Trap到Hyp进行处理，流程如下：

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235311000-378032277.png)

- Guest OS访问系统寄存器时，Trap到Hypervisor进行处理；
- Hypervisor对异常退出进行处理，如果发现是访问系统寄存器造成的异常，则调用`kvm_handle_sys_reg`来处理；
- `kvm_handle_sys_reg`：调用`emulate_sys_reg`来对系统寄存器进行模拟，在该函数中首先会查找访问的是哪一个寄存器，然后再去调用相应的回调函数；
- kvm中维护了`struct sys_reg_desc sys_reg_descs[]`系统寄存器的描述表，其中`struct sys_reg_desc`结构体中包含了对该寄存器操作的函数指针，用于指向最终的操作函数，比如针对Timer的`kvm_arm_timer_write_sysreg/kvm_arm_timer_read_sysreg`读写操作函数；
- Timer的读写操作函数，主要在`kvm_arm_timer_read/kvm_arm_timer_write`中完成，实现的功能就是根据物理的count值和offset来计算等；

 

timer的虚拟化还是比较简单，就此打住了。

### PS：

按计划，接下里该写IO虚拟化了，然后紧接着Qemu的源码相关分析。不过，在写IO虚拟化之前，我会先去讲一下PCIe的驱动框架，甚至可能还会去研究一下网络，who knows，反正这些也都是IO相关。

`Any way，I will be back soon!`

# 参考

`《AArch64 Programmer's Guides Generic Timer》`

`《Arm Architecture Reference Manual》`

欢迎关注个人公众号，不定期更新内核相关技术文章

![](https://img2020.cnblogs.com/blog/1771657/202012/1771657-20201205235402372-358763516.jpg)

    
  作者：[LoyenWang](https://www.cnblogs.com/LoyenWang/)

  出处：https://www.cnblogs.com/LoyenWang/

  公众号：LoyenWang

  版权：本文版权归作者和博客园共有

  转载：欢迎转载，但未经作者同意，必须保留此段声明；必须在文章中给出原文连接；否则必究法律责任

    
    
    <div
