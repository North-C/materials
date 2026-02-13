# Background

`kubectl get pods`

> kubernetes - v1.25

kubectl 作为一个命令行客户端，支持

## 调用栈

```text
NewKubectlCommand(KubectlOptions)
|- matchVersionConfig = NewMatchVersionFlags()
|- f=cmdutil.NewFactory(matchVersionConfig)
|- groups := templates.CommandGroups{}             // 组合不同的子命令为group
|- NewCmdApply()           // 以 apply 命令为例子 - vendor/k8s.io/kubectl/pkg/cmd/apply/apply.go
    |- ToOptions()   // 将命令行参数转换为 Options
    |- Validate()   // 验证 --XXX 选项是否冲突
    |- Run()
        |- infos, err := GetObjects()
        |- applyOneObject()
```


## 资源对象

kubectl 在发送之前，会进行一系列的**参数检验**，防止发送错误的命令至 API-Server，增加不必要的压力。

在验证通过之后，kubectl 会以 **HTTP请求**的形式转发给API-Server。

使用 ResourceBuilder 构建对象：

```go
func (o *ApplyOptions) GetObjects() ([]*resource.Info, error) {
	var err error = nil
	if !o.objectsCached {
		r := o.Builder.
			Unstructured().         // 使用非结构化对象
			Schema(o.Validator).    // 应用 schema 验证
			ContinueOnError().
			NamespaceParam(o.Namespace).DefaultNamespace().
			FilenameParam(o.EnforceNamespace, &o.DeleteOptions.FilenameOptions).
			LabelSelectorParam(o.Selector).
			Flatten().
			Do()
		o.objects, err = r.Infos()
		o.objectsCached = true
	}
	return o.objects, err
}
```

整个的资源对象生成步骤：

1. 文件解析：读取 YAML/JSON 文件
2. 反序列化：转换为 unstructured.Unstructured 对象
3. Schema 验证：验证对象结构合法性
4. 元数据填充：设置命名空间、标签等
5. RESTMapping 解析：确定 API 版本和资源类型

```go
// resource.Info 是资源对象的核心表示
type Info struct {
    Client      rest.Interface
    Mapping     *meta.RESTMapping
    Namespace   string
    Name        string
    Source      string
    Object      runtime.Object  // 实际的 Kubernetes 对象
}
```

## 创建与发送HTTP请求

在 apply 命令中，会首先创建一个Helper辅助创建：
```go
helper := resource.NewHelper(info.Client, info.Mapping).
		DryRun(o.DryRunStrategy == cmdutil.DryRunServer).
		WithFieldManager(o.FieldManager).
		WithFieldValidation(o.ValidationDirective)
```

按照不同场景，可以构造不同的 HTTP方法：
* `POST`：创建新资源 (`helper.Create`)
* `PATCH`：更新现有资源 (`helper.Patch`)
* `GET`：获取当前状态 (`info.Get`)

**对应用进行编码**

```go
// 服务端应用时的对象编码
data, err := runtime.Encode(unstructured.UnstructuredJSONScheme, info.Object)
```
其中：`runtime.Object` 是所有 Kubernetes 对象的通用接口，`unstructured.Unstructured`是动态类型，可表示任意 Kubernetes 资源，`UnstructuredJSONScheme`：是JSON 序列化方案。

希望将请求发送至服务端时，调用`Patch`方法构建HTTP请求对象(`rest.Request`)，并且进行发送：

```go
options := metav1.PatchOptions{
    Force: &o.ForceConflicts,
}
obj, err := helper.Patch(
    info.Namespace,
    info.Name,
    types.ApplyPatchType,    // "application/apply-patch+yaml"
    data,                    // 序列化后的对象数据
    &options,
)
```

helper.Patch()方法在内部执行了三个步骤：
* HTTP 请求对象的构建
* 网络请求的发送
* 响应的接收和解析

成功后，返回解析后的 Kubernetes 对象。

构建出的服务端请求的实例类似于：

```text
PATCH /api/v1/namespaces/default/pods/my-pod?fieldManager=kubectl-client-side-apply
Content-Type: application/apply-patch+yaml
Authorization: Bearer <token>

apiVersion: v1
kind: Pod
metadata:
  name: my-pod
  namespace: default
spec:
  containers:
  - name: app
    image: nginx:1.20
```

发送请求除去的过程是：
```text
kubectl apply
    ↓
helper.Patch()
    ↓
RESTClient.Patch()
    ↓
Request.Do()
    ↓
Request.request()
    ↓
Request.newHTTPRequest()  // 创建 *http.Request
    ↓
http.Client.Do()         // 标准库发送 HTTP 请求
    ↓
Transport.RoundTrip()    // 底层传输
    ↓
网络发送到 API Server
```