## 一： 创建过程关键函数

### 1. virtblk_probe

　　虚拟机在启动过程中，virtio bus上检测到有virtio块设备，就调用probe函数来插入这个virtio block设备（前端创建的virtio设备都是PCI设备，因此，在对应的virtio设备的probe函数调用之前，都会调用virtio-pci设备的probe函数，在系统中先插入一个virtio-pci设备）。

　　初始化设备的散列表，从简介（一）的流程图我们知道，系统的 IO请求会先映射到散列表中。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202454879-1565021573.png)

　　virtio_find_single_vq为virtio块设备生成一个vring_virtqueue。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202520291-1952011930.png)

　　这个函数通过调用在virtio-pci中为virtio device定义的OPS，find_vqs就跳转到vp_find_vqs，之后调用vp_try_to_find_vqs。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202548374-932615482.png)

 

 　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202554346-76991480.png)

　　在函数vp_try_to_find_vqs中，setup_vq为virtio设备创建vring_virtqueue队列。

 ![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202621474-99735573.png)

### 2. vring_virtqueue

　　每个virtio设备都有一个virtqueue接口，它提供了一些对vring进行操作的函数，如add_buf，get_buf，kick等，而vring_virtqueue是virtqueue及vring的管理结构。我们在virtio设备中保存virtqueue指针，当要使用它操作vring时，通过to_vvq来获得其管理结构vring_virtqueue。

 ![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202701548-1581624855.png)

　　Vring_virtqueue的数据结构如下所示：

 　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202708823-1236790460.png)

　　Vring，是IO请求地址的真正存放空间(virtio block设备在初始化的时候，会申请了两个页大小的空间)。num_free，表示vring_desc表中还有多少项是空闲可用的；free_head，表示在vring_desc中第一个空闲表项的位置（并且系统会将其余空闲表项通过vring_desc的next串联成一个空闲链表）；num_added，表示我们在通知对端进行读写的时候，与上次通知相比，我们添加了多少个新的IO请求到vring_desc中；last_used_idx，表示vring_used表中的idx上次IO操作之后被更新到哪个位置（与当前的vring_used->idx相减即可获得本次QEMU处理了多少个vring_desc表中的数据）。

### 3. setup_vq

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202735020-1806452143.png)

　　通过to_vp_device将virtio_device转换成virtio-pci，我们在前端虚拟机内创建的virtio设备都是一个pci设备，因此可以利用PCI设备的配置空间来完成前后端消息通知，vp_dev->ioaddr就指向配置空间的寄存器集合的首地址。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202827769-899663011.png)

　　iowrite写寄存器VIRTIO_PCI_QUEUE_SEL来通知QEMU端，当前初始化的是第index号vring_virtqueue；ioread则从QEMU端读取vring_desc表，共有多少项（virtio block设备设置为128项）。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202853704-225253373.png)

　　根据之前ioread获得的表项数来确定vring共享区域的大小，并调用alloc_pages_exact在虚拟机里为vring_virtqueue分配内存空间。

　　 ![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202917460-1949546436.png)

　　virt_to_phys(info->queue) >> VIRTIO_PCI_QUEUE_ADDR_SHIFT将虚拟机的虚拟机地址转换成物理地址，偏移VIRTIO_PCI_QUEUE_ADDR_SHIFT(12位)得到页号。

　　iowrite将vring_virtqueue在虚拟机内的物理页号写到寄存器VIRTIO_PCI_QUEUE_PFN，产生一个kvm_exit，QEMU端会捕获这个exit，并根据寄存器的地址将这个物理页号赋值给QEMU端维护的virtqueue。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510202941987-1616672675.png)

### 4. Vring_new_virtqueue 

　　 ![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510203009991-1118198232.png)

 

 

　　参数pages，是在setup_vq中给vring_virtqueue申请的物理内存页地址；参数num，是在setup_vq中通过ioread获得的vring_desc表的表项数目；vring_align，为4096，表示一个页的大小；notify，是virtio-pci注册的函数vp_notify，当要通知qemu端取vring中的数据时，就调用notify函数；callback，是qemu端完成IO请求返回后，前端处理的回调函数，virtio-blk的回调函数就是blk_done。

## 二： QEMU获取VRING地址

　　在1.3节中，提到了virtio_map函数注册了对PCI配置空间寄存器的监听函数，当虚拟机产生kvm_exit时，会根据exit的原因将退出数据分发，IO请求会被发送到这些监听函数，他们会调用virtio_ioport_write/read确定前端读/写了哪个寄存器，触发何种动作。

virtio_ioport_write对应前端的iowrite操作，virtio_ioport_read对应前端的ioread操作。

### 1. virtio_ioport_write

　　virtio_ioport_write函数根据我们iowrite的地址来区分写了哪个寄存器，要执行之后的哪些操作。

　　对于vring这个数据区域的共享，前端虚拟机在分配物理页之后，调用

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510203229343-438397774.png)

　　来通知后端QEMU进程

　　因此，我们可以看到在函数中：

![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510203337387-1022164024.png)

　　从配置空间对应的位置获得前端写入的物理页号（客户机的物理页）。

### 2. virtio_queue_set_addr

　　该函数将QEMU进程维护的virtio设备的virtqueue地址初始化，使得前端和后端指向同一片地址空间。（由于KVM下虚拟机是一个QEMU进程，因此虚拟机的内存是由QEMU进程来分配的，并且在QEMU进程内有mem_slot链表进行维护， QEMU进程知道了虚拟机创建的VRING的GPA就可以通过简单的转换在自己的HVA地址中找到VRING的内存地址）。

![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510203421977-135169719.png)

### 3. virtqueue_init

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510203443435-1546515829.png)

　　将QEMU进程内的vring中的三个表的地址初始化。

## 三：完整的读写流程

![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220510203522887-2119514271.png)

## 四. 前端写请求（Guest kernel）

### 1. do_virtblk_request

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511093908459-1025309243.png)

　　内核将IO request队列传递给该函数来处理，在while循环中将队列里的request取出，递交给do_req来做具体的请求处理，每处理一个请求issued就加1。

　　从while循环中退出时，若issued不等于0，就表示有IO request被处理过，调用virtqueue_kick通知对端QEMU。

###  2. do_req

　　该函数主要动作如下：

　　1)        获取IO request中的磁盘扇区信息；

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511094345682-301199047.png)

　　2)        第一次调用sg_set_buf，将磁盘请求的扇区信息存在virtio device的散列表中；

　　 ![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511094412459-552136365.png)

　　3)        调用blk_rq_map_sg，将request中的数据地址存至散列表里；

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511094509476-1472965056.png)

　　4)        第二次调用sg_set_buf，将本次请求的状态等额外信息存至散列表末尾；

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511094521261-896281128.png)

　　5)        调用virtqueue_add_buf，将散列表中存储的信息映射至vring数据结构内。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511094531133-1224964082.png)

 

 

 3. blk_rq_map_sg

　　将以此IO request的地址映射到virtio device的散列表(scatterlist)，返回值是散列表被填充的数目。

　　Linux系统中磁盘IO请求的数据结构是如下所示的：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511094614702-886335300.png)

　　因此，IO请求的具体内容是存储在bio_vec->bv_page这个页的bio_vec->bv_offset位置。

 

 

 　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095024551-1025606242.png)

　　这个函数是一个循环，从request中依次取出bio_vec，并保存在bvec变量中。

　　之后调用sg_set_page将bio_vec结构体中的数据赋值给virtio device的散列表。

![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095114301-240120209.png) 

　　该函数的具体操作如下：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095135864-1636493394.png)

　　在散列表中设置一次请求的结尾标志：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095144487-413729692.png)

　　因此，virtio块设备的散列表组织是这样的，第一项是IO请求的磁盘扇区信息，中间是具体的IO请求在内存中的地址，最后一项为结束标记位。

### 4.  virtqueue_add_buf_gfp

　　之前，我们通过blk_rq_map_sg将request中的请求地址存至散列表scatterlist中，通过add_buf可以将散列表中的请求地址存至vring数据结构中。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095325629-1778862709.png)

　　通过to_vvq，获得virtqueue（这个virtqueue是每个virtio device的成员）的管理结构vring_virtqueue。

　　有了vring_virtqueue后我们的vring数据结构如下所示：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095413269-55209520.png)

　　freehead指向了空闲链表的头结点。

　　在virtqueue_add_buf_gfp中对vq加锁，防止其他线程来操作vring这个数据结构。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095455535-2117310148.png)

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095504144-2057638186.png)

　　判断vring_desc中是否有足够的空闲空间来保存本次IO  request中需要添加的数据项（out+in），如果没有足够的空间就调用notify函数来通知对端，进行读写操作消耗掉vring中的数据。

　　 ![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095548174-1770527399.png)

　　num_free域进行更新，减去本次要添加到vring_desc表中的数据项，head指向当前表项中的第一个空闲位置。

　　 ![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095606730-1239061351.png)

　　在这个for循环中，sg_phys函数将散列表中的sg->page_link和sg->offset相加，获得IO请求的一个具体物理内存地址并存至vring.desc.addr中。同时设置flags为VRING_DESC_F_NEXT表示本次IO请求的数据还未结束，每个IO请求都有可能在vring_desc表中占据多项，通过next域将他们连接成一个链表的形式。prev指向vring_desc添加的最后一项表项，i指向下一个空闲表项。

 　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095646214-1536720125.png)

　　循环退出后，prev指向的最后一项表项的flags域置为非next，表示这次IO请求到该项结束。更新free_head为第一个空闲表项，即i。

　　 ![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095708671-1135235704.png)

　　vring->avail是与vring_desc对应的一张表，它指示vring_desc中有哪些表项是新添加的数据项。

　　vring.avail->ring中依次存放着每个IO请求在vring_desc组成的链表的表头位置，在for循环开始之前我们将head赋值为free_head，然后在for循环中我们从free_head所指向的位置开始添加数据，因此本次IO请求在vring_desc中组成的链表的表头就是head所指向的位置。

　　vring.avail->idx是16位长的无符号整数，它指向的是vring->avail.ring这个数组下一个可用位置，将在virtqueue_kick函数中更新这个域。

　　对vring_virtqueue更新完之后，用END_USE(vq)对其锁进行释放。

### 5. virtqueue_kick

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095801011-1699240690.png)

　　对vring_virtqueue加锁，之后更新vring.avail->idx域，它指向的是vring.avail->ring数组中下一个可用位置（即第一个空闲位置）。对端qemu程序可以取得vring这个数据结构，然后从vring.avail->ring[]中获得每一个request的链表头位置，而vring.avail->idx指示了当前哪些数据是前端设备驱动新更新的。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095822074-241603502.png)

　　调用vring_virtqueue的notify函数来通知对端，这个函数在vring_virtqueue初始化的时候用virtio-pci定义的vp_notify对其注册的，因此调用切换到vp_notify:

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095837201-2025710985.png)

　　调用iowrite向PCI配置空间的相应寄存器写入通知前端的消息。

　　queue_index表示前端将IO请求的数据存在哪个vring中（对于磁盘设备只有一个vring，因此是0；对于virtio-net设备有2-3个vring，这就要区分是读的vring还是写的vring）。

　　vdev->ioaddr是virtio设备初始化的时候赋值，指向PCI配置空间寄存器集的首地址位置，VIRTIO_PCI_QUEUE_NOTIFY是对应寄存器的偏移位置，配置空间的寄存器如下图所示分布：

 　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511095955612-1285805090.png)

　　iowrite会引发kvm_exit，这样通过kvm这个内核模块退出到qemu进程做下一步处理。

## 五.  QEMU端写请求代码流程（QEMU代码）

　　前端产生kvm_exit后，kvm模块会根据EXIT的原因，如果是IO操作的EXIT，就会退出到用户空间，由QEMU进程来完成具体的IO操作。

　　QEMU进程的kvm_main_loop_cpu循环等待KVM_EXIT的产生。当有退出产生时，调用KVM_RUN函数来确定退出的原因，对于IO操作的退出，KVM_EXIT为KVM_EXIT_IO。

　　KVM_RUN对于IO退出的操作就是调用我们在 1.3 virtio_map中注册的virtio_ioport_write函数。

### 1. virtio_ioport_write

　　对前端kick函数的iowrite操作，在virtio_ioport_write中有对应操作如下：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511100157743-845698111.png)

　　virtio_queue_notify调用各个virtio设备在初始化的时候注册的handle函数（virtio-blk设备注册了virtio_blk_handle_output）。

###  2. virtio_blk_handle_output

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511100245528-1478114885.png)

　　在这个while循环中virtio_blk_get_request会从vring中将数据取出（这个过程是通过virtqueue_pop这函数来实现的），放入VirtQueueElement这个数据结构的in_sg[]和out_sg[]这两个数组中。

　　函数virtio_blk_handle_request根据读或写或其他请求来将这些IO请求数据进一步处理。

###  3. virtqueue_pop

　　这个函数主要任务是将数据从vring中取出并保存在QEMU维护的数据结构VirtQueueElement中，所执行的操作如下所示：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511100331287-979392751.png)

 

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511100343738-1688898641.png)

　　要获取vring_desc中的IO请求数据，就要先获取vring_avail这个数组，它保存了vring_desc表中每个IO请求链表的起始位置。virtqueue_get_head返回的就是第一个可用的vring_avail.ring[]的值，根据i这个值就可以从vring_desc[i]中获取数据，并通过next指针在链表中递增查找。同时我们对last_avail_idx递增加1，下次再调用这个函数的时候，就取到了下一个vring_avail.ring[]的值，也就是存在vring_desc表中的另一个IO请求链表的起始位置。

 　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511100450854-1078493509.png)

　　函数virtqueue_pop中通过这个do..while循环来遍历整个vring_desc表。elem指向的是VirtQueueElement数据结构，in_addr直接存vring中取到的数据是前段virtio设备存放的IO请求的GPA地址，sg指向VirtQueueElement.in_sg，并将每个vring_desc[i].len保存在in_sg.iov_len中。vring_desc_addr(desc_pa, i)返回desc_pa[i].addr；vring_desc_len(desc_pa, i)返回desc_pa[i].len；virtqueue_next_desc(desc_pa, i, max)返回的是desc表中的next值。

　　这样我们在vring_desc中的保存的IO请求地址和长度都取了出来:

- 　　VirtQueueElement.in_addr[]= GPA地址
- 　　VirtQueueElement.in_sg[].io_len = 长度

　　我们调用virtqueue_map_sg这个函数对VirtQueueElement.in_addr[]中保存的GPA地址转换成QEMU进程的HVA地址，并保存到VirtQueueElement.in_sg[].iov_base中。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511100508229-1705535803.png)

 

 

###  4. virtio_blk_handle_request

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511100534050-683182833.png)

　　req->elem.out_sg[0].iov_base是IO请求的第一个数据，这数据值在前文中提到过，它是通过第一次调用sg_set_buf获取到的要执行写操作磁盘扇区信息。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511100609258-1062432550.png)

　　type为该请求的类型

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101243975-447348059.png)

　　函数qemu_iovec_init_external是对VirtQueueElement进一步封装成VirtIOBlockReq，然后调用virtio_blk_handle_write，这个函数将请求组成链表，到达32个请求就往下层递交，然后调用virtio_blk_rw_complete—>virtio_blk_req_complete。

　　virtio_blk_req_complete：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101300344-1955848409.png)

 

 

###  5. virtqueue_push

　　virtqueue_push函数主要完成对vring_used表的更新。

　　调用了两个函数：

　　l  virtqueue_fill：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101331172-2139939447.png)

　　更新vring_used表：vring_used_idx返回当前指向vring_used的第一个空闲位置；vring_used_ring_id在idx指向的空闲位置填入vring_desc表中被处理完成的IO请求链表的头结点的位置；vring_used_ring_len在idx指向的空闲位置填入被处理完成的IO请求的链表长度。

　　l  virtqueue_flush

 　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101443978-2007472093.png)

　　vring_used_idx_increment更新vring_used表中的idx域，使他指向表中的下一个空闲位置。

### 6. virtio_notify

　　当虚拟机中的virtio设备注册了回调函数，我们就调用qemu在初始化virtio_pci 时注册的绑定函数

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101525537-1882120004.png)

　　如果前端的virtio pci设备打开了MSIX中断机制，就采用msix_notify；若没开通就用普通的中断，由qemu发起：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101535012-1222530502.png)

## 六.  前端回调函数后续处理(内核代码)

　　QEMU进程对数据处理完成后，通过中断返回到前端，前端在virtio设备初始化virtqueue时注册了一个callback回调函数，对于块设备，回调函数即blk_done。

### 1. blk_done

　　这个函数是前端virtio设备初始化vring_virtqueue时，设置的回调函数。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101915681-1407839738.png)

 

 　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101921561-1552785082.png)

　　处理过程如下所示，通过while循环对每一个处理过的IO请求进行状态检查：正常完成的IO请求，返回0，否贼返回<0。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101937836-471575548.png)

　　将返回的状态值通知给系统，并将处理完成的请求从请求队列中删除，并释放virtio block request的内存空间：

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511101945666-1480063069.png)

 

###  2.virtqueue_get_buf

　　根据vring_used表在vring_desc中查找被后端qemu进程处理过的IO请求表项，并将这些表项重新设置为可用。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511102042069-868793920.png)

　　last_used_idx指向qemu在这次IO处理中所更新的vring_used表的第一项，从vring_used表中取出一个被qemu已处理完成的IO请求链（该链的头结点在vring_desc中的位置并赋值给i），同时获得这个链表的长度len。

 　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511102121998-1520433115.png)

　　ret为void指针，vq->data[i]在virtqueue_add_buf_gfp中将其赋值为virtio block request，在这里用ret指向它并返回ret，可以在blk_done中通过ret->status来获得该virtio块请求的状态等信息。Last_used_idx递增，指向vring_used表的下一项。

###  3. detach_buf

　　这个函数根据vring_usd表获得的值i，将vring_desc表中从i开始的请求链表添加到free链表中。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511102200045-1763294864.png)

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511102202932-1267967351.png)

　　while循环从链表头结点遍历整个链表，递增num_free的值。

　　![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511102211150-651372694.png)

　　vq的free_head指向的是vring_desc表中空闲表项组成的链表的表头，我们将现在释放的vring_desc表中的内容插入到这个空闲链表的表头位置。这样就将vring的空间释放，等待下次IO请求。

　　vq的free_head指向的是vring_desc表中空闲表项组成的链表的表头，我们将现在释放的vring_desc表中的内容插入到这个空闲链表的表头位置。这样就将vring的空间释放，等待下次IO请求。

## 七. 磁盘设备下发discard参数流程

virtio-blk设备如果要支持discard参数下发，需要在执行mount时添加上discard参数，discard参数在ext4文件系统生效的过程如下图所示：

![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511102651052-1626197459.png)

 

jbd2收到discard事件后，分发给blk设备并传递到后端QEMU的过程如下图所示：

![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220517104939143-2112349242.png)

 

 

discard事件后端处理涉及的数据结构和对应的注册及调用流程如下图：

![](https://img2022.cnblogs.com/blog/774036/202205/774036-20220511103029262-602785387.png)

 

    
    
    <div
