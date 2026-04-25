# 背景

- `Read the fucking source code!`  --By 鲁迅
- `A picture is worth a thousand words.` --By 高尔基

说明：

- KVM版本：5.9.1
- QEMU版本：5.0.0
- 工具：Source Insight 3.5， Visio
- 文章同步在博客园：`https://www.cnblogs.com/LoyenWang/`

新的一年， 大家牛起来！

祝小姐姐们：

落雁沉鱼 兰质蕙心 明眸皓齿 螓首蛾眉 天生丽质 天香国色 杏脸桃腮 煦色韶光 涎玉沫珠  宜嗔宜喜 远山芙蓉 艳色绝世 余霞成绮  阿娇金屋 逞娇呈美  国色天香 花颜月貌 绝色佳人 暗香盈袖 闭月羞花  倾国倾城 温婉娴淑 千娇百媚 仪态万千...

祝男的：

新年好。

# 1. 概述

先来张图：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002146556-1295538181.png)

- 图中罗列了四个关键模块：`Virtio Device`、`Virtio Driver`、`Virtqueue`、`Notification（eventfd/irqfd）`；
- `Virtio Driver`：前端部分，处理用户请求，并将I/O请求转移到后端；
- `Virtio Device`：后端部分，由Qemu来实现，接收前端的I/O请求，并通过物理设备进行I/O操作；
- `Virtqueue`：中间层部分，用于数据的传输；
- `Notification`：交互方式，用于异步事件的通知；

 

想在一篇文章中写完这四个模块，有点`too yong too simple`，所以，看起来又是一个系列文章了。

本文先从Qemu侧的virtio device入手，我会选择从一个实际的设备来阐述，没错，还是上篇文章中提到的网络设备。

# 2. 流程分析

在Qemu的网卡虚拟化时，通常会创建一个虚拟网卡前端和虚拟网卡后端，如下图：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002157164-967550439.png)

- 在虚拟机创建的时候指定参数：`-netdev tap, id = tap0， -device virtio-net-pci, netdev=tap0`；
- 创建一个`Tap`网卡后端设备；
- 创建一个`Virtio-Net`网卡前端设备；
- 网卡前端设备和后端设备进行交互，最终与Host的驱动完成数据的收发；

全文围绕着`Tap`设备的创建和`Virtio-Net`设备的创建展开。

入口流程如下：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002204631-1421245348.png)

- Qemu的代码阅读起来还是比较费劲的，各种盘根错节，里边充斥着面向对象的思想，先给自己挖个坑，后续会专题研究的，`this is for you, you have my words.`;
- 图中与本文相关的有三个模块：1）模块初始化；2）网络设备初始化；3）设备初始化；

- Qemu中设备模拟通过`type_init`先编译进系统，在`module_call_init`时进行回调，比如图中的`xxx_register_types`，在这些函数中都是根据`TypeInfo`类型信息来创建具体的实现信息；
- `net_init_client`用来创建网络设备，比如`Tap`设备；
- `device_init_func`根据Qemu命令的传入参数创建虚拟设备，比如`Virtio-Net`；

下边进入细节，`the devil is in the details`。

# 3. tap创建

从上文中，我们知道，`Tap`与`Virtio-Net`属于前后端的关系，最终是通过结构体分别指向对方，如下图：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002217998-1655315613.png)

- `NetClientState`是网卡模拟的核心结构，表示网络设备中的几个端点，两个端点通过`peer`指向对方；

创建Tap设备的主要工作就是创建一个`NetClientState`结构，并添加到`net_clients`链表中：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002303803-1084163909.png)

函数的调用细节如下图：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002310283-874984329.png)

- 处理流程只关注了核心的处理流程，整个过程有很多关于传入参数的处理，选择性忽略了；
- `net_tap_init`：与Host的`tun`驱动进行交互，其实质就是打开该设备文件，并进行相应的配置等；
- `net_tap_fd_init`：根据`net_tap_info`结构，创建`NetClientState`，并进行相关设置，这里边`net_tap_info`结构体中的接收函数指针用于实际的数据传输处理；
- `tap_read_poll`用于将fd添加到Qemu的AioContext中，用于异步响应，当有数据来临时，捕获事件并进行处理；

以上就是Tap后端的创建过程，下文将针对前端创建了。

# 4. virtio-net创建

这是一个复杂的流程。

## 4.1 数据结构

Qemu中用C语言实现了面向对象的模型，用于对设备进行抽象，精妙！

针对Virtio-Net设备，结构体及拓扑组织关系如下图：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002318824-1058290140.png)

- `DeviceState`作为所有设备的父类，其中派生了`VirtIODevice`和`PCIDevice`，而本文研究的`Virtio-Net`派生自`VirtIODevice`；
- Qemu中会虚拟一个PCI总线，同时创建`virtio-net-pci`，`virtio-balloon-pci`，`virtio-scsi-pci`等PCI代理设备，这些代理设备挂载在PCI总线上，同时会创建Virtio总线，用于挂载最终的设备，比如`VirtIONet`；
- PCI代理设备就是一个纽带；

## 4.2 流程分析

与设备创建相关的三个函数，可以从`device_init_func`入口跟踪得知：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002328216-1328380691.png)

- 当Qemu命令通过`-device`传入参数时，`device_init_func`会根据参数去查找设备，并最终调用到该设备对应的类初始化函数、对象初始化函数、以及realize函数；
- 所以，我们的分析就是这三个入口；

### 4.2.1 class_init

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002339829-618075364.png)

- 在网卡虚拟化过程中，参数只需要指定PCI代理设备即可，也就是`-device virtio-net-pci, netdev=tap0`，从而会调用到`virtio_net_pci_class_init`函数；
- 由于实现了类的继承关系，在子类初始化之前，需要先调用父类的实现，图中也表明了继承关系以及调用函数顺序；
- C语言实现继承，也就是将父对象放置在自己结构体的开始位置，图中的颜色能看出来；

### 4.2.2 instance_init

类初始化结束后，开始对象的创建：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002346674-1999852327.png)

- 针对`Virtio-Net-PCI`的实例化比较简单，作为代理，负责将它的后继对象初始化，也就是本文的前端设备`Virtio-Net`；

### 4.2.3 realize

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002356436-18682170.png)

- `realize`的调用，比较绕，简单来说，它的类继承关系中存在多个`realize`的函数指针，最终会从父类开始执行，一直调用到子类，而这些函数指针的初始化在什么时候做的呢？没错，就是在class_init类初始化的时候，进行了赋值，细节不表，结论可靠；
- 最终的调用关系就如图了；

到目前为止，我们似乎都还没有看到`Virtio-Net`设备的相关操作，不用着急，已经很接近真相了：

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002404478-1016637722.png)

- `virtio_net_pci_realize`函数，会触发`virtio_device_realize`的调用，该函数是一个通用的virtio设备实现函数，所有的virtio设备都会调用，而我们的前端设备`Virtio-Net`也是virtio设备；
- `virtio_net_device_realize`就到了我们的主角了，它进行了virtio通用的设置（后续在数据通信中再分析），还创建了一个`NetClientState`端点，与`Tap`设备对应，分别指向了对方，惺惺相惜，各自安好；
- `virtio_bus_device_plugged`表示设备插入总线时的处理，完成的工作就是按照PCI总线规划，配置各类信息，以便与Guest OS中的virtio驱动交互，后续的文章再分析了；

本文基本捋清了虚拟网卡前端设备和后端设备的创建过程，完成的工作只是绑定了彼此，数据交互以及通知机制，留给后续吧。

# 参考

`《 Virtual I/O Device (VIRTIO) Version 1.1》`

`https://www.redhat.com/en/blog/virtio-devices-and-drivers-overview-headjack-and-phone`

欢迎关注个人公众号，不定期更新技术文章。

![](https://img2020.cnblogs.com/blog/1771657/202102/1771657-20210213002442969-548664120.jpg)

    
  作者：[LoyenWang](https://www.cnblogs.com/LoyenWang/)

  出处：https://www.cnblogs.com/LoyenWang/

  公众号：LoyenWang

  版权：本文版权归作者和博客园共有

  转载：欢迎转载，但未经作者同意，必须保留此段声明；必须在文章中给出原文连接；否则必究法律责任

    
    
    <div
