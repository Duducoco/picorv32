# PicoRV32 RISCV-DV 验证环境

基于 [RISCV-DV](https://github.com/chipsalliance/riscv-dv) 的随机指令生成验证环境，使用 Spike ISS 作为参考模型，VCS 进行 RTL 仿真，通过 trace 对比验证 PicoRV32 指令执行的正确性。

## 目录结构

```
dv/
├── riscv-dv/              # RISCV-DV submodule
├── tb/
│   └── testbench_vcs.sv   # VCS testbench（含 RVFI trace 输出）
├── scripts/
│   ├── run_riscv_dv.py    # 主控脚本（生成→编译→Spike→VCS→对比）
│   ├── compile_test.py    # 汇编编译为 ELF/HEX
│   ├── spike_runner.py    # Spike ISS 运行器
│   └── compare_trace.py   # Trace 对比（strict / self-check）
├── cfg/
│   ├── riscv_core_setting.sv  # RISCV-DV 生成器 ISA 配置
│   ├── picorv32_isa.yaml      # ISA 描述
│   ├── testlist.yaml          # 测试列表
│   ├── picorv32_boot.S        # Boot 代码 + IRQ trap handler
│   ├── sections.lds           # 链接脚本
│   ├── user_define.h          # 宏替换（ecall→j write_tohost 等）
│   ├── user_init.s            # 用户初始化（j init 跳过 CSR boot）
│   └── vcs.f                  # VCS 编译选项
├── out/                   # 输出目录（git ignored）
└── Makefile
```

## 快速开始

### 依赖工具

| 工具 | 用途 |
|------|------|
| Synopsys VCS | RTL 仿真 + 覆盖率收集 |
| Spike ISS | 参考模型（`spike --isa=rv32imc_zicsr`） |
| RISC-V 工具链 | 交叉编译（`riscv64-unknown-elf-gcc`） |
| Python 3.6+ | 脚本运行 |

### 1. 初始化 RISCV-DV submodule

```bash
git submodule update --init --recursive
```

### 2. 编译 VCS

```bash
cd dv
make compile_vcs
```

### 3. 运行单个测试

```bash
make riscv_dv_test TEST=riscv_arithmetic_basic_test

# 指定随机种子（可复现）
make riscv_dv_test TEST=riscv_arithmetic_basic_test SEED=42
```

不指定 `SEED` 时每次使用随机种子，生成不同的测试用例。指定 `SEED` 可复现相同测试序列，便于调试。

### 4. 运行全部测试

```bash
for test in riscv_arithmetic_basic_test riscv_shift_test riscv_load_store_test \
            riscv_branch_test riscv_jump_test riscv_lui_auipc_test \
            riscv_rand_instr_test riscv_mul_div_test riscv_illegal_instr_test; do
    make riscv_dv_test TEST=$test
done
```

### 5. 合并覆盖率

```bash
make merge_cov
make cov_report
# 查看报告: out/cov_report/dashboard.html
```

## 验证流程

```
RISCV-DV 生成随机 .S 文件
    ↓
riscv64-unknown-elf-gcc 编译为 .elf/.hex
    ↓
┌─ Spike ISS 生成参考 trace (spike.log)
│      Spike 从 _start 启动，跳过 PicoRV32 自定义 boot 代码
├─ VCS 仿真生成 RTL trace (rtl.log)
│      PicoRV32 从 0x80000000 boot，执行完整程序
│      通过 RVFI 接口输出指令级 trace
└─→ compare_trace.py 对比两条 trace
    ↓
收集覆盖率 (line + cond + fsm + tgl + branch)
```

## 对比模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| **strict** | 逐条对比 Spike 与 RTL 的 PC、指令、寄存器写入 | 不触发异常的测试 |
| **self-check** | 仅验证 RTL 自身执行健全性（指令数、终止方式、死循环检测、PC 范围） | 可能触发异常的测试 |

strict 模式的对比处理：
- 过滤 RTL trace 中的 boot 代码和 IRQ handler 指令
- 去除 Spike trace 末尾的 `write_tohost` 无限循环
- 自动对齐两条 trace 的起始 PC
- 跳过 RTL 中含 X 值（未初始化位）的字段

## 测试列表

| 测试名 | 说明 | 对比模式 |
|--------|------|----------|
| `riscv_arithmetic_basic_test` | ADD, SUB, AND, OR, XOR, SLT, SLTU | strict |
| `riscv_shift_test` | SLL, SRL, SRA | strict |
| `riscv_load_store_test` | LW, LH, LB, LBU, LHU, SW, SH, SB | strict |
| `riscv_branch_test` | BEQ, BNE, BLT, BGE, BLTU, BGEU | strict |
| `riscv_jump_test` | JAL, JALR | self-check |
| `riscv_lui_auipc_test` | LUI, AUIPC | strict |
| `riscv_rand_instr_test` | 随机 RV32IMC 指令混合（2 iterations） | self-check |
| `riscv_mul_div_test` | MUL, MULH, MULHSU, MULHU | strict |
| `riscv_illegal_instr_test` | 非法指令异常恢复 | self-check |

## PicoRV32 特殊适配

### Boot 代码 (`cfg/picorv32_boot.S`)

PicoRV32 不支持标准 RISC-V trap/CSR 机制，使用自定义 IRQ 系统。boot 代码完成：

1. **IRQ 使能** — 通过 `maskirq` 自定义指令解除 irq[1]（非法指令）和 irq[2]（总线错误）的屏蔽
2. **IRQ handler** — 位于偏移 0x10，通过 q0/q2 寄存器保存恢复现场，清除压缩指令标记位后返回下一条指令
3. **x5(t0) 初始化** — 设置 `x5 = _start` 以匹配 Spike boot ROM 行为（Spike 将 t0 设为 `--pc` 值）

### 宏替换 (`cfg/user_define.h`)

- `ecall` → `j write_tohost`（PicoRV32 无标准 ecall 支持）
- `mret` → `nop`（无标准 trap return）

### 生成器限制 (`cfg/riscv_core_setting.sv`)

以下指令被排除在随机生成之外：
- CSR 指令（CSRRW/CSRRS/CSRRC 等）— 无标准 CSR 支持
- Trap 指令（ECALL/EBREAK/MRET 等）— 使用自定义异常机制
- FENCE/WFI — 不支持
- DIV/DIVU/REM/REMU — 已排除以规避除零后 CPU 卡死问题（MUL 系列正常）
- 未对齐访存 — `support_unaligned_load_store=0`（CATCH_MISALIGN 通过 IRQ handler 恢复，但会导致 Spike vs RTL trace 不一致）

### Testbench (`tb/testbench_vcs.sv`)

- 256KB 内存（0x80000000 ~ 0x8003FFFF）
- RVFI 接口输出指令级 trace
- 支持两种终止方式：ecall 指令 或 tohost 写入
- 100000 cycle 超时保护
- `+dump` plusarg 启用 VCD 波形输出

## 输出文件

每个测试在 `out/picorv32/<test_name>/` 下生成：

```
out/picorv32/<test_name>/
├── gen/                # RISCV-DV 生成的汇编
├── bin/
│   ├── test.elf        # ELF 可执行文件
│   ├── test.hex        # $readmemh 格式 HEX
│   └── test.dmp        # 反汇编
├── coverage/
│   ├── coverage.vdb    # VCS 覆盖率数据库
│   └── report/         # HTML 覆盖率报告
├── spike.log           # Spike 参考 trace
└── rtl.log             # RTL 仿真 trace
```

## 故障排查

### VCS 编译失败

检查 `cfg/vcs.f` 和 Makefile 中的路径配置。确保 `+define+RISCV_FORMAL` 已启用（RVFI 接口需要此宏）。

### Spike 运行失败

确认 Spike 安装并支持 rv32imc_zicsr：
```bash
spike --isa=rv32imc_zicsr --help
```

### Trace 不匹配

1. 查看 `out/picorv32/<test>/bin/test.dmp` 定位不匹配指令的汇编
2. 对比 `spike.log` 和 `rtl.log` 中对应 PC 处的寄存器值
3. 使用 `+dump` 启用 VCD 波形深入调试：
   ```bash
   # 在 run_riscv_dv.py 中 VCS 命令后加 +dump，或手动运行:
   ./out/build/simv +hex=<test.hex> +trace=rtl.log +dump
   ```

### 测试超时（TIMEOUT）

- 检查 testbench 中 `MAX_CYCLES` 参数（默认 100000）
- VCS 仿真的 `[TB]` 消息会打印到 stdout，运行脚本时可见

## 扩展

### 添加新测试

编辑 `cfg/testlist.yaml`：

```yaml
- test: my_custom_test
  description: "My custom test"
  gen_test: riscv_instr_base_test
  iterations: 1
  compare_mode: strict    # 或 self-check
  gen_opts: >
    +instr_cnt=200
    +num_of_sub_program=3
```

### 修改 ISA 配置

- 生成器配置：`cfg/riscv_core_setting.sv`
- ISA 描述：`cfg/picorv32_isa.yaml`
- Testbench 参数：`tb/testbench_vcs.sv` 中 PicoRV32 实例化参数
