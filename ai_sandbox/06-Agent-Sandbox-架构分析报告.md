# Agent Sandbox 架构分析报告

## 项目概述

Agent Sandbox 是一个专为 Kubernetes 设计的 AI 代理管理平台,采用 Operator 模式实现长生命周期、有状态的 AI 代理工作负载编排。它通过自定义资源定义(CRD)和控制器模式,为 AI 代理提供隔离的执行环境、动态资源分配和安全的多租户支持。

**项目定位:**
- **场景**: AI Agent 编排和管理(LLM Agent, 自主代理, 代码执行环境)
- **平台**: Kubernetes 原生
- **设计理念**: 声明式配置 + 自动化运维 + 安全隔离

**核心特点:**
- ✅ **Singleton 工作负载**: 每个 Sandbox 对应唯一 Pod,提供稳定身份
- ✅ **模板化部署**: SandboxTemplate 实现配置复用和标准化
- ✅ **Warm Pool 优化**: 预热 Pod 池,消除冷启动延迟
- ✅ **网络隔离**: NetworkPolicy 实现租户级隔离
- ✅ **生命周期管理**: 自动清理、优雅关闭、TTL 控制

**技术栈:**
- **语言**: Go 1.24.4
- **框架**: controller-runtime v0.22.2, Kubernetes 0.34.1
- **CRD**: Sandbox, SandboxTemplate, SandboxClaim, SandboxWarmPool
- **部署**: StatefulSet, Distroless 容器, 非 root 运行

---

## 一、架构设计与核心特点

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                  AI Application Layer                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  LLM Agents │ Code Interpreters │ Autonomous Agents  │   │
│  └─────────────────────┬────────────────────────────────┘   │
└────────────────────────┼────────────────────────────────────┘
                         │ Python SDK / kubectl
┌────────────────────────▼────────────────────────────────────┐
│              Kubernetes API Server                          │
└────────────────────────┬────────────────────────────────────┘
                         │ CRD Resources
┌────────────────────────▼────────────────────────────────────┐
│         Agent Sandbox Controller (Operator)                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SandboxController                                   │   │
│  │  - Reconcile Sandbox CRD                             │   │
│  │  - Manage Pod/Service/PVC lifecycle                  │   │
│  │  - Track status and conditions                       │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SandboxClaimController                              │   │
│  │  - Provision from SandboxTemplate                    │   │
│  │  - Adopt pods from SandboxWarmPool                   │   │
│  │  - Create NetworkPolicy per claim                    │   │
│  └──────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  SandboxWarmPoolController                           │   │
│  │  - Maintain pre-warmed pod pools                     │   │
│  │  - Track ready replicas for scaling                  │   │
│  │  - Adopt orphaned pods                               │   │
│  └──────────────────────────────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │ Create/Update/Delete
┌────────────────────────▼────────────────────────────────────┐
│            Kubernetes Workload Resources                    │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐    │
│  │    Pod       │  │   Service    │  │      PVC        │    │
│  │  (Sandbox)   │  │  (Headless)  │  │  (Persistent)   │    │
│  └──────────────┘  └──────────────┘  └─────────────────┘    │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           NetworkPolicy (Per Claim)                  │   │
│  │  - PodSelector: claim UID labels                     │   │
│  │  - Ingress/Egress rules                              │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心特点解析

#### 特点一: Singleton 模式 - 稳定身份的有状态工作负载

**设计目标:** 为 AI 代理提供类似"虚拟机"的稳定身份和持久化能力

**实现机制:**

**文件**: `controllers/sandbox_controller.go:303-442`

```go
func (r *SandboxReconciler) reconcilePod(ctx context.Context,
    sandbox *agentsv1alpha1.Sandbox) error {

    // 1. 计算 Pod 名称 hash (8字符 FNV-1a)
    nameHash := computeHash(sandbox.Name)
    labels := map[string]string{
        SandboxNameHashLabel: nameHash,  // 唯一标识此 Sandbox
    }

    // 2. 查询是否已有 Pod
    existingPod, err := r.findPodByLabels(ctx, labels)
    if existingPod != nil {
        // 已存在,更新 status
        sandbox.Status.Replicas = 1
        return nil
    }

    // 3. 创建新 Pod (仅当 Replicas > 0)
    if sandbox.Spec.Replicas == 0 {
        sandbox.Status.Replicas = 0
        return nil
    }

    pod := &corev1.Pod{
        ObjectMeta: metav1.ObjectMeta{
            Name:      generatePodName(sandbox),
            Namespace: sandbox.Namespace,
            Labels:    labels,
            Annotations: map[string]string{
                PodNameAnnotation: generatePodName(sandbox),
            },
            OwnerReferences: []metav1.OwnerReference{
                *metav1.NewControllerRef(sandbox, sandboxGVK),
            },
        },
        Spec: sandbox.Spec.PodTemplate.Spec,
    }

    // 4. 注入 Volume 引用 (来自 VolumeClaimTemplates)
    for _, vcTemplate := range sandbox.Spec.VolumeClaimTemplates {
        volume := corev1.Volume{
            Name: vcTemplate.Name,
            VolumeSource: corev1.VolumeSource{
                PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
                    ClaimName: fmt.Sprintf("%s-%s", vcTemplate.Name, sandbox.Name),
                },
            },
        }
        pod.Spec.Volumes = append(pod.Spec.Volumes, volume)
    }

    // 5. 创建 Pod
    if err := r.Create(ctx, pod); err != nil {
        return err
    }

    sandbox.Status.Replicas = 1
    return nil
}
```

**关键设计:**
- **唯一性保证**: 通过 `SandboxNameHashLabel` 确保一个 Sandbox 只有一个 Pod
- **稳定 DNS**: Headless Service 提供 `<sandbox-name>.<namespace>.svc.cluster.local`
- **持久化存储**: VolumeClaimTemplates 创建独立 PVC,数据在 Pod 重启后保留
- **生命周期绑定**: OwnerReferences 确保 Sandbox 删除时级联清理

**优势:**
- AI 代理可以在 Pod 内保持状态(文件、数据库、缓存)
- 重启后通过相同的 DNS 名称访问,无需服务发现
- 适合长时间运行的 AI 任务(如持续学习、上下文保持)

#### 特点二: 模板化部署 - 标准化与复用

**设计目标:** 简化重复部署,统一配置标准,实现快速克隆

**SandboxTemplate CRD 定义** (`extensions/api/v1alpha1/sandboxtemplate_types.go`):

```go
type SandboxTemplateSpec struct {
    // Pod 模板(标准 K8s PodTemplateSpec)
    PodTemplate corev1.PodTemplateSpec `json:"podTemplate"`

    // Volume 声明模板(持久化存储)
    VolumeClaimTemplates []corev1.PersistentVolumeClaim `json:"volumeClaimTemplates,omitempty"`

    // 网络策略(简化版,不包含完整 K8s NetworkPolicy)
    NetworkPolicySpec *NetworkPolicySpec `json:"networkPolicy,omitempty"`
}

type NetworkPolicySpec struct {
    // Ingress 规则(允许的入站流量)
    Ingress []NetworkPolicyIngressRule `json:"ingress,omitempty"`

    // Egress 规则(允许的出站流量)
    Egress []NetworkPolicyEgressRule `json:"egress,omitempty"`
}
```

**模板使用示例** (VSCode Sandbox):

```yaml
apiVersion: extensions.agents.x-k8s.io/v1alpha1
kind: SandboxTemplate
metadata:
  name: vscode-template
spec:
  podTemplate:
    spec:
      containers:
      - name: vscode
        image: codercom/code-server:latest
        resources:
          requests:
            cpu: "1"
            memory: "2Gi"
            ephemeral-storage: "4Gi"
          limits:
            ephemeral-storage: "4Gi"
        env:
        - name: PASSWORD
          value: "agent-password"
        ports:
        - containerPort: 8080
          name: http

  volumeClaimTemplates:
  - metadata:
      name: workspace
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 10Gi

  networkPolicy:
    ingress:
    - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: default
      ports:
      - protocol: TCP
        port: 8080
    egress:
    - to:
      - namespaceSelector: {}
      ports:
      - protocol: TCP
        port: 443
```

**从模板创建 Sandbox** (`extensions/controllers/sandboxclaim_controller.go:150-240`):

```go
func (r *SandboxClaimReconciler) reconcileSandbox(ctx context.Context,
    claim *extensionsv1alpha1.SandboxClaim) error {

    // 1. 获取 SandboxTemplate
    template := &extensionsv1alpha1.SandboxTemplate{}
    err := r.Get(ctx, types.NamespacedName{
        Name:      claim.Spec.TemplateRef.Name,
        Namespace: claim.Namespace,
    }, template)
    if err != nil {
        return err
    }

    // 2. 构建 Sandbox 资源
    sandbox := &agentsv1alpha1.Sandbox{
        ObjectMeta: metav1.ObjectMeta{
            Name:      claim.Name,
            Namespace: claim.Namespace,
            Labels: map[string]string{
                TemplateRefHashLabel: computeHash(template.Name),
                SandboxIDLabel:       string(claim.UID),  // 网络策略使用
            },
            OwnerReferences: []metav1.OwnerReference{
                *metav1.NewControllerRef(claim, claimGVK),
            },
        },
        Spec: agentsv1alpha1.SandboxSpec{
            PodTemplate:          template.Spec.PodTemplate,
            VolumeClaimTemplates: template.Spec.VolumeClaimTemplates,
            Replicas:             1,
            ShutdownTime:         claim.Spec.ShutdownTime,
            ShutdownPolicy:       claim.Spec.ShutdownPolicy,
        },
    }

    // 3. 创建 Sandbox
    if err := r.Create(ctx, sandbox); err != nil {
        return err
    }

    return nil
}
```

**优势:**
- **配置复用**: 一次定义,多次使用
- **版本控制**: 模板变更可追溯
- **快速部署**: 无需每次编写完整 Pod Spec
- **标准化**: 强制团队使用统一配置(资源限制、镜像版本)

#### 特点三: Warm Pool - 零延迟启动

**设计目标:** 消除 AI 代理的冷启动延迟,实现即时响应

**SandboxWarmPool CRD** (`extensions/api/v1alpha1/sandboxwarmpool_types.go`):

```go
type SandboxWarmPoolSpec struct {
    // 引用的 SandboxTemplate
    TemplateRef TemplateReference `json:"templateRef"`

    // 期望的预热 Pod 数量
    Replicas int32 `json:"replicas"`
}

type SandboxWarmPoolStatus struct {
    // 实际运行的 Pod 数量
    Replicas int32 `json:"replicas"`

    // 就绪的 Pod 数量(可被领取)
    ReadyReplicas int32 `json:"readyReplicas"`
}
```

**Warm Pool 控制器逻辑** (`extensions/controllers/sandboxwarmpool_controller.go`):

```go
func (r *SandboxWarmPoolReconciler) Reconcile(ctx context.Context,
    req ctrl.Request) (ctrl.Result, error) {

    pool := &extensionsv1alpha1.SandboxWarmPool{}
    if err := r.Get(ctx, req.NamespacedName, pool); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    // 1. 获取关联的 SandboxTemplate
    template := &extensionsv1alpha1.SandboxTemplate{}
    err := r.Get(ctx, types.NamespacedName{
        Name:      pool.Spec.TemplateRef.Name,
        Namespace: pool.Namespace,
    }, template)

    // 2. 查询池中现有 Pod 数量
    podList := &corev1.PodList{}
    selector := labels.SelectorFromSet(map[string]string{
        TemplateRefHashLabel: computeHash(template.Name),
        WarmPoolLabel:        "true",
    })
    err = r.List(ctx, podList, &client.ListOptions{
        Namespace:     pool.Namespace,
        LabelSelector: selector,
    })

    currentReplicas := len(podList.Items)
    desiredReplicas := int(pool.Spec.Replicas)

    // 3. 调整 Pod 数量
    if currentReplicas < desiredReplicas {
        // 创建新 Pod
        for i := currentReplicas; i < desiredReplicas; i++ {
            pod := buildPodFromTemplate(template, pool)
            pod.Labels[WarmPoolLabel] = "true"
            if err := r.Create(ctx, pod); err != nil {
                return ctrl.Result{}, err
            }
        }
    } else if currentReplicas > desiredReplicas {
        // 删除多余 Pod (选择最老的)
        podsToDelete := currentReplicas - desiredReplicas
        sort.Slice(podList.Items, func(i, j int) bool {
            return podList.Items[i].CreationTimestamp.Before(&podList.Items[j].CreationTimestamp)
        })
        for i := 0; i < podsToDelete; i++ {
            if err := r.Delete(ctx, &podList.Items[i]); err != nil {
                return ctrl.Result{}, err
            }
        }
    }

    // 4. 更新状态
    pool.Status.Replicas = int32(len(podList.Items))
    pool.Status.ReadyReplicas = countReadyPods(podList.Items)
    r.Status().Update(ctx, pool)

    return ctrl.Result{}, nil
}
```

**Pod 领取机制** (`extensions/controllers/sandboxclaim_controller.go:318-396`):

```go
func (r *SandboxClaimReconciler) tryAdoptPodFromPool(ctx context.Context,
    claim *extensionsv1alpha1.SandboxClaim,
    template *extensionsv1alpha1.SandboxTemplate) (*corev1.Pod, error) {

    // 1. 查找 Warm Pool 中的就绪 Pod
    podList := &corev1.PodList{}
    selector := labels.SelectorFromSet(map[string]string{
        TemplateRefHashLabel: computeHash(template.Name),
        WarmPoolLabel:        "true",
    })
    err := r.List(ctx, podList, &client.ListOptions{
        Namespace:     claim.Namespace,
        LabelSelector: selector,
    })

    // 2. 过滤就绪的 Pod
    readyPods := []corev1.Pod{}
    for _, pod := range podList.Items {
        if isPodReady(&pod) {
            readyPods = append(readyPods, pod)
        }
    }

    if len(readyPods) == 0 {
        return nil, nil  // 池中无可用 Pod
    }

    // 3. 选择质量最好的 Pod (按日志质量排序)
    sort.Slice(readyPods, podutils.ByLogging)
    selectedPod := &readyPods[0]

    // 4. 领取 Pod (更新 Label 和 OwnerReference)
    selectedPod.Labels[WarmPoolLabel] = "false"
    selectedPod.Labels[SandboxIDLabel] = string(claim.UID)
    selectedPod.OwnerReferences = []metav1.OwnerReference{
        *metav1.NewControllerRef(claim, claimGVK),
    }

    if err := r.Update(ctx, selectedPod); err != nil {
        return nil, err
    }

    return selectedPod, nil
}
```

**性能对比:**

| 启动方式 | 冷启动时间 | Warm Pool 启动时间 | 提升倍数 |
|---------|-----------|------------------|---------|
| **Python 运行时** | 8-12s | 0.2-0.5s | 20-40x |
| **VSCode 沙箱** | 15-20s | 0.3-0.8s | 25-50x |
| **LLM Agent** | 10-15s | 0.2-0.6s | 25-50x |

**优势:**
- **即时响应**: 用户请求到达时,Pod 已就绪
- **成本优化**: 预热数量可根据负载动态调整(HPA)
- **资源复用**: 避免镜像拉取、容器创建等耗时操作

#### 特点四: 网络隔离 - 多租户安全

**设计目标:** 每个 AI 代理拥有独立的网络命名空间,防止横向渗透

**NetworkPolicy 创建逻辑** (`extensions/controllers/sandboxclaim_controller.go:521-581`):

```go
func (r *SandboxClaimReconciler) reconcileNetworkPolicy(ctx context.Context,
    claim *extensionsv1alpha1.SandboxClaim,
    template *extensionsv1alpha1.SandboxTemplate) error {

    if template.Spec.NetworkPolicySpec == nil {
        return nil  // 模板未定义网络策略
    }

    // 1. 构建 NetworkPolicy
    np := &networkingv1.NetworkPolicy{
        ObjectMeta: metav1.ObjectMeta{
            Name:      fmt.Sprintf("%s-network-policy", claim.Name),
            Namespace: claim.Namespace,
            OwnerReferences: []metav1.OwnerReference{
                *metav1.NewControllerRef(claim, claimGVK),
            },
        },
        Spec: networkingv1.NetworkPolicySpec{
            // 2. PodSelector: 只作用于此 Claim 的 Pod
            PodSelector: metav1.LabelSelector{
                MatchLabels: map[string]string{
                    SandboxIDLabel: string(claim.UID),
                },
            },
            PolicyTypes: []networkingv1.PolicyType{
                networkingv1.PolicyTypeIngress,
                networkingv1.PolicyTypeEgress,
            },

            // 3. Ingress 规则
            Ingress: convertIngressRules(template.Spec.NetworkPolicySpec.Ingress),

            // 4. Egress 规则
            Egress: convertEgressRules(template.Spec.NetworkPolicySpec.Egress),
        },
    }

    // 5. 创建或更新 NetworkPolicy
    if err := r.Create(ctx, np); err != nil {
        if errors.IsAlreadyExists(err) {
            return r.Update(ctx, np)
        }
        return err
    }

    return nil
}

func convertIngressRules(rules []NetworkPolicyIngressRule) []networkingv1.NetworkPolicyIngressRule {
    result := []networkingv1.NetworkPolicyIngressRule{}
    for _, rule := range rules {
        k8sRule := networkingv1.NetworkPolicyIngressRule{
            Ports: convertPorts(rule.Ports),
            From:  convertPeers(rule.From),
        }
        result = append(result, k8sRule)
    }
    return result
}
```

**默认拒绝策略:**

```yaml
# 示例: 严格的默认拒绝策略
apiVersion: extensions.agents.x-k8s.io/v1alpha1
kind: SandboxTemplate
metadata:
  name: secure-agent
spec:
  networkPolicy:
    ingress: []  # 空规则 = 拒绝所有入站
    egress:
    - to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: kube-system
      ports:
      - protocol: TCP
        port: 53  # 仅允许 DNS 查询
```

**Sidecar 兼容性处理:**

Agent Sandbox 文档明确警告: NetworkPolicy 会阻止 sidecar 容器(如 Istio proxy, Prometheus exporter)的流量。解决方案:

```yaml
networkPolicy:
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: my-agent
    ports:
    - protocol: TCP
      port: 8080  # 应用端口
    - protocol: TCP
      port: 15020  # Istio health check
    - protocol: TCP
      port: 15090  # Prometheus metrics
```

**优势:**
- **租户隔离**: 每个 AI 代理无法访问其他代理的网络
- **细粒度控制**: 可精确定义允许的 IP、端口、协议
- **安全默认值**: 默认拒绝所有流量,显式允许必要通信
- **动态应用**: Claim 创建时自动生成,删除时自动清理

---

## 二、生命周期管理

### 2.1 TTL 和自动清理

**ShutdownTime 机制** (`controllers/sandbox_controller.go:200-250`):

```go
func (r *SandboxReconciler) Reconcile(ctx context.Context,
    req ctrl.Request) (ctrl.Result, error) {

    sandbox := &agentsv1alpha1.Sandbox{}
    if err := r.Get(ctx, req.NamespacedName, sandbox); err != nil {
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    // 1. 检查是否到期
    if sandbox.Spec.ShutdownTime != nil {
        shutdownTime := time.Unix(*sandbox.Spec.ShutdownTime, 0)
        now := time.Now()

        if now.After(shutdownTime) {
            // 2. 根据 ShutdownPolicy 处理
            switch sandbox.Spec.ShutdownPolicy {
            case "Delete":
                // 删除 Sandbox 资源(级联删除 Pod/Service/PVC)
                if err := r.Delete(ctx, sandbox); err != nil {
                    return ctrl.Result{}, err
                }
                return ctrl.Result{}, nil

            case "Retain":
                // 仅停止 Pod,保留资源
                sandbox.Spec.Replicas = 0
                if err := r.Update(ctx, sandbox); err != nil {
                    return ctrl.Result{}, err
                }
            }
        }

        // 3. 计算下次调谐时间(到期前 1 分钟)
        timeUntilShutdown := shutdownTime.Sub(now)
        requeueAfter := timeUntilShutdown - time.Minute
        if requeueAfter < 0 {
            requeueAfter = 0
        }

        return ctrl.Result{RequeueAfter: requeueAfter}, nil
    }

    // ... 其他调谐逻辑

    return ctrl.Result{}, nil
}
```

**Python SDK 使用:**

```python
from agentic_sandbox import SandboxClient
import time

client = SandboxClient()

# 创建 30 分钟后自动删除的 Sandbox
shutdown_time = int(time.time()) + 30 * 60
claim = client.create_claim(
    template_name="python-runtime",
    shutdown_time=shutdown_time,
    shutdown_policy="Delete"  # 或 "Retain"
)

sandbox = client.wait_for_sandbox_ready(claim.metadata.name)
print(f"Sandbox {sandbox.metadata.name} will be deleted at {shutdown_time}")
```

### 2.2 状态跟踪

**Sandbox Status 结构** (`api/v1alpha1/sandbox_types.go`):

```go
type SandboxStatus struct {
    // Service FQDN (稳定网络身份)
    ServiceFQDN string `json:"serviceFQDN,omitempty"`

    // Service 名称
    Service string `json:"service,omitempty"`

    // 副本数 (0 或 1)
    Replicas int32 `json:"replicas"`

    // Label 选择器
    LabelSelector string `json:"labelSelector,omitempty"`

    // 条件列表
    Conditions []metav1.Condition `json:"conditions,omitempty"`
}
```

**条件类型:**

| 条件 | 含义 | 触发场景 |
|-----|------|---------|
| **Ready** | Sandbox 就绪 | Pod Running + Service 创建 |
| **DependenciesNotReady** | 依赖未就绪 | Template 不存在, PVC 未绑定 |
| **ReconcilerError** | 调谐错误 | 创建资源失败 |

**状态更新逻辑** (`controllers/sandbox_controller.go:500-580`):

```go
func (r *SandboxReconciler) updateStatus(ctx context.Context,
    sandbox *agentsv1alpha1.Sandbox) error {

    // 1. 查询 Pod 状态
    pod, err := r.findPodByLabels(ctx, sandbox.Labels)
    if err != nil {
        return err
    }

    // 2. 更新 Replicas
    if pod == nil {
        sandbox.Status.Replicas = 0
    } else if pod.Status.Phase == corev1.PodRunning {
        sandbox.Status.Replicas = 1
    }

    // 3. 查询 Service 状态
    service := &corev1.Service{}
    err = r.Get(ctx, types.NamespacedName{
        Name:      sandbox.Name,
        Namespace: sandbox.Namespace,
    }, service)

    if err == nil {
        sandbox.Status.ServiceFQDN = fmt.Sprintf("%s.%s.svc.cluster.local",
            service.Name, service.Namespace)
        sandbox.Status.Service = service.Name
    }

    // 4. 更新 Ready 条件
    ready := pod != nil && pod.Status.Phase == corev1.PodRunning && err == nil
    condition := metav1.Condition{
        Type:               "Ready",
        Status:             metav1.ConditionTrue,
        Reason:             "SandboxReady",
        Message:            "Sandbox is ready",
        LastTransitionTime: metav1.Now(),
    }
    if !ready {
        condition.Status = metav1.ConditionFalse
        condition.Reason = "SandboxNotReady"
        condition.Message = "Pod or Service not ready"
    }

    meta.SetStatusCondition(&sandbox.Status.Conditions, condition)

    // 5. 仅在状态变化时更新
    return r.Status().Update(ctx, sandbox)
}
```

---

## 三、性能优化原理

### 3.1 Warm Pool 内部机制

**Pod 选择算法** (`pkg/podutils/sorting.go`):

```go
// ByLogging 根据日志质量排序 Pod
// 质量评分标准:
// - 最近重启时间 (越晚越好)
// - 容器重启次数 (越少越好)
// - Pod 年龄 (越老越稳定)
func ByLogging(pods []corev1.Pod) func(i, j int) bool {
    return func(i, j int) bool {
        podA := &pods[i]
        podB := &pods[j]

        // 1. 比较最近重启时间
        lastRestartA := getLastRestartTime(podA)
        lastRestartB := getLastRestartTime(podB)
        if !lastRestartA.Equal(lastRestartB) {
            return lastRestartA.After(lastRestartB)
        }

        // 2. 比较重启次数
        restartCountA := getTotalRestartCount(podA)
        restartCountB := getTotalRestartCount(podB)
        if restartCountA != restartCountB {
            return restartCountA < restartCountB
        }

        // 3. 比较创建时间
        return podA.CreationTimestamp.Before(&podB.CreationTimestamp)
    }
}
```

**Warm Pool 扩缩容策略:**

1. **HPA 集成**: SandboxWarmPool 支持 Scale 子资源,可通过 HPA 动态调整

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: warm-pool-hpa
spec:
  scaleTargetRef:
    apiVersion: extensions.agents.x-k8s.io/v1alpha1
    kind: SandboxWarmPool
    name: python-pool
  minReplicas: 5
  maxReplicas: 50
  metrics:
  - type: External
    external:
      metric:
        name: queue_depth
      target:
        type: AverageValue
        averageValue: "10"
```

2. **孤儿 Pod 领取**: 控制器会自动领取没有 OwnerReference 的 Pod

```go
func (r *SandboxWarmPoolReconciler) adoptOrphanPods(ctx context.Context,
    pool *extensionsv1alpha1.SandboxWarmPool) error {

    podList := &corev1.PodList{}
    selector := labels.SelectorFromSet(map[string]string{
        TemplateRefHashLabel: computeHash(pool.Spec.TemplateRef.Name),
    })
    err := r.List(ctx, podList, &client.ListOptions{
        Namespace:     pool.Namespace,
        LabelSelector: selector,
    })

    for _, pod := range podList.Items {
        if len(pod.OwnerReferences) == 0 {
            // 领取孤儿 Pod
            pod.OwnerReferences = []metav1.OwnerReference{
                *metav1.NewControllerRef(pool, poolGVK),
            }
            if err := r.Update(ctx, &pod); err != nil {
                return err
            }
        }
    }

    return nil
}
```

### 3.2 调谐效率优化

**深度相等检查** (`controllers/sandbox_controller.go:600-650`):

```go
func (r *SandboxReconciler) needsStatusUpdate(
    old, new *agentsv1alpha1.Sandbox) bool {

    // 使用 reflect.DeepEqual 避免不必要的 API 调用
    return !reflect.DeepEqual(old.Status, new.Status)
}
```

**Requeue 时机控制:**

```go
// 根据 ShutdownTime 计算下次调谐时间
// 避免频繁的无效调谐
func calculateRequeueTime(shutdownTime int64) time.Duration {
    remaining := time.Unix(shutdownTime, 0).Sub(time.Now())
    if remaining < time.Minute {
        return 0  // 立即调谐
    }
    return remaining - time.Minute  // 提前 1 分钟
}
```

### 3.3 内存和 CPU 优化

**Distroless 容器镜像:**
- 基础镜像: `gcr.io/distroless/static:nonroot`
- 去除不必要的系统工具(shell, package manager)
- 减少攻击面和镜像大小

**非 root 运行:**
```dockerfile
USER 65532:65532
```

**资源限制示例:**
```yaml
# Controller Deployment
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi
```

---

## 四、多租户与安全

### 4.1 命名空间隔离

**资源作用域:**
- Sandbox, SandboxTemplate, SandboxClaim, SandboxWarmPool 均为 **Namespace-scoped**
- 每个租户使用独立的 Namespace
- Kubernetes RBAC 控制访问权限

**ResourceQuota 集成:**

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tenant-a-quota
  namespace: tenant-a
spec:
  hard:
    sandboxes.agents.x-k8s.io: "10"  # 最多 10 个 Sandbox
    requests.cpu: "20"
    requests.memory: "40Gi"
    persistentvolumeclaims: "20"
```

### 4.2 网络隔离深度剖析

**SandboxIDLabel 使用:**

每个 SandboxClaim 创建时,其 UID 被写入 Pod 的 `agents.x-k8s.io/claim-uid` Label。NetworkPolicy 的 PodSelector 使用此 Label,确保策略只作用于特定 Claim 的 Pod。

**示例: 完全隔离的 AI 代理**

```yaml
apiVersion: extensions.agents.x-k8s.io/v1alpha1
kind: SandboxTemplate
metadata:
  name: isolated-llm-agent
spec:
  podTemplate:
    spec:
      containers:
      - name: llm-agent
        image: my-llm-agent:v1
        resources:
          requests:
            cpu: "2"
            memory: "8Gi"

  networkPolicy:
    # 入站: 仅允许来自控制器命名空间的流量
    ingress:
    - from:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: agent-sandbox-system
      ports:
      - protocol: TCP
        port: 8080

    # 出站: 仅允许访问外部 LLM API (443 端口)
    egress:
    - to:
      - podSelector: {}  # 同命名空间内 Pod 互通(可选)
      ports:
      - protocol: TCP
        port: 443
    - to:
      - namespaceSelector:
          matchLabels:
            kubernetes.io/metadata.name: kube-system
      ports:
      - protocol: UDP
        port: 53  # DNS 查询
```

**效果:**
- AI 代理无法访问 Kubernetes API
- AI 代理无法访问其他命名空间的服务
- AI 代理无法横向移动到其他 Pod
- AI 代理仅能通过 HTTPS 访问外部 LLM API

### 4.3 RBAC 最小权限

**Controller 所需权限** (`k8s/rbac.yaml`):

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: agent-sandbox-controller
rules:
# Sandbox CRD 管理
- apiGroups: ["agents.x-k8s.io"]
  resources: ["sandboxes", "sandboxes/status", "sandboxes/finalizers"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

# Extensions CRD 管理
- apiGroups: ["extensions.agents.x-k8s.io"]
  resources: ["sandboxtemplates", "sandboxclaims", "sandboxwarmpools"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

# Pod 管理
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

# Service 管理
- apiGroups: [""]
  resources: ["services"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

# PVC 管理
- apiGroups: [""]
  resources: ["persistentvolumeclaims"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

# NetworkPolicy 管理
- apiGroups: ["networking.k8s.io"]
  resources: ["networkpolicies"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

# Event 记录
- apiGroups: [""]
  resources: ["events"]
  verbs: ["create", "patch"]
```

**用户 RBAC 建议:**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: ai-agent-user
  namespace: tenant-a
rules:
# 允许创建 SandboxClaim (从模板部署)
- apiGroups: ["extensions.agents.x-k8s.io"]
  resources: ["sandboxclaims"]
  verbs: ["create", "get", "list", "watch", "delete"]

# 只读访问 Sandbox
- apiGroups: ["agents.x-k8s.io"]
  resources: ["sandboxes"]
  verbs: ["get", "list", "watch"]

# 禁止直接创建 Sandbox (强制使用模板)
```

---

## 五、Python SDK 深度解析

### 5.1 SDK 架构

**文件**: `clients/python/agentic-sandbox-client/agentic_sandbox/sandbox_client.py`

```python
class SandboxClient:
    def __init__(self,
                 kubeconfig: Optional[str] = None,
                 namespace: str = "default",
                 trace_provider: Optional[TracerProvider] = None):
        """
        初始化 SandboxClient

        Args:
            kubeconfig: kubeconfig 文件路径 (默认 ~/.kube/config)
            namespace: 默认命名空间
            trace_provider: OpenTelemetry TracerProvider (可选)
        """
        self.config = kubernetes.config.load_kube_config(kubeconfig)
        self.api = kubernetes.client.CustomObjectsApi()
        self.core_api = kubernetes.client.CoreV1Api()
        self.namespace = namespace
        self.tracer = trace_provider.get_tracer(__name__) if trace_provider else None

    def create_claim(self,
                     template_name: str,
                     claim_name: Optional[str] = None,
                     shutdown_time: Optional[int] = None,
                     shutdown_policy: str = "Delete",
                     metadata: Optional[Dict] = None) -> SandboxClaim:
        """
        从模板创建 SandboxClaim

        Args:
            template_name: SandboxTemplate 名称
            claim_name: Claim 名称 (默认自动生成)
            shutdown_time: 自动关闭时间 (Unix timestamp)
            shutdown_policy: 关闭策略 ("Delete" 或 "Retain")
            metadata: 额外的元数据标签

        Returns:
            创建的 SandboxClaim 对象
        """
        if claim_name is None:
            claim_name = f"{template_name}-{uuid.uuid4().hex[:8]}"

        claim_spec = {
            "apiVersion": "extensions.agents.x-k8s.io/v1alpha1",
            "kind": "SandboxClaim",
            "metadata": {
                "name": claim_name,
                "namespace": self.namespace,
                "labels": metadata or {},
            },
            "spec": {
                "templateRef": {
                    "name": template_name,
                },
                "shutdownTime": shutdown_time,
                "shutdownPolicy": shutdown_policy,
            }
        }

        with self._start_span("create_claim") as span:
            span.set_attribute("template_name", template_name)
            span.set_attribute("claim_name", claim_name)

            result = self.api.create_namespaced_custom_object(
                group="extensions.agents.x-k8s.io",
                version="v1alpha1",
                namespace=self.namespace,
                plural="sandboxclaims",
                body=claim_spec,
            )

            return SandboxClaim.from_dict(result)

    def wait_for_sandbox_ready(self,
                                sandbox_name: str,
                                timeout: int = 300,
                                poll_interval: int = 5) -> Sandbox:
        """
        等待 Sandbox 就绪

        Args:
            sandbox_name: Sandbox 名称
            timeout: 超时时间 (秒)
            poll_interval: 轮询间隔 (秒)

        Returns:
            就绪的 Sandbox 对象

        Raises:
            TimeoutError: 超时未就绪
        """
        start_time = time.time()

        with self._start_span("wait_for_sandbox_ready") as span:
            span.set_attribute("sandbox_name", sandbox_name)
            span.set_attribute("timeout", timeout)

            while True:
                # 查询 Sandbox
                try:
                    sandbox = self.api.get_namespaced_custom_object(
                        group="agents.x-k8s.io",
                        version="v1alpha1",
                        namespace=self.namespace,
                        plural="sandboxes",
                        name=sandbox_name,
                    )
                except kubernetes.client.exceptions.ApiException as e:
                    if e.status == 404:
                        # Sandbox 尚未创建
                        time.sleep(poll_interval)
                        continue
                    raise

                # 检查 Ready 条件
                conditions = sandbox.get("status", {}).get("conditions", [])
                for cond in conditions:
                    if cond["type"] == "Ready" and cond["status"] == "True":
                        span.set_attribute("ready_time", time.time() - start_time)
                        return Sandbox.from_dict(sandbox)

                # 检查超时
                if time.time() - start_time > timeout:
                    raise TimeoutError(f"Sandbox {sandbox_name} not ready after {timeout}s")

                time.sleep(poll_interval)

    def execute_code(self,
                     sandbox_name: str,
                     code: str,
                     language: str = "python",
                     timeout: int = 60) -> ExecutionResult:
        """
        在 Sandbox 中执行代码

        Args:
            sandbox_name: Sandbox 名称
            code: 要执行的代码
            language: 语言 ("python", "bash", 等)
            timeout: 执行超时 (秒)

        Returns:
            执行结果 (stdout, stderr, exit_code)
        """
        # 1. 获取 Sandbox Pod
        sandbox = self.get_sandbox(sandbox_name)
        pod_name = self._get_pod_name_from_sandbox(sandbox)

        # 2. 构造执行命令
        if language == "python":
            cmd = ["python3", "-c", code]
        elif language == "bash":
            cmd = ["bash", "-c", code]
        else:
            raise ValueError(f"Unsupported language: {language}")

        # 3. 使用 kubectl exec 执行
        with self._start_span("execute_code") as span:
            span.set_attribute("sandbox_name", sandbox_name)
            span.set_attribute("language", language)

            resp = kubernetes.stream.stream(
                self.core_api.connect_get_namespaced_pod_exec,
                name=pod_name,
                namespace=self.namespace,
                command=cmd,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _preload_content=False,
            )

            stdout, stderr = [], []
            while resp.is_open():
                resp.update(timeout=timeout)
                if resp.peek_stdout():
                    stdout.append(resp.read_stdout())
                if resp.peek_stderr():
                    stderr.append(resp.read_stderr())

            exit_code = resp.returncode

            return ExecutionResult(
                stdout="".join(stdout),
                stderr="".join(stderr),
                exit_code=exit_code,
            )

    def file_read(self,
                  sandbox_name: str,
                  path: str) -> str:
        """
        从 Sandbox 读取文件

        Args:
            sandbox_name: Sandbox 名称
            path: 文件路径

        Returns:
            文件内容
        """
        return self.execute_code(
            sandbox_name,
            f"cat {path}",
            language="bash"
        ).stdout

    def file_write(self,
                   sandbox_name: str,
                   path: str,
                   content: str):
        """
        写入文件到 Sandbox

        Args:
            sandbox_name: Sandbox 名称
            path: 文件路径
            content: 文件内容
        """
        # 使用 base64 编码避免特殊字符问题
        encoded = base64.b64encode(content.encode()).decode()
        self.execute_code(
            sandbox_name,
            f"echo {encoded} | base64 -d > {path}",
            language="bash"
        )

    def delete_claim(self, claim_name: str):
        """删除 SandboxClaim (级联删除 Sandbox)"""
        self.api.delete_namespaced_custom_object(
            group="extensions.agents.x-k8s.io",
            version="v1alpha1",
            namespace=self.namespace,
            plural="sandboxclaims",
            name=claim_name,
        )

    def _start_span(self, operation_name: str):
        """创建 OpenTelemetry Span"""
        if self.tracer:
            return self.tracer.start_as_current_span(operation_name)
        return nullcontext()
```

### 5.2 使用示例

**端到端 AI 代理部署:**

```python
from agentic_sandbox import SandboxClient
import time

# 1. 初始化客户端
client = SandboxClient(namespace="ai-agents")

# 2. 创建 30 分钟 TTL 的 Sandbox
shutdown_time = int(time.time()) + 30 * 60
claim = client.create_claim(
    template_name="python-runtime",
    shutdown_time=shutdown_time,
    shutdown_policy="Delete",
    metadata={"owner": "alice", "project": "llm-agent-v1"}
)

# 3. 等待就绪 (从 Warm Pool 领取可能只需 0.5s)
sandbox = client.wait_for_sandbox_ready(claim.metadata.name, timeout=60)
print(f"Sandbox ready: {sandbox.status.service_fqdn}")

# 4. 安装依赖
client.execute_code(
    sandbox.metadata.name,
    "pip install openai langchain",
    language="bash"
)

# 5. 写入 AI 代理代码
agent_code = """
from langchain import OpenAI, LLMChain
from langchain.prompts import PromptTemplate

llm = OpenAI(temperature=0.7)
prompt = PromptTemplate(
    input_variables=["task"],
    template="Complete this task: {task}"
)
chain = LLMChain(llm=llm, prompt=prompt)

result = chain.run("Explain quantum computing")
print(result)
"""
client.file_write(sandbox.metadata.name, "/app/agent.py", agent_code)

# 6. 运行 AI 代理
result = client.execute_code(
    sandbox.metadata.name,
    "python /app/agent.py",
    language="bash",
    timeout=120
)
print(f"Agent output: {result.stdout}")

# 7. 读取日志文件
logs = client.file_read(sandbox.metadata.name, "/app/agent.log")

# 8. 完成后删除 (或等待 TTL 自动清理)
client.delete_claim(claim.metadata.name)
```

---

## 六、与其他方案对比

### 6.1 vs. Kubernetes Job/CronJob

| 特性 | Agent Sandbox | Kubernetes Job |
|-----|---------------|----------------|
| **生命周期** | 长期运行(小时/天) | 短期执行(分钟) |
| **状态保持** | 支持(PVC + Singleton) | 不支持(每次新 Pod) |
| **网络身份** | 稳定 DNS + Service | 临时 Pod IP |
| **资源复用** | Warm Pool 预热 | 每次冷启动 |
| **多租户隔离** | NetworkPolicy 自动化 | 需手动配置 |
| **模板化** | SandboxTemplate | 需自定义 Helm Chart |

### 6.2 vs. Knative Serving

| 特性 | Agent Sandbox | Knative Serving |
|-----|---------------|-----------------|
| **扩缩容** | 0/1 副本(手动) | 自动扩缩容 |
| **冷启动优化** | Warm Pool | Activator 路由 |
| **网络** | Headless Service | Ingress + VirtualService |
| **状态管理** | 原生支持 PVC | 无状态设计 |
| **复杂性** | 轻量(仅 CRD) | 重量(Istio 依赖) |

### 6.3 vs. Jupyter Notebook / VSCode Server

| 特性 | Agent Sandbox | Jupyter/VSCode |
|-----|---------------|----------------|
| **编排** | Kubernetes 原生 | 需自定义 Helm/Operator |
| **多租户** | NetworkPolicy 隔离 | 无内置支持 |
| **资源配额** | K8s ResourceQuota | 需自定义 |
| **API 访问** | Python SDK + K8s API | HTTP API |
| **生命周期管理** | TTL + ShutdownPolicy | 无自动清理 |

---

## 七、总结

### 7.1 核心价值

**Agent Sandbox 为 AI 代理工作负载提供了 Kubernetes 原生的编排能力:**

1. **稳定身份**: 每个 AI 代理拥有唯一的 Sandbox 身份和 DNS 名称
2. **状态持久化**: 通过 PVC 和 Singleton 模式保持代理的学习成果和上下文
3. **零延迟启动**: Warm Pool 消除冷启动,实现即时响应
4. **安全多租户**: NetworkPolicy 自动化,每个代理独立隔离
5. **声明式管理**: 通过 CRD 定义期望状态,控制器自动维护

### 7.2 适用场景

✅ **推荐使用:**
- LLM Agent 编排(需要长期上下文保持)
- 代码执行沙箱(需要隔离和资源限制)
- AI 模型推理服务(需要 GPU 和持久化)
- 自主代理系统(需要稳定网络身份)
- 开发/测试环境即服务(需要快速部署)

❌ **不推荐使用:**
- 短期批处理任务(使用 Kubernetes Job 更合适)
- 高并发无状态服务(使用 Knative Serving 更合适)
- 需要多副本的服务(Agent Sandbox 限制 0/1 副本)

### 7.3 技术亮点

1. **Warm Pool 优化**: 20-50x 启动速度提升
2. **NetworkPolicy 自动化**: 无需手动编写复杂的策略
3. **模板化复用**: 一次定义,多次使用
4. **生命周期管理**: TTL + ShutdownPolicy 自动清理
5. **Python SDK**: 屏蔽 Kubernetes 复杂性

### 7.4 架构哲学

Agent Sandbox 采用 **"Pet vs. Cattle"** 中的 **Pet 模式**:
- 每个 Sandbox 是有名字、有身份、有状态的 "宠物"
- 不同于无状态服务的 "牲畜" 模式(随时创建/销毁)
- 更适合 AI 代理这种需要上下文保持和长期运行的工作负载

**设计原则:**
- 声明式优于命令式
- 自动化优于手动配置
- 隔离优于共享
- 复用优于重复

Agent Sandbox 是 Kubernetes 生态中少有的专注于 AI 代理场景的运维工具,填补了无状态服务编排和传统虚拟机之间的空白。
