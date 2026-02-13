# bugfix-ExecSync

`bugfix-ExecSync`

Exec 接口下，我们

## 源代码对比

通过 golang-1.7.13 下的 httputils/reverseproxy.go 与 koordinator 下reverseproxy.go 进行对比，主要区别有如下几点：

https://cs.opensource.google/go/go/+/refs/tags/go1.20:src/net/http/httputil/reverseproxy.go;l=794

1. 修改了`func upgradeType(h http.Header) string`，将返回值`h.Get("Upgrade")`全部改为小写

```go
< 	return strings.ToLower(h.Get("Upgrade"))
---
> 	return h.Get("Upgrade")
```

2. 增加输入和输出两面channel信息，分离输入和输出通道。

```go
616,617c608
< 	stdoutDone := make(chan error)
< 	stdinDone := make(chan struct{})
---
> 	errc := make(chan error, 1)
619,631c610,612
< 	go func() {
< 		spc.copyToBackend()
< 		if c, ok := backConn.(CloseWriter); ok {
< 			c.CloseWrite()
< 		}
< 		close(stdinDone)
< 	}()
< 	go spc.copyFromBackend(stdoutDone)
< 	select {
< 	case <-stdoutDone:
< 	case <-stdinDone:
< 		<-stdoutDone
< 	}
---
> 	go spc.copyToBackend(errc)
> 	go spc.copyFromBackend(errc)
> 	<-errc
```

3. 增加了CloseWriter接口，关闭数据写入通道后但是依旧可以接收响应。

```go
< // CloseWriter implement CloseWrite method
< type CloseWriter interface {
< 	CloseWrite() error
< }
< 
```

## 测试与验证

