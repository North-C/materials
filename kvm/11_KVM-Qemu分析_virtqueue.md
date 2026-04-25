# 背景

- `Read the fucking source code!`  --By 鲁迅
- `A picture is worth a thousand words.` --By 高尔基

说明：

- KVM版本：5.9.1
- QEMU版本：5.0.0
- 工具：Source Insight 3.5， Visio
- 文章同步在博客园：`https://www.cnblogs.com/LoyenWang/`

# 1. 概述

汪汪汪，最近忙成狗了，一下子把我更新的节奏打乱了，草率的道个歉。

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173659872-275187796.png)

- 前边系列将Virtio Device和Virtio Driver都已经讲完，本文将分析virtqueue；
- virtqueue用于前后端之间的数据交换，一看到这种数据队列，首先想到的就是ring-buffer，实际的实现会是怎么样的呢？

# 2. 数据结构

先看一下核心的数据结构：

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173709126-884834927.png)

- 通常Virtio设备操作Virtqueue时，都是通过`struct virtqueue`结构体，这个可以理解成对外的一个接口，而`Virtqueue`机制的实现依赖于`struct vring_virtqueue`结构体；
- `Virtqueue`有三个核心的数据结构，由`struct vring`负责组织：

- `struct vring_desc`：描述符表，每一项描述符指向一片内存，内存类型可以分为out类型和in类型，分别代表输出和输入，而内存的管理都由驱动来负责。该结构体中的next字段，可用于将多个描述符构成一个描述符链，而flag字段用于描述属性，比如只读只写等；
- `struct vring_avail`：可用描述符区域，用于记录设备可用的描述符ID，它的主体是数组ring，实际就是一个环形缓冲区；
- `struct vring_used`：已用描述符区域，用于记录设备已经处理完的描述符ID，同样，它的ring数组也是环形缓冲区，与`struct vring_avail`不同的是，它还记录了设备写回的数据长度；

这么看，当然是有点不太直观，所以，下图来了：

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173718528-1016668684.png)

- 简单来说，驱动会分配好内存（`scatterlist`），并通过`virtqueue_add`添加到描述表中，这样描述符表中的条目就都能对应到具体的物理地址了，其实可以把它理解成一个资源池子；
- 驱动可以将可用的资源更新到`struct vring_avail`中，也就是将可用的描述符ID添加到ring数组中，熟悉环形缓冲区的同学应该清楚它的机制，通过维护头尾两个指针来进行管理，Driver负责更新头指针（idx），Device负责更新尾指针（Qemu中的Device负责维护一个last_avail_idx），头尾指针，你追我赶，生生不息；
- 当设备使用完了后，将已用的描述符ID更新到`struct vring_used`中，`vring_virtqueue`自身维护了last_used_idx，机制与`struct vring_avail`一致；

# 3. 流程分析

## 3.1 发送

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173735876-1164554235.png)

当驱动需要把数据发送给设备时，流程如上图所示：

- ①A表示分配一个Buffer并添加到Virtqueue中，①B表示从Used队列中获取一个Buffer，这两种中选择一种方式；
- ②表示将Data拷贝到Buffer中，用于传送；
- ③表示更新Avail队列中的描述符索引值，注意，驱动中需要执行memory barrier操作，确保Device能看到正确的值；
- ④与⑤表示Driver通知Device来取数据；
- ⑥表示Device从Avail队列中获取到描述符索引值；
- ⑦表示将描述符索引对应的地址中的数据取出来；
- ⑧表示Device更新Used队列中的描述符索引；
- ⑨与⑩表示Device通知Driver数据已经取完了；

## 3.2 接收

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173744024-718252802.png)

当驱动从设备接收数据时，流程如上图所示：

- ①表示Device从Avail队列中获取可用描述符索引值；
- ②表示将数据拷贝至描述符索引对应的地址上；
- ③表示更新Used队列中的描述符索引值；
- ④与⑤表示Device通知Driver来取数据；
- ⑥表示Driver从Used队列中获取已用描述符索引值；
- ⑦表示将描述符索引对应地址中的数据取出来；
- ⑧表示将Avail队列中的描述符索引值进行更新；
- ⑨与⑩表示Driver通知Device有新的可用描述符；

## 3.3 代码分析

代码的分析将围绕下边这个图来展开（`Virtio-Net`），偷个懒，只分析单向数据发送了：

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173757944-2086503669.png)

### 3.3.1 virtqueue创建

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173804452-1571678857.png)

- 之前的系列文章分析过virtio设备和驱动，Virtio-Net是PCI网卡设备驱动，分别会在`virtnet-probe`和`virtio_pci_probe`中完成所有的初始化；
- `virtnet_probe`函数入口中，通过`init_vqs`完成Virtqueue的初始化，这个逐级调用关系如图所示，最终会调用到`vring_create_virtqueue`来创建Virtqueue；
- 这个创建的过程中，有些细节是忽略的，比如通过PCI去读取设备的配置空间，获取创建Virtqueue所需要的信息等；
- 最终就是围绕`vring_virtqueue`数据结构的初始化展开，其中vring数据结构的内存分配也都是在驱动中完成，整个结构体都由驱动来管理与维护；

### 3.3.2 virtio-net驱动发送

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173812553-1572434645.png)

- 网络数据的传输在驱动中通过`start_xmit`函数来实现；
- `xmit_skb`函数中，`sg_init_table`初始化sg列表，`sg_set_buf`将sg指向特定的buffer，`skb_to_sgvec`将socket buffer中的数据填充sg；
- 通过`virtqueue_add_outbuf`将sg添加到Virtqueue中，并更新Avail队列中描述符的索引值；
- `virtqueue_notify`通知Device，可以过来取数据了；

### 3.3.3 Qemu virtio-net设备接收

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173819450-917504788.png)

- Guest驱动写寄存器操作时，陷入到KVM中，最终Qemu会捕获到进行处理，入口函数为`kvm_handle_io`；
- Qemu中会针对IO内存区域设置读写的操作函数，当Guest进行IO操作时，最终触发操作函数的调用，针对Virtio-Net，由于它是PCI设备，操作函数为`virtio_pci_config_write`；
- `virtio_pci_config_write`函数中，对Guest的写操作进行判断并处理，比如在`VIRTIO_PCI_QUEUE_NOTIFY`时，调用`virtio_queue_notify`，用于处理Guest驱动的通知，并最终回调`handle_output`函数；
- 针对Virtio-Net设备，发送的回调函数为`virtio_net_handle_tx_bh`，并在`virtio_net_flush_tx`中完成操作；
- 通用的操作模型：通过`virtqueue_pop`从Avail队列中获取地址，将数据进行处理，通过`virtqueue_push`将处理完后的描述符索引更新到Used队列中，通过`virtio_notify`通知Guest驱动；

Virtqueue这种设计思想比较巧妙，不仅用在virtio中，在AMP系统中处理器之间的通信也能看到它的身影。

草草收场了，下回见。

# 参考

`https://www.redhat.com/en/blog/virtqueues-and-virtio-ring-how-data-travels`

`Virtual I/O Device Version 1.1`

欢迎关注个人公众号，不定期更新技术文章。

![](https://img2020.cnblogs.com/blog/1771657/202103/1771657-20210328173930969-714910267.jpg)

    
  作者：[LoyenWang](https://www.cnblogs.com/LoyenWang/)

  出处：https://www.cnblogs.com/LoyenWang/

  公众号：LoyenWang

  版权：本文版权归作者和博客园共有

  转载：欢迎转载，但未经作者同意，必须保留此段声明；必须在文章中给出原文连接；否则必究法律责任

    
    
    <div
