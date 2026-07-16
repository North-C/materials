# CubeSandbox arm64 8u16G Formal Benchmark Report

- Generated at: 2026-07-15 16:27:13 CST
- Remote workdir: `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846`
- Template ID: `tpl-bca9467038864260a79d908c`
- Template spec: `cpu=8000m,mem=16000Mi`
- Template status: `READY` / replica `READY`
- Image: `127.0.0.1:5000/cube-bench-suite:upstream-arm64@sha256:6b2a35715ad085bf5e96d19f8eb090377d9fff78c4ca2ed82a75324add8f7325`
- Registry digest: `127.0.0.1:5000/cube-bench-suite@sha256:6b2a35715ad085bf5e96d19f8eb090377d9fff78c4ca2ed82a75324add8f7325`
- Result dirs: memory `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/benchmark-results-memory-20260715-162130`, prime `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/benchmark-results-prime-20260715-160253`, runtime `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/benchmark-results-runtime-20260715-160918`

Note: the first all-in-one memory run timed out at the SDK HTTP read timeout. The final memory data below was collected as four independent Template/Sandbox runs with the same formal parameters, so each subtest has its own stdout/stderr/rc artifact.

## 1. Memory Read/Write

| mode | threads | block_size | total_size | transferred_MiB | throughput_MiB_s | ops_s | sysbench_time_s | lat_avg_ms | lat_p95_ms | rc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| seq-read | 2 | 1G | 100G | 102400.00 | 35187.89 | 34.36 | 2.9073 | 58.12 | 58.92 | 0 |
| seq-write | 2 | 1G | 100G | 102400.00 | 39376.87 | 38.45 | 2.5977 | 51.93 | 147.61 | 0 |
| rnd-read | 2 | 1G | 100G | 20480.00 | 618.51 | 0.60 | 33.1091 | 3303.72 | 3448.53 | 0 |
| rnd-write | 2 | 1G | 100G | 21504.00 | 657.58 | 0.64 | 32.6991 | 2990.50 | 3448.53 | 0 |

## 2. Prime Calculation

| cpu_max_prime | threads | time | events_s | total_events | sysbench_time_s | lat_avg_ms | lat_p95_ms |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1000 | 2 | 30s | 338562.17 | 10157943 | 30.0002 | 0.01 | 0.01 |
| 2000 | 2 | 30s | 117608.49 | 3528681 | 30.0003 | 0.02 | 0.02 |
| 3000 | 2 | 30s | 62937.96 | 1888360 | 30.0004 | 0.03 | 0.03 |
| 5000 | 2 | 30s | 31065.40 | 932059 | 30.0003 | 0.06 | 0.07 |
| 10000 | 2 | 30s | 12414.75 | 372478 | 30.0002 | 0.16 | 0.16 |
| 20000 | 2 | 30s | 5026.62 | 150813 | 30.0003 | 0.40 | 0.40 |
| 30000 | 2 | 30s | 2961.17 | 88844 | 30.0004 | 0.68 | 0.68 |
| 50000 | 2 | 30s | 1514.49 | 45440 | 30.0007 | 1.32 | 1.32 |
| 100000 | 2 | 30s | 603.75 | 18116 | 30.0034 | 3.31 | 3.30 |

## 3. Language Runtime Benchmarks

| benchmark | suite | params | value | unit | direction |
| --- | --- | --- | --- | --- | --- |
| Go build | golang.org/x/benchmarks | GO_BENCH_REPEATS=3 | 36211035016.67 | ns/op | lower is better |
| Go http | golang.org/x/benchmarks | GO_BENCH_REPEATS=3 | 10169.67 | ns/op | lower is better |
| Go json | golang.org/x/benchmarks | GO_BENCH_REPEATS=3 | 3950657.67 | ns/op | lower is better |
| Go garbage | golang.org/x/benchmarks | GO_BENCH_REPEATS=3 | 1755303.00 | ns/op | lower is better |
| PHP score | pantheon-systems/php-bench | PHPBENCH_ITERATIONS=2000000 | 749205 | score | higher is better |
| PHP total_time | pantheon-systems/php-bench | PHPBENCH_ITERATIONS=2000000 | 26.6950 | s | lower is better |
| Python json_dumps | python/pyperformance | PYPERFORMANCE_MODE=rigorous | 11.1 +- 0.1 | ms | lower is better |
| Python json_loads | python/pyperformance | PYPERFORMANCE_MODE=rigorous | 18.2 +- 0.2 | us | lower is better |
| Python python_startup | python/pyperformance | PYPERFORMANCE_MODE=rigorous | 9.51 +- 0.05 | ms | lower is better |
| Python richards | python/pyperformance | PYPERFORMANCE_MODE=rigorous | 67.4 +- 0.9 | ms | lower is better |
| Python scimark_fft | python/pyperformance | PYPERFORMANCE_MODE=rigorous | 297 +- 3 | ms | lower is better |
| Python scimark_lu | python/pyperformance | PYPERFORMANCE_MODE=rigorous | 142 +- 3 | ms | lower is better |
| Python scimark_monte_carlo | python/pyperformance | PYPERFORMANCE_MODE=rigorous | 86.1 +- 1.5 | ms | lower is better |
| Python scimark_sor | python/pyperformance | PYPERFORMANCE_MODE=rigorous | 173 +- 3 | ms | lower is better |
| Python scimark_sparse_mat_mult | python/pyperformance | PYPERFORMANCE_MODE=rigorous | 4.44 +- 0.04 | ms | lower is better |
| Node Octane score | dai-shi/benchmark-octane | default | 48328 | score | higher is better |
| Node Octane duration | dai-shi/benchmark-octane | default | 30.7510 | s | lower is supporting metric |
| Java SciMark Composite Score | mork-optimization/scimark 2.2 | -large | 2213.71 | score | higher is better |
| Java SciMark FFT | mork-optimization/scimark 2.2 | -large | 607.05 | score | higher is better |
| Java SciMark SOR | mork-optimization/scimark 2.2 | -large | 1202.77 | score | higher is better |
| Java SciMark Monte Carlo | mork-optimization/scimark 2.2 | -large | 1551.09 | score | higher is better |
| Java SciMark Sparse matmult | mork-optimization/scimark 2.2 | -large | 2136.11 | score | higher is better |
| Java SciMark LU | mork-optimization/scimark 2.2 | -large | 5571.52 | score | higher is better |

## 4. Execution Status

| case | rc | elapsed_sec | stdout_bytes | stderr_bytes |
| --- | --- | --- | --- | --- |
| 01-sysbench-memory-seq-read-formal | 0 | 3.905 | 1088 | 0 |
| 01-sysbench-memory-seq-write-formal | 0 | 3.612 | 1090 | 0 |
| 01-sysbench-memory-rnd-read-formal | 0 | 34.078 | 1085 | 0 |
| 01-sysbench-memory-rnd-write-formal | 0 | 33.671 | 1087 | 0 |
| 02-sysbench-prime-1000 | 0 | 30.016 | 894 | 0 |
| 02-sysbench-prime-2000 | 0 | 30.015 | 893 | 0 |
| 02-sysbench-prime-3000 | 0 | 30.016 | 891 | 0 |
| 02-sysbench-prime-5000 | 0 | 30.016 | 889 | 0 |
| 02-sysbench-prime-10000 | 0 | 30.014 | 891 | 0 |
| 02-sysbench-prime-20000 | 0 | 30.016 | 889 | 0 |
| 02-sysbench-prime-30000 | 0 | 30.013 | 888 | 0 |
| 02-sysbench-prime-50000 | 0 | 30.013 | 888 | 0 |
| 02-sysbench-prime-100000 | 0 | 30.016 | 888 | 0 |
| 03-go-benchmark-formal | 0 | 203.258 | 6453 | 1860 |
| 04-php-benchmark-formal | 0 | 26.744 | 4618 | 0 |
| 05-python-benchmark-formal | 0 | 349.74 | 12421 | 0 |
| 06-node-octane-formal | 0 | 30.838 | 3749 | 0 |
| 07-java-scimark-formal | 0 | 31.742 | 366 | 0 |

## 5. Artifacts

- Template creation JSON: `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/create-template.json`
- Template info JSON: `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/template-info.json`
- Prime tarball: `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/benchmark-results-prime-20260715-160253.tar.gz`
- Runtime tarball: `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/benchmark-results-runtime-20260715-160918.tar.gz`
- Memory tarballs:
  - `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/benchmark-results-memory-20260715-162130/sysbench-memory-seq-read-formal.tar.gz`
  - `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/benchmark-results-memory-20260715-162130/sysbench-memory-seq-write-formal.tar.gz`
  - `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/benchmark-results-memory-20260715-162130/sysbench-memory-rnd-read-formal.tar.gz`
  - `/home/lyq/cube-bench-formal-arm64-8c16g-20260715-154846/benchmark-results-memory-20260715-162130/sysbench-memory-rnd-write-formal.tar.gz`
