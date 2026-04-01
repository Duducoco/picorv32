# PicoRV32 RISCV-DV 验证环境

PICORV32_ROOT := $(shell pwd)/..
DV_ROOT := $(PICORV32_ROOT)/dv
CFG_DIR := $(DV_ROOT)/cfg
SCRIPTS_DIR := $(DV_ROOT)/scripts
OUT_DIR := $(DV_ROOT)/out

SIMV := $(OUT_DIR)/build/simv

.PHONY: all clean compile_vcs riscv_dv_test help

help:
	@echo "PicoRV32 RISCV-DV 验证环境"
	@echo ""
	@echo "目标:"
	@echo "  compile_vcs       - 编译 VCS"
	@echo "  riscv_dv_test     - 运行单个测试 (TEST=<test_name> [SEED=<number>])"
	@echo "  merge_cov         - 合并所有测试的覆盖率"
	@echo "  cov_report        - 生成覆盖率报告"
	@echo "  clean             - 清理输出文件"
	@echo ""
	@echo "示例:"
	@echo "  make compile_vcs"
	@echo "  make riscv_dv_test TEST=riscv_arithmetic_basic_test"
	@echo "  make riscv_dv_test TEST=riscv_arithmetic_basic_test SEED=42"
	@echo "  make merge_cov"
	@echo "  make cov_report"

compile_vcs:
	@mkdir -p $(OUT_DIR)/build
	@echo "编译 VCS..."
	cd $(OUT_DIR)/build && vcs -full64 -sverilog \
		-f $(CFG_DIR)/vcs.f \
		$(PICORV32_ROOT)/picorv32.v \
		$(DV_ROOT)/tb/testbench_vcs.sv \
		-o $(SIMV) \
		-Mdir=$(OUT_DIR)/build/csrc \
		-debug_access+all \
		-timescale=1ns/1ps \
		-cm_dir $(OUT_DIR)/build/coverage.vdb
	@echo "VCS 编译完成: $(SIMV)"

riscv_dv_test: $(SIMV)
	@if [ -z "$(TEST)" ]; then \
		echo "错误: 请指定 TEST=<test_name>"; \
		echo "示例: make riscv_dv_test TEST=riscv_arithmetic_basic_test"; \
		echo "可选: SEED=<number> 设置随机种子"; \
		exit 1; \
	fi
	@echo "运行测试: $(TEST)"
	python3 $(SCRIPTS_DIR)/run_riscv_dv.py --test=$(TEST) --simv=$(SIMV) \
		$(if $(SEED),--seed=$(SEED))

$(SIMV):
	@echo "VCS 未编译，正在编译..."
	$(MAKE) compile_vcs

merge_cov:
	@echo "合并覆盖率数据库..."
	@if [ ! -d $(OUT_DIR) ]; then \
		echo "错误: 没有找到测试输出目录"; \
		exit 1; \
	fi
	@if [ ! -d $(OUT_DIR)/build/coverage.vdb ]; then \
		echo "错误: 没有找到编译时覆盖率数据库，请先运行 make compile_vcs"; \
		exit 1; \
	fi
	@find $(OUT_DIR)/picorv32 -name "coverage.vdb" -type d > cov_list.txt
	@if [ ! -s cov_list.txt ]; then \
		echo "错误: 没有找到测试覆盖率数据库"; \
		rm -f cov_list.txt; \
		exit 1; \
	fi
	urg -full64 -dir $(OUT_DIR)/build/coverage.vdb -dir `cat cov_list.txt | tr '\n' ' '` \
		-dbname $(OUT_DIR)/merged_coverage -report $(OUT_DIR)/cov_report
	@rm -f cov_list.txt
	@echo "覆盖率已合并到: $(OUT_DIR)/merged_coverage"
	@echo "覆盖率报告: $(OUT_DIR)/cov_report/dashboard.html"

cov_report:
	@if [ ! -d $(OUT_DIR)/merged_coverage ]; then \
		echo "错误: 请先运行 make merge_cov"; \
		exit 1; \
	fi
	@echo "生成覆盖率报告..."
	urg -full64 -dir $(OUT_DIR)/merged_coverage -report $(OUT_DIR)/cov_report
	@echo "覆盖率报告: $(OUT_DIR)/cov_report/dashboard.html"

clean:
	rm -rf $(OUT_DIR)
	rm -rf $(DV_ROOT)/csrc
	rm -f $(DV_ROOT)/*.vcd $(DV_ROOT)/*.fsdb
	rm -f cov_list.txt
	@echo "清理完成"
