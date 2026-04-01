#!/usr/bin/env python3
"""RISCV-DV 验证流程主控脚本"""

import os
import sys
import subprocess
import argparse
import yaml
from pathlib import Path

PICORV32_ROOT = Path(__file__).parent.parent.parent
DV_ROOT = PICORV32_ROOT / "dv"
RISCV_DV = DV_ROOT / "riscv-dv"
CFG_DIR = DV_ROOT / "cfg"
SCRIPTS_DIR = DV_ROOT / "scripts"
OUT_DIR = DV_ROOT / "out"

def run_cmd(cmd, cwd=None, check=True):
    """执行命令"""
    print(f"[CMD] {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"[ERROR] {result.stderr}")
        return None
    return result

def load_testlist(testlist_path):
    """加载 testlist.yaml，返回 {test_name: config} 字典"""
    with open(testlist_path) as f:
        tests = yaml.safe_load(f)
    return {t['test']: t for t in tests}

def generate_test(test_name, output_dir, seed=None):
    """使用 RISCV-DV 生成测试（VCS 作为生成器）

    RISCV-DV 产物放到 output_dir/gen/，.S 文件复制到 output_dir/。
    seed: 随机种子（None 表示每次随机）
    """
    output_dir = Path(output_dir)
    gen_dir = output_dir / "gen"
    gen_dir.mkdir(parents=True, exist_ok=True)

    seed_opt = f" --seed={seed}" if seed is not None else ""

    cmd = (f"python3 run.py --custom_target={CFG_DIR} "
           f"--test={test_name} "
           f"--testlist={CFG_DIR}/testlist.yaml "
           f"--simulator=vcs "
           f"-o {gen_dir} --steps=gen --verbose"
           f"{seed_opt}")
    print(f"[INFO] Seed: {seed if seed is not None else 'random'}")

    result = run_cmd(cmd, cwd=RISCV_DV)
    if result is None:
        return None

    # 查找生成的 .S 文件
    asm_files = list(gen_dir.glob("asm_test/*.S"))
    if not asm_files:
        print(f"[ERROR] No .S file generated for {test_name}")
        return None

    # 复制 .S 到测试根目录
    import shutil
    copied = []
    for src in asm_files:
        dst = output_dir / src.name
        shutil.copy2(src, dst)
        copied.append(dst)
        print(f"[INFO] {src.name} -> {dst}")

    return copied[0]

def compile_test(asm_file, output_dir):
    """编译测试"""
    cmd = f"python3 {SCRIPTS_DIR}/compile_test.py {asm_file} {output_dir}"
    result = run_cmd(cmd)
    if result is None:
        return None
    return output_dir / "test.hex"

def run_spike(elf_file, output_log):
    """运行 Spike"""
    cmd = f"python3 {SCRIPTS_DIR}/spike_runner.py {elf_file} {output_log}"
    result = run_cmd(cmd)
    if result is None:
        return None
    return output_log

def run_vcs(hex_file, trace_file, simv_path, cov_dir):
    """运行 VCS 仿真"""
    if not simv_path.exists():
        print(f"[ERROR] VCS executable not found: {simv_path}")
        return None

    cov_dir.mkdir(parents=True, exist_ok=True)
    cov_vdb = cov_dir / "coverage.vdb"

    # 使用编译时生成的设计数据库
    build_cov_vdb = OUT_DIR / "build" / "coverage.vdb"

    test_dir = cov_dir.parent
    bin_dir = Path(hex_file).parent

    # 读取 tohost 地址（由 compile_test.py 从 ELF 提取）
    tohost_arg = ""
    tohost_file = bin_dir / "tohost_addr.txt"
    if tohost_file.exists():
        tohost_addr = tohost_file.read_text().strip()
        tohost_arg = f"+tohost={tohost_addr}"
        print(f"[INFO] tohost address: 0x{tohost_addr}")

    cmd = (f"{simv_path.resolve()} +hex={hex_file} +trace={trace_file} "
           f"{tohost_arg} "
           f"-cm line+cond+fsm+tgl+branch -cm_dir {cov_vdb} "
           f"-cm_log {test_dir / 'cm.log'} "
           f"-cm_name test")
    result = run_cmd(cmd, cwd=test_dir)
    if result is None:
        return None

    # 打印 VCS 仿真关键输出（TIMEOUT/TRAP/ECALL/tohost 等）
    if result and result.stdout:
        for line in result.stdout.splitlines():
            if "[TB]" in line:
                print(line)

    # 合并编译时的设计数据库和运行时的测试数据库
    report_dir = cov_dir / "report"
    report_cmd = f"urg -full64 -dir {build_cov_vdb} -dir {cov_vdb} -report {report_dir}"
    run_cmd(report_cmd, check=False)
    print(f"[INFO] Coverage report: {report_dir}/dashboard.html")

    return trace_file

def compare_traces(spike_log, rtl_log, compare_mode="strict"):
    """对比 trace"""
    if compare_mode == "self-check":
        cmd = (f"python3 {SCRIPTS_DIR}/compare_trace.py "
               f"--mode self-check --rtl-log {rtl_log}")
    else:
        cmd = (f"python3 {SCRIPTS_DIR}/compare_trace.py "
               f"--mode strict --spike-log {spike_log} --rtl-log {rtl_log}")
    result = run_cmd(cmd, check=False)
    return result.returncode == 0

def run_single_test(test_name, simv_path, compare_mode="strict", seed=None):
    """运行单个测试"""
    print(f"\n{'='*60}")
    print(f"Running test: {test_name} (compare_mode: {compare_mode})")
    print(f"{'='*60}")

    test_out = OUT_DIR / "picorv32" / test_name
    bin_out = test_out / "bin"
    cov_out = test_out / "coverage"
    spike_log = test_out / "spike.log"
    rtl_log = test_out / "rtl.log"

    # 1. 生成测试
    print("[1/5] Generating test...")
    asm_file = generate_test(test_name, test_out, seed=seed)
    if not asm_file:
        return False

    # 2. 编译测试
    print("[2/5] Compiling test...")
    hex_file = compile_test(asm_file, bin_out)
    if not hex_file:
        return False

    elf_file = bin_out / "test.elf"

    # 3. 运行 Spike (仅 strict 模式需要)
    if compare_mode == "strict":
        print("[3/5] Running Spike...")
        if not run_spike(elf_file, spike_log):
            return False
    else:
        print("[3/5] Skipping Spike (self-check mode)...")

    # 4. 运行 VCS
    print("[4/5] Running VCS...")
    if not run_vcs(hex_file, rtl_log, simv_path, cov_out):
        return False

    # 5. 对比 trace
    print("[5/5] Comparing traces...")
    passed = compare_traces(spike_log, rtl_log, compare_mode)

    if passed:
        print(f"[PASS] {test_name}")
        print(f"[INFO] Coverage: {cov_out}/coverage.vdb")
        print(f"[INFO] Report: {cov_out}/report/dashboard.html")
    else:
        print(f"[FAIL] {test_name}")

    return passed

def compile_vcs():
    """编译 VCS"""
    print("Compiling VCS...")
    build_dir = OUT_DIR / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    simv_path = build_dir / "simv"

    cmd = (f"vcs -full64 -sverilog -f {CFG_DIR}/vcs.f "
           f"{PICORV32_ROOT}/picorv32.v {DV_ROOT}/tb/testbench_vcs.sv "
           f"-o {simv_path} -Mdir={build_dir}/csrc -debug_access+all")
    result = run_cmd(cmd, cwd=build_dir)

    if result is None:
        print("[ERROR] VCS compilation failed")
        return None

    print(f"[SUCCESS] VCS compiled: {simv_path}")
    return simv_path

def run_testlist(testlist_path, simv_path):
    """运行 testlist 中的所有测试"""
    test_configs = load_testlist(testlist_path)
    results = {}

    for test_name, config in test_configs.items():
        compare_mode = config.get("compare_mode", "strict")
        iterations = config.get("iterations", 1)

        for i in range(iterations):
            iter_name = f"{test_name}_{i}" if iterations > 1 else test_name
            passed = run_single_test(test_name, simv_path, compare_mode)
            results[iter_name] = passed

    # 汇总结果
    print(f"\n{'='*60}")
    print("Test Summary")
    print(f"{'='*60}")
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    for name, status in results.items():
        print(f"  {'PASS' if status else 'FAIL'}: {name}")
    print(f"\nTotal: {total}, Passed: {passed}, Failed: {total - passed}")

    return all(results.values())

def main():
    parser = argparse.ArgumentParser(description="RISCV-DV verification flow")
    parser.add_argument("--test", help="Single test name")
    parser.add_argument("--testlist", help="Test list YAML file")
    parser.add_argument("--compile-vcs", action="store_true", help="Compile VCS")
    parser.add_argument("--simv", default=str(OUT_DIR / "build" / "simv"), help="Path to VCS executable")
    parser.add_argument("--compare-mode", choices=["strict", "self-check"],
                        help="Override compare mode for single test (default: from testlist)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Randomization seed for test generation (default: random)")
    args = parser.parse_args()

    simv_path = Path(args.simv)

    # 编译 VCS
    if args.compile_vcs or not simv_path.exists():
        simv_path = compile_vcs()
        if not simv_path:
            sys.exit(1)

    # 运行测试
    if args.test:
        # 确定 compare_mode：优先命令行参数，其次从 testlist 查找
        compare_mode = args.compare_mode
        if not compare_mode:
            testlist_path = CFG_DIR / "testlist.yaml"
            if testlist_path.exists():
                test_configs = load_testlist(testlist_path)
                if args.test in test_configs:
                    compare_mode = test_configs[args.test].get("compare_mode", "strict")
            if not compare_mode:
                compare_mode = "strict"

        passed = run_single_test(args.test, simv_path, compare_mode, seed=args.seed)
        sys.exit(0 if passed else 1)
    elif args.testlist:
        passed = run_testlist(args.testlist, simv_path)
        sys.exit(0 if passed else 1)
    else:
        print("Usage: --test <test_name> or --testlist <yaml_file>")
        sys.exit(1)

if __name__ == "__main__":
    main()
