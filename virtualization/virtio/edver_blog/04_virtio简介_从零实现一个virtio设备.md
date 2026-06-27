# 简介：

　　前几节分析了virtio机制和现有的balloon设备实现，至此我们已经知道了virtio是什么、怎么使用的，本节我们就自己实现一个virtio纯虚设备。

　　功能：

- QEMU模拟的设备启动一个定时器，每5秒发送一次中断通知GUEST
- GUEST对应的驱动接收到中断后讲自身变量自增，然后通过vring发送给QEMU
- QEMU收到GUEST发送过来的消息后打印出接收到的数值 

# 一： 设备创建

#### 　　1. 添加virtio id，

　　　　用于guest内部的设备和驱动match，需要和linux内核中定义一致。

　　　　文件: include/standard-headers/linux/virtio_ids.h

```
#define VIRTIO_ID_TEST       21 /* virtio test */
```

#### 　　2. 添加device id

　　　　vendor-id和device-id用于区分PCI设备,**注意不要超过0x104f**

　　　　文件: include/hw/pci/pci.h

```
#define PCI_DEVICE_ID_VIRTIO_TEST       0x1013
```

#### 　　3. 添加virtio-test设备配置空间定义的头文件

　　　　定义于GUEST协商配置的feature和config结构体，需要与linux中定义一致，config在本示例中并未使用，结构拷贝自balloon

　　　　文件： include/standard-headers/linux/virtio_test.h

```
#ifndef _LINUX_VIRTIO_TEST_H
#define _LINUX_VIRTIO_TEST_H

#include "standard-headers/linux/types.h"
#include "standard-headers/linux/virtio_types.h"
#include "standard-headers/linux/virtio_ids.h"
#include "standard-headers/linux/virtio_config.h"

#define VIRTIO_TEST_F_CAN_PRINT    0

struct virtio_test_config {
    /* Number of pages host wants Guest to give up. */
    uint32_t num_pages;
    /* Number of pages we've actually got in balloon. */
    uint32_t actual;
    /* Event host wants Guest to do */
    uint32_t event;
};

struct virtio_test_stat {
    __virtio16 tag;
    __virtio64 val;
} QEMU_PACKED;

#endif
```

#### 　　4. 添加virtio-test设备模拟代码

　　　　此代码包括了对vring的操作和简介中的功能主体实现，与驱动交互的代码逻辑都在这里。

　　　　文件：hw/virtio/virtio-test.c

```
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/iov.h"
#include "qemu/timer.h"
#include "qemu-common.h"
#include "hw/virtio/virtio.h"
#include "hw/virtio/virtio-test.h"
#include "sysemu/kvm.h"
#include "sysemu/hax.h"
#include "exec/address-spaces.h"
#include "qapi/error.h"
#include "qapi/qapi-events-misc.h"
#include "qapi/visitor.h"
#include "qemu/error-report.h"

#include "hw/virtio/virtio-bus.h"
#include "hw/virtio/virtio-access.h"
#include "migration/migration.h"

static void virtio_test_handle_output(VirtIODevice *vdev, VirtQueue *vq)
{
    VirtIOTest *s = VIRTIO_TEST(vdev);
    VirtQueueElement *elem;
    MemoryRegionSection section;

    for (;;) {
        size_t offset = 0;
        uint32_t pfn;
        elem = virtqueue_pop(vq, sizeof(VirtQueueElement));
        if (!elem) {
            return;
        }

        while (iov_to_buf(elem->out_sg, elem->out_num, offset, &pfn, 4) == 4) {
            int p = virtio_ldl_p(vdev, &pfn);

            offset += 4;
            qemu_log("=========get virtio num:%d\n", p);
        }

        virtqueue_push(vq, elem, offset);
        virtio_notify(vdev, vq);
        g_free(elem);
    }
}

static void virtio_test_get_config(VirtIODevice *vdev, uint8_t *config_data)
{
    VirtIOTest *dev = VIRTIO_TEST(vdev);
    struct virtio_test_config config;

    config.actual = cpu_to_le32(dev->actual);
    config.event = cpu_to_le32(dev->event);

    memcpy(config_data, &config, sizeof(struct virtio_test_config));

}

static void virtio_test_set_config(VirtIODevice *vdev,
                                      const uint8_t *config_data)
{
    VirtIOTest *dev = VIRTIO_TEST(vdev);
    struct virtio_test_config config;

    memcpy(&config, config_data, sizeof(struct virtio_test_config));
    dev->actual = le32_to_cpu(config.actual);
    dev->event = le32_to_cpu(config.event);
}

static uint64_t virtio_test_get_features(VirtIODevice *vdev, uint64_t f,
                                            Error **errp)
{
    VirtIOTest *dev = VIRTIO_TEST(vdev);
    f |= dev->host_features;
    virtio_add_feature(&f, VIRTIO_TEST_F_CAN_PRINT);

    return f;
}

static int virtio_test_post_load_device(void *opaque, int version_id)
{
    VirtIOTest *s = VIRTIO_TEST(opaque);

    return 0;
}

static const VMStateDescription vmstate_virtio_test_device = {
    .name = "virtio-test-device",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = virtio_test_post_load_device,
    .fields = (VMStateField[]) {
        VMSTATE_UINT32(actual, VirtIOTest),
        VMSTATE_END_OF_LIST()
    },
};

static void test_stats_change_timer(VirtIOTest *s, int64_t secs)
{
    timer_mod(s->stats_timer, qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) + secs * 1000);
}

static void test_stats_poll_cb(void *opaque)
{
    VirtIOTest *s = opaque;
    VirtIODevice *vdev = VIRTIO_DEVICE(s);

    qemu_log("==============set config:%d\n", s->set_config++);
    virtio_notify_config(vdev);
    test_stats_change_timer(s, 1);
}

static void virtio_test_device_realize(DeviceState *dev, Error **errp)
{
    VirtIODevice *vdev = VIRTIO_DEVICE(dev);
    VirtIOTest *s = VIRTIO_TEST(dev);
    int ret;

    virtio_init(vdev, "virtio-test", VIRTIO_ID_TEST,
                sizeof(struct virtio_test_config));

    s->ivq = virtio_add_queue(vdev, 128, virtio_test_handle_output);

    /* create a new timer */
    g_assert(s->stats_timer == NULL);
    s->stats_timer = timer_new_ms(QEMU_CLOCK_VIRTUAL, test_stats_poll_cb, s);
    test_stats_change_timer(s, 30);
}

static void virtio_test_device_unrealize(DeviceState *dev, Error **errp)
{
    VirtIODevice *vdev = VIRTIO_DEVICE(dev);
    VirtIOTest *s = VIRTIO_TEST(dev);

    virtio_cleanup(vdev);
}

static void virtio_test_device_reset(VirtIODevice *vdev)
{
    VirtIOTest *s = VIRTIO_TEST(vdev);
}

static void virtio_test_set_status(VirtIODevice *vdev, uint8_t status)
{
    VirtIOTest *s = VIRTIO_TEST(vdev);
    return;
}

static void virtio_test_instance_init(Object *obj)
{
    VirtIOTest *s = VIRTIO_TEST(obj);

    return;
}

static const VMStateDescription vmstate_virtio_test = {
    .name = "virtio-test",
    .minimum_version_id = 1,
    .version_id = 1,
    .fields = (VMStateField[]) {
        VMSTATE_VIRTIO_DEVICE,
        VMSTATE_END_OF_LIST()
    },
};

static Property virtio_test_properties[] = {
    DEFINE_PROP_END_OF_LIST(),
};

static void virtio_test_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    VirtioDeviceClass *vdc = VIRTIO_DEVICE_CLASS(klass);

    dc->props = virtio_test_properties;
    dc->vmsd = &vmstate_virtio_test;
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
    vdc->realize = virtio_test_device_realize;
    vdc->unrealize = virtio_test_device_unrealize;
    vdc->reset = virtio_test_device_reset;
    vdc->get_config = virtio_test_get_config;
    vdc->set_config = virtio_test_set_config;
    vdc->get_features = virtio_test_get_features;
    vdc->set_status = virtio_test_set_status;
    vdc->vmsd = &vmstate_virtio_test_device;
}

static const TypeInfo virtio_test_info = {
    .name = TYPE_VIRTIO_TEST,
    .parent = TYPE_VIRTIO_DEVICE,
    .instance_size = sizeof(VirtIOTest),
    .instance_init = virtio_test_instance_init,
    .class_init = virtio_test_class_init,
};

static void virtio_register_types(void)
{
    type_register_static(&virtio_test_info);
}

type_init(virtio_register_types)
```

　　　　文件： include/hw/virtio/virtio-test.h

```
#ifndef QEMU_VIRTIO_TEST_H
#define QEMU_VIRTIO_TEST_H

#include "standard-headers/linux/virtio_test.h"
#include "hw/virtio/virtio.h"
#include "hw/pci/pci.h"

#define TYPE_VIRTIO_TEST "virtio-test-device"
#define VIRTIO_TEST(obj) \
        OBJECT_CHECK(VirtIOTest, (obj), TYPE_VIRTIO_TEST)

typedef struct VirtIOTest {
    VirtIODevice parent_obj;
    VirtQueue *ivq;
    uint32_t set_config;
    uint32_t actual;
    VirtQueueElement *stats_vq_elem;
    size_t stats_vq_offset;
    QEMUTimer *stats_timer;
    uint32_t host_features;
    uint32_t event;
} VirtIOTest;

#endif
```

#### 　　5. virtio-test-pci设备的实现

　　　　virtio-test设备属于virtio设备挂接在virtio总线上，但是virtio属于PCI设备。真正的设备发现和配置操作都依赖于PCI协议，因此将virtio-test设备包含于virtio-test-pci中，提供给外层的感知是这是一个pci设备，遵循PCI协议的规范。

　　　　头文件： hw/virtio/virtio-pci.h

```
#include "hw/virtio/virtio-gpu.h"
 #include "hw/virtio/virtio-crypto.h"
 #include "hw/virtio/vhost-user-scsi.h"
+#include "hw/virtio/virtio-test.h"
 #if defined(CONFIG_VHOST_USER) && defined(CONFIG_LINUX)
 #include "hw/virtio/vhost-user-blk.h"
 #endif typedef struct VirtIOGPUPCI VirtIOGPUPCI;
 typedef struct VHostVSockPCI VHostVSockPCI;
 typedef struct VirtIOCryptoPCI VirtIOCryptoPCI;
 typedef struct VirtIOWifiPCI VirtIOWifiPCI;
+typedef struct VirtIOTestPCI VirtIOTestPCI;+/*
+ * virtio-test-pci: This extends VirtioPCIProxy.
+ */
+#define TYPE_VIRTIO_TEST_PCI "virtio-test-pci"
+#define VIRTIO_TEST_PCI(obj) \
+        OBJECT_CHECK(VirtIOTestPCI, (obj), TYPE_VIRTIO_TEST_PCI)
+
+struct VirtIOTestPCI {
+    VirtIOPCIProxy parent_obj;
+    VirtIOTest vdev;
+};
```

　　　　文件： hw/virtio/virtio-pci.c

```
/* virtio-test-pci */
static Property virtio_test_pci_properties[] = {
    DEFINE_PROP_UINT32("class", VirtIOPCIProxy, class_code, 0),
    DEFINE_PROP_END_OF_LIST(),
};

static void virtio_test_pci_realize(VirtIOPCIProxy *vpci_dev, Error **errp)
{
    VirtIOTestPCI *dev = VIRTIO_TEST_PCI(vpci_dev);
    DeviceState *vdev = DEVICE(&dev->vdev);

    if (vpci_dev->class_code != PCI_CLASS_OTHERS &&
        vpci_dev->class_code != PCI_CLASS_MEMORY_RAM) { /* qemu < 1.1 */
        vpci_dev->class_code = PCI_CLASS_OTHERS;
    }

    qdev_set_parent_bus(vdev, BUS(&vpci_dev->bus));
    object_property_set_bool(OBJECT(vdev), true, "realized", errp);
}

static void virtio_test_pci_class_init(ObjectClass *klass, void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    VirtioPCIClass *k = VIRTIO_PCI_CLASS(klass);
    PCIDeviceClass *pcidev_k = PCI_DEVICE_CLASS(klass);
    k->realize = virtio_test_pci_realize;
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
    dc->props = virtio_test_pci_properties;
    pcidev_k->vendor_id = PCI_VENDOR_ID_REDHAT_QUMRANET;
    pcidev_k->device_id = PCI_DEVICE_ID_VIRTIO_TEST;
    pcidev_k->revision = VIRTIO_PCI_ABI_VERSION;
    pcidev_k->class_id = PCI_CLASS_OTHERS;
}

static void virtio_test_pci_instance_init(Object *obj)
{
    VirtIOTestPCI *dev = VIRTIO_TEST_PCI(obj);

    virtio_instance_init_common(obj, &dev->vdev, sizeof(dev->vdev),
                                TYPE_VIRTIO_TEST);
}

static const TypeInfo virtio_test_pci_info = {
    .name          = TYPE_VIRTIO_TEST_PCI,
    .parent        = TYPE_VIRTIO_PCI,
    .instance_size = sizeof(VirtIOTestPCI),
    .instance_init = virtio_test_pci_instance_init,
    .class_init    = virtio_test_pci_class_init,
};

@@ -2739,6 +2789,7 @@ static void virtio_pci_register_types(void)
     type_register_static(&virtio_scsi_pci_info);
     type_register_static(&virtio_balloon_pci_info);
+    type_register_static(&virtio_test_pci_info);
     type_register_static(&virtio_serial_pci_info);
     type_register_static(&virtio_net_pci_info);
```

#### 　　6. 使设备生效

- 上述代码没有添加将virtio-test.c加入编译工程的代码，需要在对应CMake工程中将C文件加入，设置include目录（-I）的地方不要漏掉
- 完成后编译生成可执行文件
- 执行启动命令时加入对应参数： -qemu -device virtio-test-pci
- 在hmp界面输入info qtree可以看到设备已经创建
- ![](https://img2022.cnblogs.com/blog/774036/202202/774036-20220209104652708-966561027.png)
- 

 进入guest找到 /sys/buc/pci/devices目录，这里的第19就是我们新建的设备

- ![](https://img2022.cnblogs.com/blog/774036/202202/774036-20220210094813131-1908199180.png)

# 二： GUEST内实现驱动

#### 　　1. 添加virtio id

　　　　需要和设备定义的virtio id一致，用于设备和驱动的match　　

　　　　文件：include/uapi/linux/virtio_ids.h

```
#define VIRTIO_ID_TEST       21 /* virtio test */
```

#### 　　2. 添加virtio-test驱动配置空间结构定义头文件

　　　　文件内容和QEMU定义相同，用于驱动和设备协商配置和feature

　　　　文件：include/uapi/linux/virtio_test.h

```
#ifndef _LINUX_VIRTIO_TEST_H
#define _LINUX_VIRTIO_TEST_H
#include <linux/types.h>
#include <linux/virtio_types.h>
#include <linux/virtio_ids.h>
#include <linux/virtio_config.h>

/* The feature bitmap for virtio balloon */
#define VIRTIO_TEST_F_CAN_PRINT 0

struct virtio_test_config {
    /* Number of pages host wants Guest to give up. */
    __u32 num_pages;
    /* Number of pages we've actually got in balloon. */
    __u32 actual;
};

struct virtio_test_stat {
    __virtio16 tag;
    __virtio64 val;
} __attribute__((packed));

#endif /* _LINUX_VIRTIO_TEST_H */
```

#### 　　3. 添加virtio-test驱动实现

　　　　文件： drivers/virtio/virtio_test.c

```
#include <linux/virtio.h>
#include <linux/virtio_test.h>
#include <linux/swap.h>
#include <linux/workqueue.h>
#include <linux/delay.h>
#include <linux/slab.h>
#include <linux/module.h>
#include <linux/oom.h>
#include <linux/wait.h>
#include <linux/mm.h>
#include <linux/mount.h>
#include <linux/magic.h>

struct virtio_test {
    struct virtio_device *vdev;
    struct virtqueue *print_vq;

    struct work_struct print_val_work;
    bool stop_update;
    atomic_t stop_once;

    /* Waiting for host to ack the pages we released. */
    wait_queue_head_t acked;

    __virtio32 num[256];
};

static struct virtio_device_id id_table[] = {
    { VIRTIO_ID_TEST, VIRTIO_DEV_ANY_ID },
    { 0 },
};

static struct virtio_test *vb_dev;

static void test_ack(struct virtqueue *vq)
{
    struct virtio_test *vb = vq->vdev->priv;
    printk("virttest get ack\n");
    unsigned int len;
    virtqueue_get_buf(vq, &len);
}

static int init_vqs(struct virtio_test *vb)
{
    struct virtqueue *vqs[1];
    vq_callback_t *callbacks[] = { test_ack };
    static const char * const names[] = { "print"};
    int err, nvqs;

    nvqs = virtio_has_feature(vb->vdev, VIRTIO_TEST_F_CAN_PRINT) ? 1 : 0;
    err = virtio_find_vqs(vb->vdev, nvqs, vqs, callbacks, names, NULL);
    if (err)
        return err;

    vb->print_vq = vqs[0];

    return 0;
}

static void remove_common(struct virtio_test *vb)
{
    /* Now we reset the device so we can clean up the queues. */
    vb->vdev->config->reset(vb->vdev);

    vb->vdev->config->del_vqs(vb->vdev);
}

static void virttest_remove(struct virtio_device *vdev)
{
    struct virtio_test *vb = vdev->priv;

    remove_common(vb);
    cancel_work_sync(&vb->print_val_work);
    kfree(vb);
    vb_dev = NULL;
}

static int virttest_validate(struct virtio_device *vdev)
{
    return 0;
}

static void print_val_func(struct work_struct *work)
{
    struct virtio_test *vb;
    struct scatterlist sg;

    vb = container_of(work, struct virtio_test, print_val_work);
    printk("virttest get config change\n");

    struct virtqueue *vq = vb->print_vq;
    vb->num[0]++;
    sg_init_one(&sg, &vb->num[0], sizeof(vb->num[0]));

    /* We should always be able to add one buffer to an empty queue. */
    virtqueue_add_outbuf(vq, &sg, 1, vb, GFP_KERNEL);
    virtqueue_kick(vq);
}

static void virttest_changed(struct virtio_device *vdev)
{
    struct virtio_test *vb = vdev->priv;
    printk("virttest virttest_changed\n");
    if (!vb->stop_update) {
        //atomic_set(&vb->stop_once, 0);
        queue_work(system_freezable_wq, &vb->print_val_work);
    }
}

static int virttest_probe(struct virtio_device *vdev)
{
    struct virtio_test *vb;
    int err;

    printk("******create virttest\n");
    if (!vdev->config->get) {
        return -EINVAL;
    }

    vdev->priv = vb = kmalloc(sizeof(*vb), GFP_KERNEL);
    if (!vb) {
        err = -ENOMEM;
        goto out;
    }
    vb->num[0] = 0;
    vb->vdev = vdev;
    INIT_WORK(&vb->print_val_work, print_val_func);

    vb->stop_update = false;

    init_waitqueue_head(&vb->acked);
    err = init_vqs(vb);
    if (err)
        goto out_free_vb;

    virtio_device_ready(vdev);

    atomic_set(&vb->stop_once, 0);
    vb_dev = vb;

    return 0;

out_free_vb:
    kfree(vb);
out:
    return err;
}

static unsigned int features[] = {
    VIRTIO_TEST_F_CAN_PRINT,
};

static struct virtio_driver virtio_test_driver = {
    .feature_table = features,
    .feature_table_size = ARRAY_SIZE(features),
    .driver.name =  KBUILD_MODNAME,
    .driver.owner = THIS_MODULE,
    .id_table = id_table,
    .validate = virttest_validate,
    .probe =    virttest_probe,
    .remove =   virttest_remove,
    .config_changed = virttest_changed,
};

module_virtio_driver(virtio_test_driver);
MODULE_DEVICE_TABLE(virtio, id_table);
MODULE_DESCRIPTION("Virtio test driver");
MODULE_LICENSE("GPL");
```

#### 　　4. 新驱动编译进内核

　　　　为了简便我们没有定义KConfig中的宏，直接将模块编译进生成的内核文件

　　　　当然这里也可以将virtio_test.o赋值给obj-m，编译成模块，启动后通过insmod进行加载virtio_test.ko

　　　　文件： drivers/virtio/Makefile

```
obj-y += virtio_test.o
```

# 三： 最终效果

　　启动后在qemu测交互打印，每次set config将会使guest内部变量自增，并通过vring发送给qemu，qemu进行打印。

　　![](https://img2022.cnblogs.com/blog/774036/202202/774036-20220209110328556-1058502921.png)

 

    
    
    <div
