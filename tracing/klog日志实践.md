# 日志实践

[logging](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-instrumentation/logging.md)

对于公共的共享库，不应该使用日志，而是返回 error。

logging 当中使用较多的是：`klog.InfoS` and `klog.ErrorS`，原型如下：

```go
func InfoS(message string, keysAndValues ...interface{})
func InfoSDepth(depth int, message string, keysAndValues ...interface{})
func ErrorS(err error, message string, keysAndValues ...interface{})
func ErrorSDepth(depth int, err error, message string, keysAndValues ...interface{})
```
例子：
```go
klog.InfoS("Received HTTP request", "method", "GET", "URL", "/metrics", "latency", time.Second)
```

**原有的非结构化的 `klog.Infof()` 不推荐使用，尽量迁移到结构化的 `klog.InfoS()`上来。**两者的输出区别(第一行为 InfoF，第二行为 InfoS)：

```text
I0528 19:15:22.737538   47512 logtest.go:52] Pod kube-system/kube-dns status was updated to ready
I0528 19:15:22.737538   47512 logtest.go:52] "Pod status was updated" pod="kube-system/kube-dns" status="ready"
```

结构化的格式如下：

```text
Lmmdd hh:mm:ss.uuuuuu threadid file:line] msg...

where the fields are defined as follows:
	L                A single character, representing the log level (eg 'I' for INFO)
	mm               The month (zero padded; ie May is '05')
	dd               The day (zero padded)
	hh:mm:ss.uuuuuu  Time in hours, minutes and fractional seconds
	threadid         The space-padded thread ID as returned by GetTID()
	file             The file name
	line             The line number
	msg              The user-supplied message
```

**日志级别：**

```text
级别	含义
v=0	Generally useful for this to always be visible to a cluster operator.
v=1	A reasonable default log level if you don’t want verbosity.
v=2	Useful steady state information about the service and important log messages that may correlate to significant changes in the system.
This is the recommended default log level for most systems.
v=3	Extended information about changes.
v=4	Debug level verbosity.
v=5	Trace level verbosity.
v=6	Display requested resources.
v=7	Display HTTP request headers.
v=8	Display HTTP request contents.
v=9	Display HTTP request contents without truncation of contents.
```

---

[结构化klog](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-instrumentation/migration-to-structured-logging.md#structured-logging-in-kubernetes)

```text
Remove string formatting from log message

With structured logging, log messages are no longer formatted, leaving argument marshalling up to the logging client implementation. This allows messages to be a static description of event.

All string formatting (%d, %v, %w, %s) should be removed and log message string simplified. Describing arguments in log messages is no longer needed and should be removed leaving only a description of what happened.

Additionally we can improve messages to comply with good practices:

1. 大写字母开头 Start from a capital letter.  
2. 不要以句号结尾 Do not end the message with a period.
3. 使用主动语态 Use active voice. Use complete sentences when there is an acting subject ("A could not do B") or omit the subject if the subject would be the program itself ("Could not do B").
4. 使用过去式 Use past tense ("Could not delete B" instead of "Cannot delete B") 
5. 当引用对象时，说明对象的类型 When referring to an object, state what type of object it is. ("Deleted pod" instead of "Deleted")
```

## 细节 - `klog.InfoSDepth` 和 `klog.ErorSDepth` 方法

klog 中的 `klog.InfoSDepth` 和 `klog.ErorSDepth` 是针对结构化日志输出设计的扩展方法，其核心作用是为开发者提供更精细的**调用栈信息控制**和**日志层级管理**。以下是具体解析：

---

### 一、`klog.InfoSDepth` 的作用
1. **结构化日志输出**  
   与 `klog.InfoS` 类似，`InfoSDepth` 用于输出**键值对形式的结构化日志**，例如：  
   ```go
   klog.InfoSDepth(1, "Pod status updated", "pod", "kubedns", "status", "ready")
   ```
   输出示例：`"Pod status updated" pod="kubedns" status="ready"`。

2. **控制调用栈深度**  
   `Depth` 参数允许开发者指定**日志记录的调用位置**（Caller Frame）。例如：  
   • `klog.InfoSDepth(0, ...)` 记录当前调用位置的代码行（与 `klog.InfoS` 默认行为一致）。  
   • `klog.InfoSDepth(1, ...)` 会向调用栈上层移动一级，记录调用该日志语句的父函数位置。  
   这在封装日志工具时特别有用，可避免日志始终指向封装函数，而是指向实际业务代码的位置。

3. **适用场景**  
   当开发者需要**隐藏底层日志工具的实现细节**，或需要**在多层封装中准确定位日志来源**时，可通过调整 `Depth` 参数优化日志的可读性。

---

### 二、`klog.ErorSDepth` 的作用
1. **错误级别的结构化日志**  
   `ErorSDepth`（推测为 `ErrorSDepth`，可能存在拼写差异）是 `klog.ErrorS` 的扩展版本，用于输出**错误级别**的结构化日志。例如：  
   ```go
   klog.ErrorSDepth(1, errors.New("connection timeout"), "API call failed", "endpoint", "/healthz")
   ```
   输出示例：`"API call failed" err="connection timeout" endpoint="/healthz"`。

2. **调用栈深度控制**  
   与 `InfoSDepth` 类似，`ErrorSDepth` 的 `Depth` 参数允许调整错误日志的调用位置记录。例如：  
   • 在公共错误处理函数中调用 `ErrorSDepth(1)`，可使日志指向触发错误的业务代码行，而非公共函数内部。

3. **与日志级别结合**  
   错误日志通常属于 `ERROR` 或更高优先级，结合 `Depth` 参数可确保在复杂调用链中快速定位问题根源。

---

### 三、与 `klog.V(2).InfoS` 的对比
用户提到的 `klog.V(2).InfoS` 用于**动态控制日志详细程度**（需通过 `--v=2` 标志启用），而 `InfoSDepth`/`ErrorSDepth` 的核心差异在于：  
• **`V(level)` 控制的是日志的输出阈值**（是否显示），属于**全局日志级别管理**。  
• **`Depth` 参数控制的是日志的调用位置信息**，属于**日志元数据精准性优化**，与日志级别无关。

---

### 四、总结
• **`InfoSDepth`**：在结构化日志基础上，允许指定调用栈深度，优化日志位置信息的准确性。  
• **`ErrorSDepth`**：针对错误级别的结构化日志，提供相同的调用栈控制能力。  
• **适用场景**：适用于封装工具库、中间件或需要精确追踪日志来源的复杂项目。

通过合理使用这两个方法，开发者可以提升日志的可维护性和调试效率，尤其在微服务或分层架构中效果显著。

: 参考 klog 的 `InfoDepth` 和 `InfoS` 实现逻辑，`Depth` 参数通过调整调用栈偏移量决定日志位置记录。例如，`klog.InfoDepth(1, "msg")` 的日志位置会指向调用该方法的上一级函数（见示例输出中的 `proc.go:204`）。