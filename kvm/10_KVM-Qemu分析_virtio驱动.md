# 背景

- `Read the fucking source code!`  --By 鲁迅
- `A picture is worth a thousand words.` --By 高尔基

说明：

- KVM版本：5.9.1
- QEMU版本：5.0.0
- 工具：Source Insight 3.5， Visio
- 文章同步在博客园：`https://www.cnblogs.com/LoyenWang/`

# 1. 概述

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230011372-860838932.png)

- 前篇文章讲完了Qemu中如何来创建Virtio Device，本文将围绕Guest OS中的Virtio Driver来展开；

看一下Guest OS（Linux）中的Virtio框架高层架构图：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230018412-1701114651.png)

- 核心模块为virtio和virtqueue，其他高层的驱动都是基于核心模块之上构建的；
- 显然，本文会延续这个系列，继续分析virtio-net驱动，重心在整体流程和框架上，细节不表；
- virtio-net，又是一个virtio设备，又是一个PCI设备，那么驱动会怎么组织呢？带着问题上路吧。

# 2. 数据结构

说到驱动怎么能不提linux设备驱动模型呢，感兴趣的朋友可以去看看PCI系列分析文章，简单来说就是内核创建总线用于挂载设备，总线负责设备与驱动的匹配。Linux内核创建了一个virtio bus：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230026389-1415523459.png)

- virtio设备和virtio驱动，通过`virtio_device_id`来匹配，而这个都是在virtio规范中定义好的；
- `virtio_device`结构中有一个`struct virtio_config_ops`，函数集由驱动来进行指定，用于操作具体的设备；

本文描述的virtio-net驱动，既是一个virtio设备，也是一个pci设备，在内核中通过结构体`struct virtio_pci_device`来组织：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230035773-340142374.png)

- 该结构体中维护了几个IO区域：`Common, ISR, Device, Notify`，用于获取virtio设备的各种信息，这个也是由virtio规范决定的；
- 通常来说一个virtio设备，由以下几个部分组成：

- Device status field
- Feature bits
- Notifications
- Device Configuration space
- One or more virtqueues

- 从结构体看，它用于充当pci设备和virtio设备的纽带，后续也会在probe函数中针对不同的部分进行对应的初始化；

以总线的匹配视角来看就是这样子的：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230048521-644906865.png)

# 3. 流程分析

## 3.1 virtio总线创建

先看一下virtio总线的创建，virtio bus当然也算是基建了：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230056465-1815162121.png)

- `bus_register`注册virtio总线，总线负责匹配，在匹配成功后调用通用的`virtio_dev_probe`函数；
- 千里姻缘一线牵，当Virtio的ID号能对上时，就会触发驱动探测，所以什么时候进行设备注册呢？

## 3.2 virtio驱动调用流程

详细的细节，建议阅读之前PCI驱动系列的分析文章，下边罗列关键部分：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230103153-2040554903.png)

- virtio-net设备通过挂在pci总线上，系统在PCI子系统初始化时会去枚举所有的设备，并将枚举的设备注册进系统；
- 系统在匹配上之后，调用设备的驱动；

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230400403-1000958582.png)

- PCI设备根据Vendor ID来匹配驱动；
- virtio规范中规定基于PCI的virtio设备，Vendor ID号为：`0x1AF4`，因此最终调用的驱动入口为`virtio_pci_probe`；

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230417971-437424297.png)

- 在probe函数中分配`struct virtio_pci_device`结构，前文中也提到过它负责将virtio设备和pci设备绑定到一起，最终会在两个设备驱动的probe函数中完成整体结构的初始化，也就是`virtio_pci_probe`完成一部分，实际的virtio设备驱动中完成一部分；
- `virtio_pci_modern_probe`：该函数的内容就与virtio规范紧密相关了，简单来说，virtio设备都会按照规范填充common、device、isr、notification等功能部分，而`virtio_pci_modern_probe`函数通过`virtio_pci_find_capability`去获取对应的能力，并且通过`map_capability`完成IO空间的映射；
- `virtio_pci_probe`中还设置了`virtio_pci_config_ops`操作函数集，并传递给virtio驱动，在驱动中调用这些回调函数来操作virtio设备；
- `register_virtio_device`：向系统注册virtio设备，从而也就触发了virtio总线的匹配操作，最终调用`virtio_dev_probe`函数；
- `virtio_dev_probe`函数中按照virtio规范分阶段设置不同的状态、获取virtio设备的feature等，并最终调用实际设备的驱动程序了；

At last，终于摸到本文要说的virtio-net的驱动的入口了，当然，文章也要戛然而止了。

整体执行流程及框架应该清楚了，细节就留给大家了，待续。。。

# 参考

`https://developer.ibm.com/technologies/linux/articles/l-virtio/`

`Virtual I/O Device (VIRTIO) Version 1.1`

欢迎关注个人公众号，不定期更新技术文章。

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210224230213154-275255868.jpg)

    
  作者：[LoyenWang](https://www.cnblogs.com/LoyenWang/)

  出处：https://www.cnblogs.com/LoyenWang/

  公众号：LoyenWang

  版权：本文版权归作者和博客园共有

  转载：欢迎转载，但未经作者同意，必须保留此段声明；必须在文章中给出原文连接；否则必究法律责任

    
    
    <div
