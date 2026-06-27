1.概述

      根据前一章信息，virtio设备分为前端设备/通信层/后端设备，本章从后端设备设备（qemu的balloon设备为例）的初始化开始分析。

      从启动到balloon设备开始初始化基本调用流程如下：

![](https://img2020.cnblogs.com/blog/774036/202104/774036-20210421101624613-1715754909.png)

 

 

    balloon代码执行流程如下：

![](https://img2020.cnblogs.com/blog/774036/202104/774036-20210421101645830-1515162619.png)

 

 

 

## 2. 关键结构

###     2.1 balloon设备结构

```
typedef struct VirtIOBalloon {
    VirtIODevice parent_obj;
    VirtQueue *ivq, *dvq, *svq;  // 3个 virt queue
    // pages we want guest to give up 
   	uint32_t num_pages; 
    // pages in balloon
    uint32_t actual;
    uint64_t stats[VIRTIO_BALLOON_S_NR];  // status 
    
    // status virtqueue 会用到
    VirtQueueElement *stats_vq_elem;
    size_t stats_vq_offset;
    
    // 定时器, 定时查询功能
    QEMUTimer *stats_timer;
    int64_t stats_last_update;
    int64_t stats_poll_interval;
    
    // features
    uint32_t host_features;
    // for adjustmem, reserved guest free memory
    uint64_t res_size;
} VirtIOBalloon;

```

分析：

- num_pages字段是balloon中表示我们希望guest归还给host的内存大小
- actual字段表示balloon实际捕获的pages数目

          guest处理configuration change中断，完成之后调用virtio_cwrite函数。因为写balloon设备的配置空间，所以陷出，
          qemu收到后会找到balloon设备，修改config修改config时，更新balloon->actual字段

- stats_last_update在每次从status virtioqueue中取出数据时更新

###      2.2 消息通讯结构VirtQueue

```
struct VirtQueue
{
    VRing vring;

    /* Next head to pop */
    uint16_t last_avail_idx;

    /* Last avail_idx read from VQ. */
    uint16_t shadow_avail_idx;

    uint16_t used_idx;

    /* Last used index value we have signalled on */
    uint16_t signalled_used;

    /* Last used index value we have signalled on */
    bool signalled_used_valid;

    /* Notification enabled? */
    bool notification;

    uint16_t queue_index;
    //队列中正在处理的请求的数目
    unsigned int inuse;

    uint16_t vector;
    //回调函数
    VirtIOHandleOutput handle_output;
    VirtIOHandleAIOOutput handle_aio_output;
    VirtIODevice *vdev;
    EventNotifier guest_notifier;
    EventNotifier host_notifier;
    QLIST_ENTRY(VirtQueue) node;
};

```

 

## 3. 初始化流程

###      3.1 设备类型注册

```
type_init(virtio_register_types)
	type_register_static(&virtio_balloon_info);
		->instance_init = virtio_balloon_instance_init,
		->class_init = virtio_balloon_class_init,
```

###  

      3.2 类及实例初始化 ​

```
qemu_opts_foreach(qemu_find_opts("device"), device_init_func, NULL, NULL)	//vl.c
  qdev_device_add								//qdev-monitor.c
    object_new()				
       ->class_init
       ->instance_init
    object_property_set_bool(realized)  --> virtio_balloon_device_realize	//virtio-balloon.c
       ->virtio_init
       ->virtio_add_queue

```

###      3.3 balloon设备实例化

         virtio_balloon_device_realize实例化函数主要执行两个函数完成实例化操作，首先调用virtio_init初始化virtio设备的公共部分。 virtio_init的 主要工作是初始化所有virtio设备的基类TYPE_VIRTIO_DEVICE（"virtio-device"）的实例VirtIODevice结构体。
         实例化代码简化实现如下：

```
static void virtio_balloon_device_realize(DeviceState *dev, Error **errp)
{
    virtio_init(vdev, "virtio-balloon", VIRTIO_ID_BALLOON,
                sizeof(struct virtio_balloon_config));

    ret = qemu_add_balloon_handler(virtio_balloon_to_target,
                                   virtio_balloon_stat,
                                   virtio_balloon_adjustmem,
                                   virtio_balloon_get_stats, s);

...

    s->ivq = virtio_add_queue(vdev, 128, virtio_balloon_handle_output);
    s->dvq = virtio_add_queue(vdev, 128, virtio_balloon_handle_output);
    s->svq = virtio_add_queue(vdev, 128, virtio_balloon_receive_stats);

    reset_stats(s);
}
```

         virio_init的代码流程和基本成员注释如下：

```
void virtio_init(VirtIODevice *vdev, const char *name,
                 uint16_t device_id, size_t config_size)
{
    BusState *qbus = qdev_get_parent_bus(DEVICE(vdev));
    VirtioBusClass *k = VIRTIO_BUS_GET_CLASS(qbus);
    int i;
    int nvectors = k->query_nvectors ? k->query_nvectors(qbus->parent) : 0;

    if (nvectors) {
        //vector_queues与 MSI中断相关
        vdev->vector_queues =
            g_malloc0(sizeof(*vdev->vector_queues) * nvectors);
    }

    vdev->device_id = device_id;
    vdev->status = 0;
    atomic_set(&vdev->isr, 0);  //中断请求
    vdev->queue_sel = 0;    //配置队列的时候选择队列
    //config_vector与MSI中断相关
    vdev->config_vector = VIRTIO_NO_VECTOR;
    //vq分配了1024个virtQueue并进行初始化
    vdev->vq = g_malloc0(sizeof(VirtQueue) * VIRTIO_QUEUE_MAX);
    vdev->vm_running = runstate_is_running();
    vdev->broken = false;
    for (i = 0; i < VIRTIO_QUEUE_MAX; i++) {
        vdev->vq[i].vector = VIRTIO_NO_VECTOR;
        vdev->vq[i].vdev = vdev;
        vdev->vq[i].queue_index = i;
    }

    vdev->name = name;
    //config_len表示配置空间的长度
    vdev->config_len = config_size;
    if (vdev->config_len) {
        //config表示配置数据的存放区域
        vdev->config = g_malloc0(config_size);
    } else {
        vdev->config = NULL;
    }
    vdev->vmstate = qemu_add_vm_change_state_handler(virtio_vmstate_change,
                                                     vdev);
    vdev->device_endian = virtio_default_endian();
    //use_guest_notifier_mask与irqfd有关
    vdev->use_guest_notifier_mask = true;
}

```

        virtio_init主要操作为：

            1. 设置中断
            2. 申请virtqueue空间
            3.  申请配置数据空间
 
        初始化操作完成后，realize函数继续调用virtio_add_queue创建了3个virtqueue（ivq、dvq、svq）并将回调函数virtio_balloon_handle_output挂接到virtqueue的handle_output，用于处理virtqueue中的数据，handle_output函数处理在消息通信一节再分析。 virtio_add_queue实现如下

```
VirtQueue *virtio_add_queue(VirtIODevice *vdev, int queue_size,
                            VirtIOHandleOutput handle_output)
{
    int i;

    for (i = 0; i < VIRTIO_QUEUE_MAX; i++) {
        if (vdev->vq[i].vring.num == 0)
            break;
    }

    if (i == VIRTIO_QUEUE_MAX || queue_size > VIRTQUEUE_MAX_SIZE)
        abort();

    vdev->vq[i].vring.num = queue_size;
    vdev->vq[i].vring.num_default = queue_size;
    vdev->vq[i].vring.align = VIRTIO_PCI_VRING_ALIGN;
    vdev->vq[i].handle_output = handle_output;
    vdev->vq[i].handle_aio_output = NULL;

    return &vdev->vq[i];
}

```

## 4. balloon处理

    4.1 回调函数处理流程
       上一章分析到realize函数注册了3个virtqueue的回调函数，先分析inflate和deflate（ivq和dvq）涉及的函数，查询状态信息的函数稍后分析。ivq和dvq注册的handle_output为virtio_balloon_handle_output，当gust侧通过virtqueue进行通知的时候会调用handle_out对数据进行处理。

```
static void virtio_balloon_handle_output(VirtIODevice *vdev, VirtQueue *vq)
{
    VirtIOBalloon *s = VIRTIO_BALLOON(vdev);
    VirtQueueElement *elem;
    MemoryRegionSection section;

    for (;;) {
        size_t offset = 0;
        uint32_t pfn;
        //获取virtqueue中的数据到qemu侧virt-ring通用的数据结构
        //handle_out函数通用操作
        elem = virtqueue_pop(vq, sizeof(VirtQueueElement));
        if (!elem) {
            if (hax_enabled() && vq == s->dvq) {
                hax_issue_invept();
            }
            return;
        }

        while (iov_to_buf(elem->out_sg, elem->out_num, offset, &pfn, 4) == 4) {
            ram_addr_t pa;
            ram_addr_t addr;
            int p = virtio_ldl_p(vdev, &pfn);
            //将页框转换成GPA
            pa = (ram_addr_t) p << VIRTIO_BALLOON_PFN_SHIFT;
            offset += 4;

            //根据pa找到对应的MemoryRegionSection
            section = memory_region_find(get_system_memory(), pa, 1);
            if (!int128_nz(section.size) ||
                !memory_region_is_ram(section.mr) ||
                memory_region_is_rom(section.mr) ||
                memory_region_is_romd(section.mr)) {
                trace_virtio_balloon_bad_addr(pa);
                memory_region_unref(section.mr);
                continue;
            }

            trace_virtio_balloon_handle_output(memory_region_name(section.mr),
                                               pa);
            /* Using memory_region_get_ram_ptr is bending the rules a bit, but
               should be OK because we only want a single page.  */
            addr = section.offset_within_region;
            //根据section获取对应的HVA，然后调用balloon函数处理对应页面
            balloon_page(memory_region_get_ram_ptr(section.mr) + addr, pa,
                         !!(vq == s->dvq));
            memory_region_unref(section.mr);
        }

        //处理完后通知gust，此处为handle_out通用操作
        virtqueue_push(vq, elem, offset);
        virtio_notify(vdev, vq);
        g_free(elem);
    }
}

```

        handle_output函数使用virtqueue_pop取出virtqueue中对应的数据到VirtQueueElement结构体中，在经过地址转换后得到了HVA地址，然后将HVA和队列信息（dvq/ivq?）传入balloon_page进行qemu侧的balloon处理。

    4.2 qemu处理队列分类

        balloon_page根据deflate参数判断此次操作时inflate还是deflate，分如下操作：
         1. 如果使deflate操作，直接返回。因为deflate操作表示gust会再次使用对应的页面地址，主要是gust内部取消掉这部分页面不可用的标志，QEMU侧因为提供给gust的虚拟地址空间一直是保留状态所以无需特殊处理
          2. 如果使inflate操作，表示对应的页面将不会再提供给gust使用，所以此时先取消对应的ept映射再对QEMU侧的HVA地址使用qemu_madvise进行处理。
       具体代码如下：

```
static void balloon_page(void *addr, ram_addr_t gpa, int deflate)
{
    if (!qemu_balloon_is_inhibited() && (!kvm_enabled() ||
                                         kvm_has_sync_mmu())) {
#ifdef _WIN32
        if (!hax_enabled() || !hax_ept_set_supported()) {
            return;
        }
        // For deflation, ept entry can be rebuilt via VMX EPT VIOLATION.
        if (deflate || hax_invalid_ept_entries(gpa, BALLOON_PAGE_SIZE)) {
            return;
        }
#endif

        qemu_madvise(addr, BALLOON_PAGE_SIZE,
                deflate ? QEMU_MADV_WILLNEED : QEMU_MADV_DONTNEED);
    }
}

```

       4.3 qemu处理虚拟内存
         balloon_page对操作类型分类后，调用qemu_madvise针对不同操作系统处理虚拟地址空间：
qemu_madvise-》 *_madvise。
          *_madvise处理两种情况willneed和dontneed，分别表示deflate和inflate过程，上一步已经说明过deflate过程主要在GUST侧取消页面不可用标记，这里目前只处理dontneed过程。
          在windows平台下虚拟地址申请函数VirtualAlloc可以有提交(commit)和保留（reserve）操作，只有commit的页面才可以在访问时申请物理空间。
          在系统初始化时（参考[这里](http://http//3ms.huawei.com/km/blogs/details/9732599?l=zh-cn)的pc.ram的初始化流程），qemu_anon_ram_alloc函数使用VirtualAlloc（MEM_COMMIT | MEM_RESERVE）为pc.ram保留并提交了4G空间（可配置，不一定是4G)。所以GUST访问的空间都是已经提交过并且保留下来不会被其他malloc之类的函数占用的，因此这4G是连续的。
          当gust执行inflate操作后，放入balloon中的页面也不会再被访问，在上一步中取消EPT映射后需要在free掉对应的虚拟地址以释放内存，但是为了保证pc.ram的内存连续并且随时可用，所以free后再次virtualAlloc（MEM_COMMIT），保持页面是提交状态，避免gust进行deflate后访问对应界面而发生异常。

    
    
    <div
