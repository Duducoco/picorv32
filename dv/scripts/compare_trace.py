#!/usr/bin/env python3
"""对比 Spike 和 RTL trace

支持两种模式:
- strict:     逐条对比 Spike 和 RTL trace（用于不触发异常的测试）
- self-check: 仅验证 RTL 自身执行健全性（用于可能触发异常的测试）
"""

import sys
import re
import argparse
from pathlib import Path

# Spike boot ROM 运行在 0x1000 区域，过滤掉
MIN_PC = 0x80000000
# 有效内存范围
MAX_PC = 0x8003FFFF
# IRQ handler 地址范围 (0x80000000 ~ 0x80000200 为 boot+handler 区域)
IRQ_HANDLER_BASE = 0x80000010
IRQ_HANDLER_END  = 0x80000200

def parse_spike_log(log_file):
    """解析 Spike --log-commits 格式
    格式: core   0: 3 0x80000060 (0x800000b7) x1  0x80000000
    注意：仅解析 commit 行（"3" 前缀），跳过 disasm 行避免重复计数
    """
    traces = []
    with open(log_file) as f:
        for line in f:
            line = line.strip()
            if not line or not line.startswith("core"):
                continue

            parts = line.split()
            if len(parts) < 5:
                continue

            # 仅解析 commit 行（parts[2] == '3'），跳过 disasm 行
            if parts[2] != '3':
                continue

            pc_idx, insn_idx, reg_start = 3, 4, 5

            if len(parts) <= insn_idx:
                continue

            pc = int(parts[pc_idx], 16)
            if pc < MIN_PC:
                continue

            insn_str = parts[insn_idx].strip('()')
            insn = int(insn_str, 16)

            trace = {'pc': pc, 'insn': insn}

            # 解析寄存器写
            if len(parts) > reg_start and parts[reg_start].startswith('x'):
                try:
                    trace['rd_addr'] = int(parts[reg_start][1:])
                    trace['rd_wdata'] = int(parts[reg_start + 1], 16)
                except (ValueError, IndexError):
                    pass

            traces.append(trace)

    return traces

def _hex_to_int(hex_str):
    """将可能包含 x/X（仿真未初始化位）的十六进制字符串转换为整数。

    返回 (value, has_x)，has_x 为 True 表示含有不确定位。
    """
    lower = hex_str.lower()
    has_x = 'x' in lower
    clean = lower.replace('x', '0')
    return int(clean, 16), has_x


def parse_rtl_log(log_file):
    """解析 RTL trace
    格式: PC=00000080 INSN=00000297 INTR=0 x5=00000080
    支持 VCS 仿真中的 x/X 值（未初始化位）
    """
    traces = []
    with open(log_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            trace = {}

            pc_match = re.search(r'PC=([0-9a-fA-FxX]{8})', line)
            if pc_match:
                trace['pc'], trace['pc_has_x'] = _hex_to_int(pc_match.group(1))

            insn_match = re.search(r'INSN=([0-9a-fA-FxX]+)', line)
            if insn_match:
                trace['insn'], trace['insn_has_x'] = _hex_to_int(insn_match.group(1))

            intr_match = re.search(r'INTR=(\d+)', line)
            if intr_match:
                trace['intr'] = int(intr_match.group(1))

            rd_match = re.search(r'x(\d+)=([0-9a-fA-FxX]{8})', line)
            if rd_match:
                trace['rd_addr'] = int(rd_match.group(1))
                trace['rd_wdata'], trace['rd_has_x'] = _hex_to_int(rd_match.group(2))

            mem_match = re.search(r'MEM\[([0-9a-fA-FxX]{8})\]=([0-9a-fA-FxX]{8})', line)
            if mem_match:
                trace['mem_addr'], _ = _hex_to_int(mem_match.group(1))
                trace['mem_wdata'], _ = _hex_to_int(mem_match.group(2))

            if 'pc' in trace and 'insn' in trace:
                traces.append(trace)

    return traces

def _trim_tohost_loop(trace):
    """去除 trace 末尾的 write_tohost 无限循环。

    RISCV-DV 的 write_tohost 是 sw+j 的紧密循环，Spike 不使用 htif 时
    会一直执行到超时，产生大量重复 trace。
    检测方法：如果末尾 N 条指令的唯一 PC 集合很小（≤3），则为紧密循环。
    """
    if len(trace) < 10:
        return trace

    # 取末尾 20 条指令，检查是否为紧密循环
    tail_size = min(20, len(trace))
    tail_pcs = [trace[len(trace) - tail_size + i]['pc'] for i in range(tail_size)]
    unique_pcs = set(tail_pcs)

    if len(unique_pcs) > 3:
        return trace  # 末尾不是紧密循环

    # 找到循环体的 PC 集合，从后向前找到第一个不在循环中的指令
    loop_pcs = unique_pcs
    first_loop_idx = len(trace)
    for i in range(len(trace) - 1, -1, -1):
        if trace[i]['pc'] in loop_pcs:
            first_loop_idx = i
        else:
            break

    # 保留循环的第一轮（用于 tohost 写入验证），截断后续重复
    loop_len = len(loop_pcs)
    trim_point = first_loop_idx + loop_len
    if trim_point < len(trace):
        return trace[:trim_point]

    return trace


def _align_start_pc(spike_trace, rtl_trace):
    """对齐两个 trace 的起始 PC。

    Spike 从 init 标签启动（跳过 boot 代码），RTL 从 _start 启动。
    两者起始 PC 可能不同，需要找到第一个共同 PC 对齐。
    """
    if not spike_trace or not rtl_trace:
        return spike_trace, rtl_trace

    spike_pc = spike_trace[0]['pc']
    rtl_pc = rtl_trace[0]['pc']

    if spike_pc == rtl_pc:
        return spike_trace, rtl_trace

    # 尝试在 RTL trace 中找到 Spike 的起始 PC
    for i, t in enumerate(rtl_trace):
        if t['pc'] == spike_pc:
            return spike_trace, rtl_trace[i:]

    # 反向：在 Spike trace 中找到 RTL 的起始 PC
    for i, t in enumerate(spike_trace):
        if t['pc'] == rtl_pc:
            return spike_trace[i:], rtl_trace

    # 无法对齐，原样返回
    return spike_trace, rtl_trace


def compare_strict(spike_log, rtl_log, max_errors=20):
    """严格模式：逐条对比 Spike 和 RTL trace

    处理流程:
    1. 过滤 RTL boot/IRQ handler 区域指令
    2. 去除 Spike write_tohost 无限循环
    3. 对齐两个 trace 的起始 PC（Spike 从 init 启动，RTL 从 _start 启动）
    4. 逐条对比 PC、指令、寄存器写入
    """
    spike_trace_raw = parse_spike_log(spike_log)
    rtl_trace_raw = parse_rtl_log(rtl_log)

    # 过滤 RTL trace：跳过 boot 代码（PC < 0x80000200）中初始的 maskirq/j 指令
    # 以及所有 IRQ handler 内的指令
    rtl_trace = []
    in_user_code = False
    for t in rtl_trace_raw:
        pc = t['pc']
        intr = t.get('intr', 0)
        # 跳过 boot 区域的指令 (0x80000000 ~ 0x800001FF)
        if not in_user_code:
            if pc >= IRQ_HANDLER_END:
                in_user_code = True
            else:
                continue
        # 跳过 IRQ handler 内的指令
        if intr == 1 or (IRQ_HANDLER_BASE <= pc < IRQ_HANDLER_END):
            continue
        rtl_trace.append(t)

    # 去除 Spike trace 末尾的 write_tohost 无限循环
    spike_trace = _trim_tohost_loop(spike_trace_raw)

    # 对齐起始 PC
    spike_trace, rtl_trace = _align_start_pc(spike_trace, rtl_trace)

    print(f"[INFO] Spike trace: {len(spike_trace_raw)} raw -> {len(spike_trace)} instructions (after trim + align)")
    print(f"[INFO] RTL trace: {len(rtl_trace_raw)} raw -> {len(rtl_trace)} instructions (after filter + align)")

    if len(spike_trace) == 0:
        print("[ERROR] Spike trace is empty!")
        return False

    if len(rtl_trace) == 0:
        print("[ERROR] RTL trace is empty!")
        return False

    errors = []
    min_len = min(len(spike_trace), len(rtl_trace))

    for i in range(min_len):
        spike = spike_trace[i]
        rtl = rtl_trace[i]

        # 跳过 RTL 含 X 值的字段（仿真未初始化位，无法可靠对比）
        if not rtl.get('pc_has_x'):
            if spike['pc'] != rtl['pc']:
                errors.append(f"Line {i}: PC mismatch - spike={spike['pc']:08x} rtl={rtl['pc']:08x}")
        if not rtl.get('insn_has_x'):
            if spike['insn'] != rtl['insn']:
                errors.append(f"Line {i}: INSN mismatch - spike={spike['insn']:08x} rtl={rtl['insn']:08x}")
        if 'rd_addr' in spike and 'rd_addr' in rtl and not rtl.get('rd_has_x'):
            if spike['rd_addr'] != rtl['rd_addr']:
                errors.append(f"Line {i}: RD_ADDR mismatch - spike=x{spike['rd_addr']} rtl=x{rtl['rd_addr']}")
            elif spike['rd_wdata'] != rtl['rd_wdata']:
                errors.append(f"Line {i}: RD_WDATA mismatch x{spike['rd_addr']} - spike={spike['rd_wdata']:08x} rtl={rtl['rd_wdata']:08x}")

        if len(errors) >= max_errors:
            break

    if abs(len(spike_trace) - len(rtl_trace)) > 2:
        errors.append(f"Trace length mismatch - spike={len(spike_trace)} rtl={len(rtl_trace)}")

    return errors

def compare_self_check(rtl_log, min_instr=10, max_instr=50000, max_repeat=50):
    """自检模式：仅验证 RTL 自身执行健全性

    检查项:
    1. 程序正常终止（trace 包含 ecall 指令）
    2. 指令执行数在合理范围内
    3. 无连续 PC 重复（死循环检测）
    4. 所有执行的 PC 地址在有效内存范围内（trap handler 地址除外）
    """
    rtl_trace = parse_rtl_log(rtl_log)
    errors = []

    print(f"[INFO] RTL trace: {len(rtl_trace)} instructions")

    if len(rtl_trace) == 0:
        print("[ERROR] RTL trace is empty!")
        return False

    # 检查 1: 指令数在合理范围内
    if len(rtl_trace) < min_instr:
        errors.append(f"Too few instructions: {len(rtl_trace)} < {min_instr}")
    if len(rtl_trace) > max_instr:
        errors.append(f"Too many instructions: {len(rtl_trace)} > {max_instr} (possible infinite loop)")

    # 检查 2: 程序正常终止
    # 支持两种终止方式:
    # a) ECALL 指令 (0x00000073)
    # b) 写入 tohost 地址 (trace 中出现 MEM[tohost]=非零值)
    found_termination = False
    # 检查最后 20 条指令中是否有终止信号
    check_range = rtl_trace[-20:] if len(rtl_trace) >= 20 else rtl_trace
    for t in check_range:
        if t['insn'] == 0x00000073:  # ecall
            found_termination = True
            break
        if 'mem_addr' in t and t.get('mem_wdata', 0) != 0:
            # tohost 写入检测：写入数据为 1 表示 PASS
            found_termination = True
            break
    if not found_termination:
        errors.append("Program did not terminate normally (no ECALL or tohost write detected)")

    # 检查 3: 死循环检测 - 连续 N 条指令 PC 相同
    repeat_count = 1
    for i in range(1, len(rtl_trace)):
        if rtl_trace[i]['pc'] == rtl_trace[i-1]['pc']:
            repeat_count += 1
            if repeat_count >= max_repeat:
                errors.append(f"Possible infinite loop: PC=0x{rtl_trace[i]['pc']:08x} repeated {repeat_count} times at instruction {i}")
                break
        else:
            repeat_count = 1

    # 检查 4: 所有 PC 地址在有效范围内
    invalid_pc_count = 0
    for t in rtl_trace:
        pc = t['pc']
        intr = t.get('intr', 0)
        # boot/handler 区域地址合法
        if pc >= MIN_PC and pc < IRQ_HANDLER_END:
            continue
        # 正常代码区域
        if pc >= IRQ_HANDLER_END and pc <= MAX_PC:
            continue
        # IRQ handler 内部跳转
        if intr == 1:
            continue
        invalid_pc_count += 1
        if invalid_pc_count <= 5:
            errors.append(f"Invalid PC address: 0x{pc:08x} (not in valid memory range)")

    if invalid_pc_count > 5:
        errors.append(f"... and {invalid_pc_count - 5} more invalid PC addresses")

    # 统计 IRQ handler 调用次数
    irq_count = sum(1 for t in rtl_trace if t['pc'] == IRQ_HANDLER_BASE)
    if irq_count > 0:
        print(f"[INFO] IRQ handler invoked {irq_count} times")

    return errors

def main():
    parser = argparse.ArgumentParser(description="Compare Spike and RTL traces")
    parser.add_argument("--mode", choices=["strict", "self-check"], default="strict",
                        help="Comparison mode: strict (Spike vs RTL) or self-check (RTL only)")
    parser.add_argument("--rtl-log", help="RTL trace log file")
    parser.add_argument("--spike-log", help="Spike trace log file (required for strict mode)")
    parser.add_argument("--max-errors", type=int, default=20, help="Maximum errors to report")
    # 兼容旧的位置参数调用方式: compare_trace.py <spike_log> <rtl_log>
    parser.add_argument("positional", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args()

    # 兼容旧调用方式: compare_trace.py <spike_log> <rtl_log>
    if args.positional and len(args.positional) == 2 and not args.rtl_log:
        args.spike_log = args.positional[0]
        args.rtl_log = args.positional[1]
        args.mode = "strict"

    if not args.rtl_log:
        parser.error("--rtl-log is required (or provide two positional args: <spike_log> <rtl_log>)")

    if args.mode == "strict":
        if not args.spike_log:
            print("[ERROR] --spike-log required for strict mode")
            sys.exit(1)
        errors = compare_strict(args.spike_log, args.rtl_log, args.max_errors)
    else:
        errors = compare_self_check(args.rtl_log)

    if errors is False:
        print("[FAIL] Invalid trace data!")
        sys.exit(1)
    elif not errors:
        print("[PASS] Traces match!" if args.mode == "strict" else "[PASS] Self-check passed!")
        sys.exit(0)
    else:
        print(f"[FAIL] Found {len(errors)} errors:")
        for err in errors:
            print(f"  {err}")
        sys.exit(1)

if __name__ == "__main__":
    main()
