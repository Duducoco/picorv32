# PicoRV32 RISCV-DV 验证环境

本目录包含基于 RISCV-DV 的随机指令生成验证环境，配合 Spike ISS 和 VCS 仿真器进行离线对比验证。

## 目录结构

```
dv/
├── riscv-dv/          # RISCV-DV submodule
├── tb/                # VCS testbench
│   └── testbench_vcs.sv
├── scripts/           # 验证脚本
│   ├── run_riscv_dv.py      # 主控脚本
│   ├── compile_test.py      # 测试编译
│   ├── spike_runner.py      # Spike 运行器
│   └── compare_trace.py     # Trace 对比
├── cfg/               # 配置文件
│   ├── picorv32_isa.yaml    # ISA 配置
│   ├── testlist.yaml        # 测试列表
│   ├── sections.lds         # 链接脚本
│   └── vcs.f                # VCS 文件列表
├── out/               # 输出目录（.gitignore）
└── Makefile
```

## 快速开始

### 1. 初始化 RISCV-DV submodule

```bash
git submodule update --init --recursive
```

### 2. 编译 VCS（带覆盖率）

```bash
make riscv_dv_compile
# 或从根目录
cd .. && make riscv_dv_compile
```

### 3. 运行单个测试

```bash
make riscv_dv_test TEST=riscv_arithmetic_basic_test
# 或从根目录
cd .. && make riscv_dv_test TEST=riscv_arithmetic_basic_test
```

### 4. 合并覆盖率并生成报告

```bash
# 运行多个测试后
make merge_cov
make cov_report
# 查看报告: out/cov_report/dashboard.html
```

## 验证流程

```
RISCV-DV (VCS 生成器) 生成 .S
    ↓
编译为 .elf/.hex
    ↓
Spike 生成参考 trace ──┐
    ↓                   ├─→ 对比
VCS 仿真生成 RTL trace ─┘
    ↓
收集覆盖率 (line+cond+fsm+tgl+branch)
```

## 可用测试

参见 `cfg/testlist.yaml`：

- `riscv_arithmetic_basic_test` - 基础算术指令
- `riscv_shift_test` - 移位指令
- `riscv_load_store_test` - 访存指令
- `riscv_branch_test` - 分支指令
- `riscv_jump_test` - 跳转指令
- `riscv_mul_div_test` - 乘除法指令
- `riscv_compressed_test` - 压缩指令
- `riscv_rand_instr_test` - 随机指令混合

## 依赖工具

- RISC-V 工具链：`riscv32-unknown-elf-gcc`
- Spike ISS：`spike`
- Synopsys VCS
- Python 3.6+

## 输出文件

每个测试在 `out/<test_name>/` 下生成：

```
out/<test_name>/
├── asm/           # RISCV-DV 生成的汇编
├── bin/           # 编译产物
│   ├── test.elf
│   ├── test.hex
│   └── test.dmp   # 反汇编
├── coverage/      # 覆盖率数据
│   ├── coverage.vdb      # 覆盖率数据库
│   └── report/           # 覆盖率报告
│       └── dashboard.html
├── spike.log      # Spike trace
└── rtl.log        # VCS trace
```

合并后的覆盖率：
```
out/
├── merged_coverage/    # 合并的覆盖率数据库
└── cov_report/         # 合并后的 HTML 报告
    └── dashboard.html
```

## 故障排查

### VCS 编译失败

检查 `cfg/vcs.f` 路径是否正确，确保 `+define+RISCV_FORMAL` 已启用。

### Spike 运行失败

确保 Spike 已安装且支持 RV32IMC：
```bash
spike --isa=rv32imc --help
```

### Trace 不匹配

查看 `out/<test_name>/test.dmp` 反汇编文件，对比 `spike.log` 和 `rtl.log`。

## 扩展

### 添加新测试

编辑 `cfg/testlist.yaml`：

```yaml
- test: my_custom_test
  description: "My custom test"
  iterations: 1
  gen_opts: >
    +instr_cnt=200
    +num_of_sub_program=3
```

### 修改 ISA 配置

编辑 `cfg/picorv32_isa.yaml` 调整支持的指令集和 CSR。
