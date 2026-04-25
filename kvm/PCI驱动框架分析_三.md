# 背 景

- `Read the fucking source code!`  --By 鲁迅
- `A picture is worth a thousand words.` --By 高尔基

说明：

- Kernel版本：4.14
- ARM64处理器
- 使用工具：Source Insight 3.5， Visio

# 1. 概述

先回顾一下PCIe的架构图：

![](https://img2020.cnblogs.com/blog/1771657/202101/1771657-20210109185706644-1642038746.png)

- 本文将讲PCIe Host的驱动，对应为`Root Complex`部分，相当于PCI的`Host Bridge`部分；
- 本文会选择Xilinx的`nwl-pcie`来进行分析；
- 驱动的编写整体偏简单，往现有的框架上套就可以了，因此不会花太多笔墨，点到为止；

# 2. 流程分析

- 但凡涉及到驱动的分析，都离不开驱动模型的介绍，驱动模型的实现让具体的驱动开发变得更容易；
- 所以，还是回顾一下上篇文章提到的驱动模型：Linux内核建立了一个统一的设备模型，分别采用总线、设备、驱动三者进行抽象，其中设备与驱动都挂在总线上，当有新的设备注册或者新的驱动注册时，总线会去进行匹配操作（`match`函数），当发现驱动与设备能进行匹配时，就会执行probe函数的操作；

![](https://img2020.cnblogs.com/blog/1771657/202101/1771657-20210109185741192-1760974470.png)

- `《Linux PCI驱动框架分析（二）》`中提到过PCI设备、PCI总线和PCI驱动的创建，PCI设备和PCI驱动挂接在PCI总线上，这个理解很直观。针对PCIe的控制器来说，同样遵循设备、总线、驱动的匹配模型，不过这里的总线是由虚拟总线`platform`总线来替代，相应的设备和驱动分别为`platform_device`和`platform_driver`；

那么问题来了，`platform_device`是在什么时候创建的呢？那就不得不提到`Device Tree`设备树了。

## 2.1 Device Tree

- 设备树用于描述硬件的信息，包含节点各类属性，在dts文件中定义，最终会被编译成dtb文件加载到内存中；
- 内核会在启动过程中去解析dtb文件，解析成`device_node`描述的`Device Tree`；
- 根据`device_node`节点，创建`platform_device`结构，并最终注册进系统，这个也就是PCIe Host设备的创建过程；

我们看看PCIe Host的设备树内容：

```
pcie: pcie@fd0e0000 {
	compatible = "xlnx,nwl-pcie-2.11";
	status = "disabled";
	#address-cells = <3>;
	#size-cells = <2>;
	#interrupt-cells = <1>;
	msi-controller;
	device_type = "pci";
    
	interrupt-parent = <&gic>;
	interrupts = <0 118 4>,
		     <0 117 4>,
		     <0 116 4>,
		     <0 115 4>,	/* MSI_1 [63...32] */
		     <0 114 4>;	/* MSI_0 [31...0] */
	interrupt-names = "misc", "dummy", "intx", "msi1", "msi0";
	msi-parent = <&pcie>;
    
	reg = <0x0 0xfd0e0000 0x0 0x1000>,
	      <0x0 0xfd480000 0x0 0x1000>,
	      <0x80 0x00000000 0x0 0x1000000>;
	reg-names = "breg", "pcireg", "cfg";
	ranges = <0x02000000 0x00000000 0xe0000000 0x00000000 0xe0000000 0x00000000 0x10000000	/* non-prefetchable memory */
		  0x43000000 0x00000006 0x00000000 0x00000006 0x00000000 0x00000002 0x00000000>;/* prefetchable memory */
	bus-range = <0x00 0xff>;
    
	interrupt-map-mask = <0x0 0x0 0x0 0x7>;
	interrupt-map =     <0x0 0x0 0x0 0x1 &pcie_intc 0x1>,
			    <0x0 0x0 0x0 0x2 &pcie_intc 0x2>,
			    <0x0 0x0 0x0 0x3 &pcie_intc 0x3>,
			    <0x0 0x0 0x0 0x4 &pcie_intc 0x4>;
    
	pcie_intc: legacy-interrupt-controller {
		interrupt-controller;
		#address-cells = <0>;
		#interrupt-cells = <1>;
	};
};

```

关键字段描述如下：

- `compatible`：用于匹配PCIe Host驱动；
- `msi-controller`：表示是一个MSI（`Message Signaled Interrupt`）控制器节点，这里需要注意的是，有的SoC中断控制器使用的是GICv2版本，而GICv2并不支持MSI，所以会导致该功能的缺失；
- `device-type`：必须是`"pci"`；
- `interrupts`：包含NWL PCIe控制器的中断号；
- `interrupts-name`：`msi1, msi0`用于MSI中断，`intx`用于旧式中断，与`interrupts`中的中断号对应；
- `reg`：包含用于访问PCIe控制器操作的寄存器物理地址和大小；
- `reg-name`：分别表示`Bridge registers`，`PCIe Controller registers`， `Configuration space region`，与`reg`中的值对应；
- `ranges`：PCIe地址空间转换到CPU的地址空间中的范围；
- `bus-range`：PCIe总线的起始范围；
- `interrupt-map-mask`和`interrupt-map`：标准PCI属性，用于定义PCI接口到中断号的映射；
- `legacy-interrupt-controller`：旧式的中断控制器；

## 2.2 probe流程

- 系统会根据dtb文件创建对应的platform_device并进行注册；
- 当驱动与设备通过`compatible`字段匹配上后，会调用probe函数，也就是`nwl_pcie_probe`；

![](https://img2020.cnblogs.com/blog/1771657/202101/1771657-20210109185820984-571538081.png)

看一下`nwl_pcie_probe`函数：

![](https://img2020.cnblogs.com/blog/1771657/202101/1771657-20210109185829006-646052988.png)

- 通常probe函数都是进行一些初始化操作和注册操作：

- 初始化包括：数据结构的初始化以及设备的初始化等，设备的初始化则需要获取硬件的信息（比如寄存器基地址，长度，中断号等），这些信息都从DTS而来；
- 注册操作主要是包含中断处理函数的注册，以及通常的设备文件注册等;

 

- 针对PCI控制器的驱动，核心的流程是需要分配并初始化一个`pci_host_bridge`结构，最终通过这个`bridge`去枚举PCI总线上的所有设备；
- `devm_pci_alloc_host_bridge`：分配并初始化一个基础的`pci_hsot_bridge`结构；
- `nwl_pcie_parse_dt`：获取DTS中的寄存器信息及中断信息，并通过`irq_set_chained_handler_and_data`设置`intx`中断号对应的中断处理函数，该处理函数用于中断的级联；
- `nwl_pcie_bridge_init`：硬件的Controller一堆设置，这部分需要去查阅Spec，了解硬件工作的细节。此外，通过`devm_request_irq`注册`misc`中断号对应的中断处理函数，该处理函数用于控制器自身状态的处理；
- `pci_parse_request_of_pci_ranges`：用于解析PCI总线的总线范围和总线上的地址范围，也就是CPU能看到的地址区域；
- `nwl_pcie_init_irq_domain`和`mwl_pcie_enable_msi`与中断级联相关，下个小节介绍；
- `pci_scan_root_bus_bridge`：对总线上的设备进行扫描枚举，这个流程在`Linux PCI驱动框架分析（二）`中分析过。`brdige`结构体中的`pci_ops`字段，用于指向PCI的读写操作函数集，当具体扫描到设备要读写配置空间时，调用的就是这个函数，由具体的Controller驱动实现；

## 2.3 中断处理

PCIe控制器，通过PCIe总线连接各种设备，因此它本身充当一个中断控制器，级联到上一层的中断控制器（比如GIC），如下图：

![](https://img2020.cnblogs.com/blog/1771657/202101/1771657-20210109185902554-698495300.png)

- PCIe总线支持两种中断的处理方式：

- Legacy Interrupt：总线提供`INTA#, INTB#, INTC#, INTD#`四根中断信号，PCI设备借助这四根信号使用电平触发方式提交中断请求；
- MSI(`Message Signaled Interrupt`) Interrupt：基于消息机制的中断，也就是往一个指定地址写入特定消息，从而触发一个中断；

针对两种处理方式，`NWL PCIe`驱动中，实现了两个`irq_chip`，也就是两种方式的中断控制器：

![](https://img2020.cnblogs.com/blog/1771657/202101/1771657-20210109185914394-919535159.png)

- `irq_domain`对应一个中断控制器（`irq_chip`），`irq_domain`负责将硬件中断号映射到虚拟中断号上；
- 来一张旧图吧，具体文章可以去参考中断子系统相关文章；

![](https://img2020.cnblogs.com/blog/1771657/202101/1771657-20210109185927544-1567201778.png)

再来看一下`nwl_pcie_enable_msi`函数：

![](https://img2020.cnblogs.com/blog/1771657/202101/1771657-20210109185939530-1889974159.png)

- 在该函数中主要完成的工作就是设置级联的中断处理函数，级联的中断处理函数中最终会去调用具体的设备的中断处理函数；

 

所以，稍微汇总一下，作为两种不同的中断处理方式，套路都是一样的，都是创建`irq_chip`中断控制器，为该中断控制器添加`irq_domain`，具体设备的中断响应流程如下：

- 设备连接在PCI总线上，触发中断时，通过PCIe控制器充当的中断控制器路由到上一级控制器，最终路由到CPU；
- CPU在处理PCIe控制器的中断时，调用它的中断处理函数，也就是上文中提到过的`nwl_pcie_leg_handler`，`nwl_pcie_msi_handler_high`，和`nwl_pcie_leg_handler_low`；
- 在级联的中断处理函数中，调用`chained_irq_enter`进入中断级联处理；
- 调用`irq_find_mapping`找到具体的PCIe设备的中断号；
- 调用`generic_handle_irq`触发具体的PCIe设备的中断处理函数执行；
- 调用`chained_irq_exit`退出中断级联的处理；

## 2.4 总结

- PCIe控制器驱动，各家的IP实现不一样，驱动的差异可能会很大，单独分析一个驱动毕竟只是个例，应该去掌握背后的通用框架；
- 各类驱动，大体都是硬件初始化配置，资源申请注册，核心是处理与硬件的交互（一般就是中断的处理），如果需要用户来交互的，则还需要注册设备文件，实现一堆`file_operation`操作函数集；
- 好吧，我个人不太喜欢分析某个驱动，草草收场了；

下篇开始，继续回归到虚拟化，期待一下吧。

# 参考

`Documentation/devicetree/bindings/pci/xlinx-nwl-pcie.txt`

欢迎关注个人公众号，不定期分享技术文章：

![](https://img2020.cnblogs.com/blog/1771657/202101/1771657-20210109190018964-49593240.jpg)

    
  作者：[LoyenWang](https://www.cnblogs.com/LoyenWang/)

  出处：https://www.cnblogs.com/LoyenWang/

  公众号：LoyenWang

  版权：本文版权归作者和博客园共有

  转载：欢迎转载，但未经作者同意，必须保留此段声明；必须在文章中给出原文连接；否则必究法律责任

    
    
    <div
