# kubectl cp <host-file-path> <pod>:<file-path> 失败

## 环境信息

版本：
* AMD64
* Linux
* Kubernetes
* Docker
* Runtime-proxy
* golang v1.23.6

## 异常复现


## ReverseProxy 反向代理

在创建`ReverseProxy`时，使用的是如下代码，只针对Transport和Director进行设置，即响应修改和请求转发。

```go
func ReverseProxy(containerRuntimeEndpoint string) *httputil.ReverseProxy {
	return &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			param := ""
			if len(req.URL.RawQuery) > 0 {
				param = "?" + req.URL.RawQuery
			}
			u, _ := url.Parse("http://docker" + req.URL.Path + param)
			*req.URL = *u
		},
		Transport: &http.Transport{
			DialContext: func(_ context.Context, _, _ string) (net.Conn, error) {
				return net.Dial("unix", containerRuntimeEndpoint)
			}},
	}
}
```

> 创建时定义了 Transport，如果未定义将使用`DefaultTransport`。

之后，调用 `reverseproxy.ServeHTTP()`进行监听和转发，在其中通过定义的 RoundTrip()发送时用：

```go
func (p *ReverseProxy) ServeHTTP(rw http.ResponseWriter, req *http.Request) {
    transport := p.Transport
    if transport == nil {
        transport = http.DefaultTransport
    }

    ...

    res, err := transport.RoundTrip(outreq)  // 发送一次请求
    roundTripMutex.Lock()
    roundTripDone = true
    roundTripMutex.Unlock()
    if err != nil {
        p.getErrorHandler()(rw, outreq, err)
        return
    }

    // Deal with 101 Switching Protocols responses: (WebSocket, h2c, etc)
    if res.StatusCode == http.StatusSwitchingProtocols {
        if !p.modifyResponse(rw, res, outreq) {
            return
        }
        // 处理Upgrade机制获取到的响应
        p.handleUpgradeResponse(rw, outreq, res)
        return
    }

    ...
}
```

在 ServeHTTP中调用到 `net/http/roundtrip.go` 中的 `Transport.RoundTrip()` 方法。

```go
// RoundTrip implements the [RoundTripper] interface.
//
// For higher-level HTTP client support (such as handling of cookies
// and redirects), see [Get], [Post], and the [Client] type.
//
// Like the RoundTripper interface, the error types returned
// by RoundTrip are unspecified.
func (t *Transport) RoundTrip(req *Request) (*Response, error) {
	if t == nil {
		panic("transport is nil")
	}
	return t.roundTrip(req)
}
```

进入到 `net/http/transport.go`完成一次请求发送和响应接收：

```go
// roundTrip implements a RoundTripper over HTTP.
func (t *Transport) roundTrip(req *Request) (_ *Response, err error) {
    // 初始化参数
    // 参数合法性检查
    // 如果请求带 Body，包装成 *readTrackingBody，支持重放（用于重试）
    // 是否注册alternateRoundTripper,用于 HTTP/2 注册
    // 构造不可重试的 context.WithCancelCause，负责整个生命周期的取消
    ctx, cancel := context.WithCancelCause(req.Context())
    // 任何错误返回前都需要 cancel(err)，保证清理上下文
    defer func() {
		if err != nil {
			cancel(err)
		}
	}()

    // 无限for循环处理
    for {
        // t.getConn 拿一条“持久连接” persistConn（HTTP/1 或 HTTP/2）
        // 如果已有idle的可用连接，则直接使用，若没有，则dialConn进行连接。
        pconn, err := t.getConn(treq, cm)

        // 依据 HTTP/1或HTTP/2 发送请求
        if pconn.alt != nil {
			// HTTP/2 path.
			resp, err = pconn.alt.RoundTrip(req)
		} else {
			resp, err = pconn.roundTrip(treq)
		}
        // 可重试的错误 和不可重试的错误处理
        ...
    }
}
```

`Transport`
```go
getConn -> queueForDial -> startDialConnForLocked -> dialConnFor -> dialConn -> persistConn.readLoop
```

`persistConn` 的读循环中，会新建 Response：

```go
readLoop -> readResponse

// 读取一个HTTP Response
func (pc *persistConn) readResponse(rc requestAndChan, trace *httptrace.ClientTrace) (resp *Response, err error) {
    ...
    if resp.isProtocolSwitch() {
        resp.Body = newReadWriteCloserBody(pc.br, pc.conn)
    }
    ...
}
```

在这里，不同于一般的Response.Body的`io.ReadCloser`类型，而是增加和`io.Write`接口，构成`io.ReadWriteCloser`。在ReverseProxy的代码中，关闭 backend connection时，希望转换为 CloseWriter接口，并使用 CloseWrite() 进行半关闭，也就是来源于此。在早先的版本当中，并没有为该结构体定义`CloseWrite()`方法，导致实际上并不能成功调用。

```go
func newReadWriteCloserBody(br *bufio.Reader, rwc io.ReadWriteCloser) io.ReadWriteCloser {
	body := &readWriteCloserBody{ReadWriteCloser: rwc}
	if br.Buffered() != 0 {
		body.br = br
	}
	return body
}

// readWriteCloserBody is the Response.Body type used when we want to
// give users write access to the Body through the underlying
// connection (TCP, unless using custom dialers). This is then
// the concrete type for a Response.Body on the 101 Switching
// Protocols response, as used by WebSockets, h2c, etc.
type readWriteCloserBody struct {
	_  incomparable
	br *bufio.Reader // used until empty
	io.ReadWriteCloser
}

func (b *readWriteCloserBody) Read(p []byte) (n int, err error) {
	if b.br != nil {
		if n := b.br.Buffered(); len(p) > n {
			p = p[:n]
		}
		n, err = b.br.Read(p)
		if b.br.Buffered() == 0 {
			b.br = nil
		}
		return n, err
	}
	return b.ReadWriteCloser.Read(p)
}

// 在 v1.25版本中添加
func (b *readWriteCloserBody) CloseWrite() error {
	if cw, ok := b.ReadWriteCloser.(interface{ CloseWrite() error }); ok {
		return cw.CloseWrite()
	}
	return fmt.Errorf("CloseWrite: %w", ErrNotSupported)
}
```

---

请求接收到之后，会对 Upgrade 机制下的 Response 进行传输。

```go
func (p *ReverseProxy) handleUpgradeResponse(rw http.ResponseWriter, req *http.Request, res *http.Response) {
    ...

    backConn, ok := res.Body.(io.ReadWriteCloser)
    ...

    rc := http.NewResponseController(rw)
	conn, brw, hijackErr := rc.Hijack()
    ...

    copyHeader(rw.Header(), res.Header)
    
    // 将响应的头部写入到 client侧
    res.Header = rw.Header()
	res.Body = nil // so res.Write only writes the headers; we have res.Body in backConn above
	if err := res.Write(brw); err != nil {
		p.getErrorHandler()(rw, req, fmt.Errorf("response write: %v", err))
		return
	}
	if err := brw.Flush(); err != nil {
		p.getErrorHandler()(rw, req, fmt.Errorf("response flush: %v", err))
		return
	}
    // 下面代码为 koordinator 基于初始代理的修改
    stdoutDone := make(chan error)
	stdinDone := make(chan struct{})
	spc := switchProtocolCopier{user: conn, backend: backConn}
	go func() {
		spc.copyToBackend()
		if c, ok := backConn.(CloseWriter); ok {
            // 在此处增加日志
			c.CloseWrite()
		} else {
            // 在此处增加日志打印，可以发现 backConn 无法转换为 CloseWriter 接口
        }
		close(stdinDone)
	}()
	go spc.copyFromBackend(stdoutDone)
	select {
	case <-stdoutDone:
	case <-stdinDone:
		<-stdoutDone
	}
	return

}

// CloseWriter implement CloseWrite method
type CloseWriter interface {
	CloseWrite() error
}

// switchProtocolCopier exists so goroutines proxying data back and
// forth have nice names in stacks.
type switchProtocolCopier struct {
	user, backend io.ReadWriter
}

func (c switchProtocolCopier) copyFromBackend(errc chan<- error) {
	_, err := io.Copy(c.user, c.backend)
	errc <- err
}

func (c switchProtocolCopier) copyToBackend() error {
	_, err := io.Copy(c.backend, c.user)
	return err
}
```

---

额外部分 - 看看 ReverseProxy的内容：

```go
type ReverseProxy struct {
    // 请求发出前“改包”,Go1.20之后的新版
    Rewrite func(*ProxyRequest)
    // 请求发出前“改包”，以前的旧版接口
    Director func(*http.Request)
    // 真正发请求的 RoundTripper，默认用 http.DefaultTransport
    Transport http.RoundTripper

    FlushInterval time.Duration

    ErrorLog *log.Logger

	BufferPool BufferPool
    // 后端响应返回后“改响应”
    ModifyResponse func(*http.Response) error
    // 后端连不上或 ModifyResponse 失败时走这里，默认 502
	ErrorHandler func(http.ResponseWriter, *http.Request, error)
}
```

它的作用可以概括，就是**把进来的请求原封不动（或稍加改写）转给后端，再把后端响应原路抄回客户端**,或者说，**ReverseProxy = “自带连接池、自动 X-Forwarded、自动删 hop 头、可插拔改写、支持流式、默认 502 错误”的反向代理利器。**

```text
客户端 → http.Server → ReverseProxy.ServeHTTP → Transport → 后端
                        ↑                              ↓
                   可选拦截/改写                可选拦截/改写
                        ↑                              ↓
                   ModifyResponse/ErrorHandler ← 后端响应
```

在 kubectl exec/cp 当中，会在 http 头部增加 Upgrade，表示升级协议为 SPDY/Websocket。


## net/http

net/http库中的几个基本概念：RoundTripper、Transport、io.ReadWriteCloser.

**RoundTrip - 把请求发出去，把响应拿回来，别做多余的事，且必须并发安全。**
```go
type RoundTripper interface {
	RoundTrip(*Request) (*Response, error)
}
```

- 接口职能：RoundTripper 负责把 `*http.Request` 变成 `*http.Response`。它只关心**“这一次”** HTTP 请求/响应的比特传输，不关心重定向、认证、Cookie、缓存等高层逻辑。
- 实现该接口需要保证 goroutine 的并发安全性。
- 对于接口的返回值，`err != nil` 仅仅表示**没有获取到响应**。
- 禁止修改 Request 的内容，只允许进行读取和关闭 `Request.Body`。
- 确保关闭：即使 RoundTrip 返回错误，也必须保证最终 Response.Body.Close() 会被调用（可以异步）

看到 reverseproxy当中使用到的`http.Response`，

```go
// Response represents the response from an HTTP request.
// Header 部分保存在内存中，一旦出现就会返回，Body 部分是边读边来的流
type Response struct {
	Status     string // e.g. "200 OK"
	StatusCode int    // e.g. 200
	Proto      string // e.g. "HTTP/1.0"
	ProtoMajor int    // e.g. 1
	ProtoMinor int    // e.g. 0

	Header Header

	// Body represents the response body.
    // 注释中提到：在成功的 "101 Switching Protocols"响应中，会为Body实现 io.Writer接口
	Body io.ReadCloser

	ContentLength int64

	TransferEncoding []string

	Close bool

	Uncompressed bool

	Trailer Header

	Request *Request

	TLS *tls.ConnectionState
}
```
