# CubeSandbox Benchmark Image

This image is prepared for CubeSandbox template creation and uses upstream
open-source benchmark projects where available. Custom code in this image is
limited to the CubeSandbox health probe and thin command wrappers.

Template flags:

```bash
cubemastercli tpl create-from-image \
  --image <registry>/cube-bench-suite:<tag> \
  --writable-layer-size 1G \
  --expose-port 49983 \
  --expose-port 49999 \
  --probe 49983 \
  --probe-path /health
```

Runtime entrypoint:

```bash
/opt/cube-bench/bin/run-benchmark <case>
```

Cases:

- `sysbench-memory`: upstream sysbench memory workload, configurable read/write and seq/rnd.
- `sysbench-memory-all`: runs seq-read, seq-write, rnd-read, rnd-write memory workloads.
- `sysbench-prime`: upstream sysbench CPU prime workload, using `--cpu-max-prime`.
- `sysbench-prime-matrix`: runs sysbench prime for `1000,2000,3000,5000,10000,20000,30000,50000,100000` by default.
- `go-benchmark`: upstream `golang.org/x/benchmarks` build/http/json/garbage by default; `GO_BENCH_DISABLE_PERF=1` disables the upstream build profiler.
- `php-benchmark`: upstream PHPBench 0.8.1 Pantheon fork.
- `python-benchmark`: upstream `python/pyperformance`.
- `node-octane`: upstream `dai-shi/benchmark-octane`.
- `java-scimark`: upstream `mork-optimization/scimark` SciMark 2.2 jar.
- `all`: smoke-run all benchmark groups with shortened defaults.
- `formal`: runs the formal suite with fixed memory parameters, prime matrix, and formal runtime settings.

Source commits and tarball checksums are recorded in `/opt/cube-bench/SOURCES.md`.

Default service:

- Starts envd on port `49983`; SDK command execution depends on this service.
- Starts an HTTP probe server on port `49999`.
- `GET /health` on `49983` returns 204 from envd.
- `GET /health` on `49999` returns 200 from the benchmark probe server.
- `GET /benchmarks` on `49999` returns the benchmark case list.
