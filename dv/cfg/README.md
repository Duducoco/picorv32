# PicoRV32 RISCV-DV 配置说明

## ISA 配置

根据你的 PicoRV32 参数设置，修改 `picorv32_isa.yaml` 中的 `supported_isa`：

| PicoRV32 参数 | ISA 配置 |
|--------------|---------|
| `ENABLE_MUL=0, ENABLE_DIV=0, COMPRESSED_ISA=0` | `RV32I` |
| `ENABLE_MUL=1, ENABLE_DIV=1, COMPRESSED_ISA=0` | `RV32IM` |
| `ENABLE_MUL=1, ENABLE_DIV=1, COMPRESSED_ISA=1` | `RV32IMC` |

## 测试列表

`testlist.yaml` 默认只包含 RV32I 基础指令测试。

如果启用了 M 扩展，可添加：
```yaml
- test: riscv_mul_div_test
  description: "Multiply/Divide instructions"
  gen_test: riscv_instr_base_test
  iterations: 1
  gen_opts: >
    +instr_cnt=100
```

如果启用了 C 扩展，可添加：
```yaml
- test: riscv_compressed_test
  description: "Compressed instructions"
  gen_test: riscv_instr_base_test
  iterations: 1
  gen_opts: >
    +instr_cnt=150
```

## 约束说明

PicoRV32 的限制已在配置中体现：
- 禁用所有浮点/向量扩展
- 禁用未实现的 CSR 寄存器
- 禁用 FENCE/WFI/ECALL/EBREAK 指令
- 禁用非对齐内存访问
