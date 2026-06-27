## 一： 概要

    在后端模拟出balloon设备后，gustos在启动时会扫描到此设备，遵循linux设备模型调用设备的初始化工作。Virtio-balloon属于 virtio体系，很多工作的细节需要再分析virtio的工作流程，本章暂且只分析balloon的行为，涉及virtio的部分插桩分析向后再补充分析。
    balloon执行流程如下：
![](https://img2020.cnblogs.com/blog/774036/202104/774036-20210421101847574-1209724283.png)

 

 

 

## 二：驱动创建

###     2.1 驱动注册

        Linux设备驱动模型中，各驱动可以按总线类别进行划分，且每个总线类别下可以挂载“驱动”和“设备”两类对象。内核就维护了这样一张“总线”到“驱动和设备”的总表，每当一个新驱动加进内核时，内核会扫描该驱动所挂载总线上的所有设备，并通过比对驱动中的id_table字段和设备配置空间中的Device ID，如果相同则代表该驱动可以为该设备服务，那内核就会针对该设备调用总线的probe函数(如果总线没有probe函数，再调用驱动的probe函数)。
        另外一种情况是往总线上插入一个新设备，内核同样会扫描总线上的所有驱动，看哪个驱动匹配该设备，如果匹配也对该设备调用总线的probe函数(如果总线没有probe函数，再调用驱动的probe函数)。

 　　Linux内核中前端代码主要包括driver/virtio目录下相关文件及driver/virtio_balloon.c，最终生成的内核模块有virtio.ko，virtio_ring.ko，virtio_pci.ko和virtio_balloon.ko。
 　　由于virtio-balloon-pci设备是virtio-pci设备，而virtio-pci设备又是pci设备，所以virtio-pci设备的驱动会注册到pci总线上面，因此，整个初始化过程如下:
　　(1)内核会首先找到virito-pci.ko这个驱动模块，并依次加载virtio.ko,virtio-ring.ko和virtio_pci.ko (virtio_pci.ko依赖前两个模块)执行其模块初始化函数，其中，virtio.ko模块会在系统中注册一种新的总线类型virtio总线，virtio_pci的初始化函数会调用其注册的virtio_pci_probe函数；
　　(2)virtio_pci_probe注册一个virtio设备(register_virtio_device)；
　　(3)内核再次为这个virtio设备搜索驱动模块，最终找到virtio_balloon.ko并加载调用其模块初始化函数；
　　(4)virtio_balloon初始化函数在virtio总线上添加了virtio_balloon驱动并调用了总线的probe函数(总线的probe函数优先级高于总线上设备的probe函数)即virtio_dev_probe；
　　(5)virtio_dev_probe调用virtballoon_probe完成最后的初始化任务。

        我们最终需要关注的是virtballoon_probe这个函数是怎么被调用到的，linux设备初始化开始到调用到virtballoon_probe的过程简化如下，仅供参考：
![](https://img2020.cnblogs.com/blog/774036/202104/774036-20210421101909294-2088242356.png)

 

 

        驱动可执行的动作包含在virtio_balloon_driver定义的结构体中。先来看下这个结构体的内容，文件位置driver/virtio/virtio_balloon.c。

```
static unsigned int features[] = {
	VIRTIO_BALLOON_F_MUST_TELL_HOST,
	VIRTIO_BALLOON_F_STATS_VQ,
	VIRTIO_BALLOON_F_DEFLATE_ON_OOM,
};

static struct virtio_driver virtio_balloon_driver = {
	.feature_table = features,
	.feature_table_size = ARRAY_SIZE(features),
	.driver.name =	KBUILD_MODNAME,
	.driver.owner =	THIS_MODULE,
	.id_table =	id_table,
	.probe =	virtballoon_probe,
	.remove =	virtballoon_remove,
	.config_changed = virtballoon_changed,
#ifdef CONFIG_PM_SLEEP
	.freeze	=	virtballoon_freeze,
	.restore =	virtballoon_restore,
#endif
};
module_virtio_driver(virtio_balloon_driver);

```

        可以看到，注册的 driver中注册了feature属性，driver的名称和owner，驱动加载的probe卸载的remove，感知变化的config_changed，这三个函数做了主要的工作。 先来看下加载做了什么工作。

```
static int virtballoon_probe(struct virtio_device *vdev)
{
	struct virtio_balloon *vb;
	int err;

    //device的get回调函数，用来获取qemu侧模拟的设备的config数据
    //回调在virtio_pci_modern.c中注册，原型为vp_get
	if (!vdev->config->get) {
		dev_err(&vdev->dev, "%s failure: config access disabled\n",
			__func__);
		return -EINVAL;
	}
    //申请一个virtio_balloon结构
	vdev->priv = vb = vb_dev = kmalloc(sizeof(*vb), GFP_KERNEL);
	if (!vb) {
		err = -ENOMEM;
		goto out;
	}
    //需要释放的页面默认为0，即gust默认保留全部页面，不使用balloon释放
	vb->num_pages = 0;
	mutex_init(&vb->balloon_lock);
    //初始化了两个工作队列，用于通知对应工作队列有消息到达，需要被唤醒
	init_waitqueue_head(&vb->config_change);
	init_waitqueue_head(&vb->acked);
	vb->vdev = vdev;
	vb->need_stats_update = 0;
    //尝试申请用于balloon的页面，如果失败一次则增加一
    //用来记录失败次数，如果短时间失败过多表明gust无多余内存可提供给balloon
	vb->alloc_page_tried = 0;
    //是否停止balloon，如gustos发生了lowmemkiller即内存不够gust使用，则停止balloon
	atomic_set(&vb->stop_balloon, 0);

	balloon_devinfo_init(&vb->vb_dev_info);
#ifdef CONFIG_BALLOON_COMPACTION
	vb->vb_dev_info.migratepage = virtballoon_migratepage;
#endif
    //初始化virtqueue，用于和后端设备进行通信
    //创建了3个queue用于ivq/dvq/svq时间的信息传输
    //同时注册了三个callback函数，用来唤醒上面写的两个工作队列
	err = init_vqs(vb);
	if (err)
		goto out_free_vb;
        //向oom的notify链表中添加处理回调函数，在out_of_memory函数中会调用
	vb->nb.notifier_call = virtballoon_oom_notify;
	vb->nb.priority = VIRTBALLOON_OOM_NOTIFY_PRIORITY;
	err = register_oom_notifier(&vb->nb);
	if (err < 0)
		goto out_oom_notify;
    //读取设备侧config的status，检查VIRTIO_CONFIG_S_DRIVER_OK是否置位
    //若已置位说明设备侧已经可用
	virtio_device_ready(vdev);
    //启动vballoon线程，balloon主要操作在这里完成
	vb->thread = kthread_run(balloon, vb, "vballoon");
	if (IS_ERR(vb->thread)) {
		err = PTR_ERR(vb->thread);
		goto out_del_vqs;
	}

	return 0;

out_del_vqs:
	unregister_oom_notifier(&vb->nb);
out_oom_notify:
	vdev->config->del_vqs(vdev);
out_free_vb:
	kfree(vb);
out:
	return err;
}

```

        可以看到，这里的主要工作有：

        1. 通过init_waitqueue_head初始化了两个工作队列用来接收QEMU发来的notify

        2. 通过init_vqs初始化了3个 virt_queue用来和qemu发送balloon进行inflate/deflate的page地址信息以及callback回调

        3. 启动内核线程执行vballoon，执行balloon的具体操作

###     2.2 vballoon如何运作

```
static int balloon(void *_vballoon)
{
	struct virtio_balloon *vb = _vballoon;
    //注册工作队列的唤醒函数
	DEFINE_WAIT_FUNC(wait, woken_wake_function);

	set_freezable();
	while (!kthread_should_stop()) {
		s64 diff;

		try_to_freeze();
        //将wait添加到config_change的队列，等待唤醒
        //唤醒操作需要virtballoon_changed处理，其注册到了驱动的config_changed
        //qemu执行virtio_notify_config发送notify时会被调用
        /*gust侧唤醒队列的调用栈如下
        vp_interrupt
          -> vp_config_changed
            -> virtio_config_changed
	          -> __virtio_config_changed
	            ->  drv->config_changed(virtballoon_changed)
	    */
		add_wait_queue(&vb->config_change, &wait);
		for (;;) {
            //towards_target用来计算要释放的page数量->num_pages
			if (((diff = towards_target(vb)) != 0 &&
				vb->alloc_page_tried < 5) ||
			    vb->need_stats_update ||
				!atomic_read(&vb->stop_balloon) ||
			    kthread_should_stop() ||
			    freezing(current))
			    //需要执行balloon则退出这层循环
				break;
			wait_woken(&wait, TASK_INTERRUPTIBLE, MAX_SCHEDULE_TIMEOUT);
            
			vb->alloc_page_tried = 0;
			atomic_set(&vb_dev->stop_balloon, 0);
		}
        //去除等待队列，处理时暂不接受新的balloon的notify
		remove_wait_queue(&vb->config_change, &wait);
        //更新stat信息，在初始化时置零，在stats_request调用时置一，并唤醒config_change队列
        //stats_request放入了virtqueue的callback
		if (vb->need_stats_update)
			stats_handle_request(vb);
        //diff大于零表示需要重gust申请内存放入balloon，释放内存
        //这样gust可用的内存减少，因为内存释放所以host可用内存增多
		if (diff > 0)
			fill_balloon(vb, diff);
        //diff小于零，表示gust需要从balloon中回收内存
        //这样gust可用内存增加，host内存被gust占用则可用内存减少
		else if (diff < 0)
			leak_balloon(vb, -diff);
        //更新balloon中记录的actual，刷新balloon实际申请到或释放掉的内存
		update_balloon_size(vb);

		/*
		 * For large balloon changes, we could spend a lot of time
		 * and always have work to do.  Be nice if preempt disabled.
		 */
		cond_resched();
	}
	return 0;
}

```

       主要涉及到的处理：

        1. 添加等待队列，等待config_change被唤醒，即QEMU有执行balloon操作
        2. 计算需要申请或者释放的空间，即diff值
        3. 如果需要申请或者释放空间，则调用fill_balloon或者leak_balloon进行操作
        4. 更新balloon实际占用的空间，记录到actual变量中，并通知给QEMU
       计算diff值的操作如下

```
static inline s64 towards_target(struct virtio_balloon *vb)
{
	s64 target;
	u32 num_pages;
    //获取最新的num_pages数据
	virtio_cread(vb->vdev, struct virtio_balloon_config, num_pages,
		     &num_pages);

	/* Legacy balloon config space is LE, unlike all other devices. */
	if (!virtio_has_feature(vb->vdev, VIRTIO_F_VERSION_1))
		num_pages = le32_to_cpu((__force __le32)num_pages);

	target = num_pages;
    //使用最新的num_pages数据和已有的数据做差
	return target - vb->num_pages;
}

```

 

###     2.3 balloon充气过程

```
static void fill_balloon(struct virtio_balloon *vb, size_t num)
{
	struct balloon_dev_info *vb_dev_info = &vb->vb_dev_info;

	/* We can only do one array worth at a time. */
	num = min(num, ARRAY_SIZE(vb->pfns));

	mutex_lock(&vb->balloon_lock);
	for (vb->num_pfns = 0; vb->num_pfns < num;
	     vb->num_pfns += VIRTIO_BALLOON_PAGES_PER_PAGE) {
        //从gust空间申请一个页面，并且加入到vb_dev_info->pages链表中
        //并标记page的mapcount和设定private标志。这样可以让page不会被kernel继续使用
		struct page *page = balloon_page_enqueue(vb_dev_info);

		if (!page) {
			dev_info_ratelimited(&vb->vdev->dev,
					     "Out of puff! Can't get %u pages\n",
					     VIRTIO_BALLOON_PAGES_PER_PAGE);
			vb->alloc_page_tried++;
			/* Sleep for at least 1/5 of a second before retry. */
			msleep(200);
			break;
		}
        //清零页面申请失败计数
		vb->alloc_page_tried = 0;
        //填充vb->pfns数组对应项（不太清楚作用，需再分析）
		set_page_pfns(vb, vb->pfns + vb->num_pfns, page);
        //num_pages为通知QEMU侧申请到的页面数量
		vb->num_pages += VIRTIO_BALLOON_PAGES_PER_PAGE;
		if (!virtio_has_feature(vb->vdev,
					VIRTIO_BALLOON_F_DEFLATE_ON_OOM))
			adjust_managed_page_count(page, -1);
	}

	/* Did we get any? */
	if (vb->num_pfns != 0)
        //通过ivq队列将申请到的页面信息发送给qemu
		tell_host(vb, vb->inflate_vq);
	mutex_unlock(&vb->balloon_lock);
}

```

         基本流程可以总结为：从gust空间申请页面放入balloon的链表中，并做标记使该内存内核不可用，填充设备的pfn数组，然后通过ivq通知设备侧进行处理。

###     2.4 leak_balloon过程

```
static unsigned leak_balloon(struct virtio_balloon *vb, size_t num)
{
	unsigned num_freed_pages;
	struct page *page;
	struct balloon_dev_info *vb_dev_info = &vb->vb_dev_info;

	/* We can only do one array worth at a time. */
	num = min(num, ARRAY_SIZE(vb->pfns));

	mutex_lock(&vb->balloon_lock);
	/* We can't release more pages than taken */
	num = min(num, (size_t)vb->num_pages);
	for (vb->num_pfns = 0; vb->num_pfns < num;
	     vb->num_pfns += VIRTIO_BALLOON_PAGES_PER_PAGE) {
        //将申请到balloon的页面释放出来
		page = balloon_page_dequeue(vb_dev_info);
		if (!page)
			break;
        //设置pfn数组
		set_page_pfns(vb, vb->pfns + vb->num_pfns, page);
		vb->num_pages -= VIRTIO_BALLOON_PAGES_PER_PAGE;
	}

	num_freed_pages = vb->num_pfns;
	/*
	 * Note that if
	 * virtio_has_feature(vdev, VIRTIO_BALLOON_F_MUST_TELL_HOST);
	 * is true, we *have* to do it in this order
	 */
	if (vb->num_pfns != 0)
        //使用dvq通知qemu进行处理
		tell_host(vb, vb->deflate_vq);
	release_pages_balloon(vb);
	mutex_unlock(&vb->balloon_lock);
	return num_freed_pages;
}

```

        leak_balloon的过程和fill_balloon刚好相反，它会释放存放在balloon的page链表中的page项归还给gust，同理，这部分 内存会被qemu从host申请回来留给gustos备用，此时host主机的可用内存就减少了。

 

    
    
    <div
