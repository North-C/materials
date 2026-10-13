# 机器配置检测报告

## 192.168.25.90


### BIOS 配置

| 配置项 | 值 | 说明 |
| --- | --- | --- |
| BIOS 固件 | 10.79 | 发布日期 02/10/2026 |
| CPU 型号 | Kunpeng 950 7592C CPU @ 2.3GHz |  |
| CPU 核心 | 2 路 × 96 核 × 2 线程 = 384 逻辑 CPU | SMT 开启 (sysfs) |
| NUMA 节点分布 | 4 个 NUMA 节点 | node0: CPU 0-95; node1: CPU 96-191; node2: CPU 192-287; node3: CPU 288-383 |
| CPU 调频策略 (governor) | performance | 驱动: cppc_cpufreq; 频率范围 1200 ~ 2600 MHz |
| C-state (空闲态) | N.A. | cpuidle 未导出 (ARM 平台常见, 由固件管理) |
| 睿频/超频 (Turbo) | 开启 (推断) | 最大频率 2600 MHz > 基础频率 2300 MHz |

### OS 配置

| 配置项 | 值 | 说明 |
| --- | --- | --- |
| 发行版 | openEuler 24.03 (LTS-SP3) |  |
| 内核版本 | 6.6.0-9999.sp3.vnmi.xarray.d383a36d |  |
| 静态大页 (HugeTLB) | 未配置 |  |
| 透明大页 (THP) | always |  |
| numa_balancing 开关 | 0 (内核不做自动 NUMA 迁移) |  |

### 硬件配置

| 配置项 | 值 | 说明 |
| --- | --- | --- |
| 内存容量 | 24 × 96 GB = 2304 GB (2146 GiB) |  |
| 内存类型 | DDR5 |  |
| 内存频率 | 6400 MT/s |  |
| 磁盘 nvme0n1 | 3.5T \| NVMe SSD \| 未挂载 \| HWE62P443T8L005N |  |
| 磁盘 nvme3n1 | 2.9T \| NVMe SSD \| 数据盘 \| HWE6AP443T2M00KN | /usr/local/services/cubetoolbox/cubebox_os_image, /data/CubeMaster/storage, /data/cubelet |
| 磁盘 nvme1n1 | 2.9T \| NVMe SSD \| 系统盘 \| HWE6AP443T2M00KN | /boot/efi, /boot, /usr/local/services/cubetoolbox/cubeletmnt, / 等 6 个挂载点 |
| 磁盘 nvme2n1 | 5.8T \| NVMe SSD \| 未挂载 \| HWE72P456T4M000N |  |
| 数据盘汇总 | 1 块 | NVMe SSD \| 数据盘 \| HWE6AP443T2M00KN; 另有 2 块未挂载: nvme0n1, nvme2n1 |

