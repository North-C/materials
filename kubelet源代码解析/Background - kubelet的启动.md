# kubelet的构建和启动

```text
app.NewKubeletCommand()
    |- Run(ctx, options.kubeletServer, kubeletDeps, DefaultFeatureGate)  // cmd/kubelet/app/server.go
        |- initForOS()
        |- run(ctx, options.kubeletServer, kubeletDeps, featureGate)
            |- SetFromMap(FeatureGates)                 // Set global feature gates
            |- ValidateKubeletServer()
            |- initConfigz()
            |- GetHostname()
            |- NewContainerManager()                    // pkg/kubelet/cm/container_manager_linux.go
                |- GetCgroupSubsystems()            // 判断是cgroup v1 或者 V2
                |- NewCgroupManager()
                |- NewQOSContainerManager()             // 管理节点上基于 QoS（服务质量等级）划分的顶级 cgroup 目录,与参数--cgroups-per-qos=true(默认值)有关
                |- topologymanager.NewManager()         // 启动TopologyManager()
                |- devicemanager.NewManagerXXX()
                |- cpumanager.NewManager()
                |- memoryManager.NewManager()
            |- ApplyOOMScoreAdj()
            |- PreInitRuntimeService()
                |- NewRemoteRuntimeService()
                |- NewRemoteImageService()
            |- RunKubelet()                    // cmd/kubelet/app/server.go, 负责构建和启动Kubelet
                |- k = createAndInitKubelet()        // pkg/kubelet/kubelet.go
                    |- k = NewMainKubelet()          // 正式新建Kubelet对象
                        |- BirthCry()
                        |- StartGarbageCollection()     // 开始垃圾回收
                |- startKubelet()
                    |- go k.Run()                     // 启动 Kubelet
                    |   |- kl.initializeModules()           // 启动模块
                    |   |- volumeManager.Run()
                    |   |- statusManager.Start()            // 启动组件启动循环
                    |   |- pleg.Start()                 // pod生命周期事件生成
                    |   |- syncLoop()       
                    |    
                    |- go k.ListenAndServe()          // 启动Kubelet server
            |- go daemon.SdNotify(false, "READY=1")
```

创建时的源代码：

```go
func run() {
    ....

kubeDeps.ContainerManager, err = cm.NewContainerManager(
			kubeDeps.Mounter,
			kubeDeps.CAdvisorInterface,
			cm.NodeConfig{
				RuntimeCgroupsName:    s.RuntimeCgroups,
				SystemCgroupsName:     s.SystemCgroups,
				KubeletCgroupsName:    s.KubeletCgroups,
				KubeletOOMScoreAdj:    s.OOMScoreAdj,
				CgroupsPerQOS:         s.CgroupsPerQOS,
				CgroupRoot:            s.CgroupRoot,
				CgroupDriver:          s.CgroupDriver,
				KubeletRootDir:        s.RootDirectory,
				ProtectKernelDefaults: s.ProtectKernelDefaults,
				NodeAllocatableConfig: cm.NodeAllocatableConfig{
					KubeReservedCgroupName:   s.KubeReservedCgroup,
					SystemReservedCgroupName: s.SystemReservedCgroup,
					EnforceNodeAllocatable:   sets.NewString(s.EnforceNodeAllocatable...),
					KubeReserved:             kubeReserved,
					SystemReserved:           systemReserved,
					ReservedSystemCPUs:       reservedSystemCPUs,
					HardEvictionThresholds:   hardEvictionThresholds,
				},
				QOSReserved:                             *experimentalQOSReserved,
				ExperimentalCPUManagerPolicy:            s.CPUManagerPolicy,
				ExperimentalCPUManagerPolicyOptions:     cpuManagerPolicyOptions,
				ExperimentalCPUManagerReconcilePeriod:   s.CPUManagerReconcilePeriod.Duration,
				ExperimentalMemoryManagerPolicy:         s.MemoryManagerPolicy,
				ExperimentalMemoryManagerReservedMemory: s.ReservedMemory,
				ExperimentalPodPidsLimit:                s.PodPidsLimit,
				EnforceCPULimits:                        s.CPUCFSQuota,
				CPUCFSQuotaPeriod:                       s.CPUCFSQuotaPeriod.Duration,
				ExperimentalTopologyManagerPolicy:       s.TopologyManagerPolicy,
				ExperimentalTopologyManagerScope:        s.TopologyManagerScope,
			},
			s.FailSwapOn,
			devicePluginEnabled,
			kubeDeps.Recorder)
            
            ...
}
```

`NewConainerManager()` 创建容器管理器

```go
func NewContainerManager(mountUtil mount.Interface, cadvisorInterface cadvisor.Interface, nodeConfig NodeConfig, failSwapOn bool, devicePluginEnabled bool, recorder record.EventRecorder) (ContainerManager, error) {
	subsystems, err := GetCgroupSubsystems()   // 获取 cgroup v1 或 v2
	if err != nil {
		return nil, fmt.Errorf("failed to get mounted cgroup subsystems: %v", err)
	}
    // 必须关闭 swap
	if failSwapOn {
		// Check whether swap is enabled. The Kubelet does not support running with swap enabled.
		swapFile := "/proc/swaps"
		swapData, err := ioutil.ReadFile(swapFile)
		if err != nil {
			if os.IsNotExist(err) {
				klog.InfoS("File does not exist, assuming that swap is disabled", "path", swapFile)
			} else {
				return nil, err
			}
		} else {
			swapData = bytes.TrimSpace(swapData) // extra trailing \n
			swapLines := strings.Split(string(swapData), "\n")

			// If there is more than one line (table headers) in /proc/swaps, swap is enabled and we should
			// error out unless --fail-swap-on is set to false.
			if len(swapLines) > 1 {
				return nil, fmt.Errorf("running with swap on is not supported, please disable swap! or set --fail-swap-on flag to false. /proc/swaps contained: %v", swapLines)
			}
		}
	}
    // 从 cAdvisor 上抓去机器信息
	var internalCapacity = v1.ResourceList{}
	// It is safe to invoke `MachineInfo` on cAdvisor before logically initializing cAdvisor here because
	// machine info is computed and cached once as part of cAdvisor object creation.
	// But `RootFsInfo` and `ImagesFsInfo` are not available at this moment so they will be called later during manager starts
	machineInfo, err := cadvisorInterface.MachineInfo()
	if err != nil {
		return nil, err
	}
	capacity := cadvisor.CapacityFromMachineInfo(machineInfo)
	for k, v := range capacity {
		internalCapacity[k] = v
	}
	pidlimits, err := pidlimit.Stats()
	if err == nil && pidlimits != nil && pidlimits.MaxPID != nil {
		internalCapacity[pidlimit.PIDs] = *resource.NewQuantity(
			int64(*pidlimits.MaxPID),
			resource.DecimalSI)
	}

	// Turn CgroupRoot from a string (in cgroupfs path format) to internal CgroupName
	cgroupRoot := ParseCgroupfsToCgroupName(nodeConfig.CgroupRoot)
	cgroupManager := NewCgroupManager(subsystems, nodeConfig.CgroupDriver)
	// Check if Cgroup-root actually exists on the node
	if nodeConfig.CgroupsPerQOS {
		// this does default to / when enabled, but this tests against regressions.
		if nodeConfig.CgroupRoot == "" {
			return nil, fmt.Errorf("invalid configuration: cgroups-per-qos was specified and cgroup-root was not specified. To enable the QoS cgroup hierarchy you need to specify a valid cgroup-root")
		}

		// we need to check that the cgroup root actually exists for each subsystem
		// of note, we always use the cgroupfs driver when performing this check since
		// the input is provided in that format.
		// this is important because we do not want any name conversion to occur.
		if err := cgroupManager.Validate(cgroupRoot); err != nil {
			return nil, fmt.Errorf("invalid configuration: %w", err)
		}
		klog.InfoS("Container manager verified user specified cgroup-root exists", "cgroupRoot", cgroupRoot)
		// Include the top level cgroup for enforcing node allocatable into cgroup-root.
		// This way, all sub modules can avoid having to understand the concept of node allocatable.
		cgroupRoot = NewCgroupName(cgroupRoot, defaultNodeAllocatableCgroupName)
	}
	klog.InfoS("Creating Container Manager object based on Node Config", "nodeConfig", nodeConfig)

	qosContainerManager, err := NewQOSContainerManager(subsystems, cgroupRoot, nodeConfig, cgroupManager)
	if err != nil {
		return nil, err
	}

	cm := &containerManagerImpl{
		cadvisorInterface:   cadvisorInterface,
		mountUtil:           mountUtil,
		NodeConfig:          nodeConfig,
		subsystems:          subsystems,
		cgroupManager:       cgroupManager,
		capacity:            capacity,
		internalCapacity:    internalCapacity,
		cgroupRoot:          cgroupRoot,
		recorder:            recorder,
		qosContainerManager: qosContainerManager,
	}

	if utilfeature.DefaultFeatureGate.Enabled(kubefeatures.TopologyManager) {
		cm.topologyManager, err = topologymanager.NewManager(
			machineInfo.Topology,
			nodeConfig.ExperimentalTopologyManagerPolicy,
			nodeConfig.ExperimentalTopologyManagerScope,
		)

		if err != nil {
			return nil, err
		}

	} else {
		cm.topologyManager = topologymanager.NewFakeManager()
	}

	klog.InfoS("Creating device plugin manager", "devicePluginEnabled", devicePluginEnabled)
	if devicePluginEnabled {
		cm.deviceManager, err = devicemanager.NewManagerImpl(machineInfo.Topology, cm.topologyManager)
		cm.topologyManager.AddHintProvider(cm.deviceManager)
	} else {
		cm.deviceManager, err = devicemanager.NewManagerStub()
	}
	if err != nil {
		return nil, err
	}

	// Initialize CPU manager
	if utilfeature.DefaultFeatureGate.Enabled(kubefeatures.CPUManager) {
		cm.cpuManager, err = cpumanager.NewManager(
			nodeConfig.ExperimentalCPUManagerPolicy,
			nodeConfig.ExperimentalCPUManagerPolicyOptions,
			nodeConfig.ExperimentalCPUManagerReconcilePeriod,
			machineInfo,
			nodeConfig.NodeAllocatableConfig.ReservedSystemCPUs,
			cm.GetNodeAllocatableReservation(),
			nodeConfig.KubeletRootDir,
			cm.topologyManager,
		)
		if err != nil {
			klog.ErrorS(err, "Failed to initialize cpu manager")
			return nil, err
		}
		cm.topologyManager.AddHintProvider(cm.cpuManager)
	}

	if utilfeature.DefaultFeatureGate.Enabled(kubefeatures.MemoryManager) {
		cm.memoryManager, err = memorymanager.NewManager(
			nodeConfig.ExperimentalMemoryManagerPolicy,
			machineInfo,
			cm.GetNodeAllocatableReservation(),
			nodeConfig.ExperimentalMemoryManagerReservedMemory,
			nodeConfig.KubeletRootDir,
			cm.topologyManager,
		)
		if err != nil {
			klog.ErrorS(err, "Failed to initialize memory manager")
			return nil, err
		}
		cm.topologyManager.AddHintProvider(cm.memoryManager)
	}

	return cm, nil
}
```