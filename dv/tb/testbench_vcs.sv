module testbench_vcs;
    reg clk = 0;
    reg resetn = 0;

    always #5 clk = ~clk;

    initial begin
        repeat (10) @(posedge clk);
        resetn = 1;
    end

    // 内存模型 (256KB = 65536 words)
    reg [31:0] memory [0:65535];

    initial begin
        if ($value$plusargs("hex=%s", hex_file)) begin
            $readmemh(hex_file, memory);
            $display("[TB] Loaded hex file: %s", hex_file);
        end else begin
            $display("[TB] ERROR: No hex file specified (+hex=<file>)");
            $finish;
        end
    end

    // 内存接口信号
    wire        mem_valid;
    wire        mem_instr;
    reg         mem_ready;
    wire [31:0] mem_addr;
    wire [31:0] mem_wdata;
    wire [ 3:0] mem_wstrb;
    reg  [31:0] mem_rdata;

    // 内存访问逻辑 (地址映射: 0x80000000 -> memory[0])
    wire [31:0] mem_word_addr = (mem_addr - 32'h80000000) >> 2;
    wire mem_addr_valid = (mem_addr >= 32'h80000000) && (mem_addr < 32'h80040000);

    always @(posedge clk) begin
        mem_ready <= 0;
        if (mem_valid && !mem_ready) begin
            mem_ready <= 1;
            if (mem_addr_valid) begin
                if (|mem_wstrb) begin
                    // 写操作
                    if (mem_wstrb[0]) memory[mem_word_addr][7:0]   <= mem_wdata[7:0];
                    if (mem_wstrb[1]) memory[mem_word_addr][15:8]  <= mem_wdata[15:8];
                    if (mem_wstrb[2]) memory[mem_word_addr][23:16] <= mem_wdata[23:16];
                    if (mem_wstrb[3]) memory[mem_word_addr][31:24] <= mem_wdata[31:24];
                end else begin
                    // 读操作
                    mem_rdata <= memory[mem_word_addr];
                end
            end else begin
                // 越界访问：读返回 0，写忽略
                mem_rdata <= 32'h00000000;
            end
        end
    end

    // RVFI 接口信号
    wire        rvfi_valid;
    wire [63:0] rvfi_order;
    wire [31:0] rvfi_insn;
    wire        rvfi_trap;
    wire        rvfi_halt;
    wire        rvfi_intr;
    wire [ 1:0] rvfi_mode;
    wire [ 1:0] rvfi_ixl;
    wire [ 4:0] rvfi_rs1_addr;
    wire [ 4:0] rvfi_rs2_addr;
    wire [31:0] rvfi_rs1_rdata;
    wire [31:0] rvfi_rs2_rdata;
    wire [ 4:0] rvfi_rd_addr;
    wire [31:0] rvfi_rd_wdata;
    wire [31:0] rvfi_pc_rdata;
    wire [31:0] rvfi_pc_wdata;
    wire [31:0] rvfi_mem_addr;
    wire [ 3:0] rvfi_mem_rmask;
    wire [ 3:0] rvfi_mem_wmask;
    wire [31:0] rvfi_mem_rdata;
    wire [31:0] rvfi_mem_wdata;

    // 实例化 PicoRV32
    picorv32 #(
        .PROGADDR_RESET(32'h80000000),
        .PROGADDR_IRQ(32'h80000010),
        .COMPRESSED_ISA(1),
        .ENABLE_MUL(1),
        .ENABLE_DIV(1),
        .ENABLE_IRQ(1),
        .ENABLE_IRQ_QREGS(1),
        .ENABLE_IRQ_TIMER(0),
        .ENABLE_COUNTERS(1),
        .ENABLE_COUNTERS64(1),
        .CATCH_ILLINSN(1),
        .CATCH_MISALIGN(1),
        .REGS_INIT_ZERO(1)
    ) dut (
        .clk(clk),
        .resetn(resetn),
        .trap(trap),

        .mem_valid(mem_valid),
        .mem_instr(mem_instr),
        .mem_ready(mem_ready),
        .mem_addr(mem_addr),
        .mem_wdata(mem_wdata),
        .mem_wstrb(mem_wstrb),
        .mem_rdata(mem_rdata),

        .mem_la_read(),
        .mem_la_write(),
        .mem_la_addr(),
        .mem_la_wdata(),
        .mem_la_wstrb(),

        .pcpi_valid(),
        .pcpi_insn(),
        .pcpi_rs1(),
        .pcpi_rs2(),
        .pcpi_wr(1'b0),
        .pcpi_rd(32'b0),
        .pcpi_wait(1'b0),
        .pcpi_ready(1'b0),

        .irq(32'b0),
        .eoi(),

        .rvfi_valid(rvfi_valid),
        .rvfi_order(rvfi_order),
        .rvfi_insn(rvfi_insn),
        .rvfi_trap(rvfi_trap),
        .rvfi_halt(rvfi_halt),
        .rvfi_intr(rvfi_intr),
        .rvfi_mode(rvfi_mode),
        .rvfi_ixl(rvfi_ixl),
        .rvfi_rs1_addr(rvfi_rs1_addr),
        .rvfi_rs2_addr(rvfi_rs2_addr),
        .rvfi_rs1_rdata(rvfi_rs1_rdata),
        .rvfi_rs2_rdata(rvfi_rs2_rdata),
        .rvfi_rd_addr(rvfi_rd_addr),
        .rvfi_rd_wdata(rvfi_rd_wdata),
        .rvfi_pc_rdata(rvfi_pc_rdata),
        .rvfi_pc_wdata(rvfi_pc_wdata),
        .rvfi_mem_addr(rvfi_mem_addr),
        .rvfi_mem_rmask(rvfi_mem_rmask),
        .rvfi_mem_wmask(rvfi_mem_wmask),
        .rvfi_mem_rdata(rvfi_mem_rdata),
        .rvfi_mem_wdata(rvfi_mem_wdata),
        .rvfi_csr_mcycle_rmask(),
        .rvfi_csr_mcycle_wmask(),
        .rvfi_csr_mcycle_rdata(),
        .rvfi_csr_mcycle_wdata(),
        .rvfi_csr_minstret_rmask(),
        .rvfi_csr_minstret_wmask(),
        .rvfi_csr_minstret_rdata(),
        .rvfi_csr_minstret_wdata()
    );

    // Trace 输出
    integer trace_fd;
    string hex_file;
    string trace_file;
    integer cycle_count = 0;
    parameter MAX_CYCLES = 100000;

    // tohost 检测: RISCV-DV 的 write_tohost 向 tohost 地址写入非零值表示测试结束
    // tohost 地址通过 +tohost=<addr> plusarg 传入 (由 compile_test.py 从 ELF 提取)
    reg [31:0] tohost_addr = 0;
    initial begin
        if (!$value$plusargs("tohost=%h", tohost_addr))
            tohost_addr = 0;  // 未指定则不启用 tohost 检测
        else
            $display("[TB] Monitoring tohost at 0x%08x", tohost_addr);
    end

    initial begin
        if ($value$plusargs("trace=%s", trace_file)) begin
            trace_fd = $fopen(trace_file, "w");
            $display("[TB] Trace output: %s", trace_file);
        end else begin
            trace_fd = $fopen("rtl_trace.log", "w");
            $display("[TB] Trace output: rtl_trace.log");
        end
    end

    always @(posedge clk) begin
        if (rvfi_valid) begin
            $fwrite(trace_fd, "PC=%08x INSN=%08x INTR=%0d", rvfi_pc_rdata, rvfi_insn, rvfi_intr);
            if (rvfi_rd_addr != 0)
                $fwrite(trace_fd, " x%0d=%08x", rvfi_rd_addr, rvfi_rd_wdata);
            if (|rvfi_mem_wmask)
                $fwrite(trace_fd, " MEM[%08x]=%08x", rvfi_mem_addr, rvfi_mem_wdata);
            $fwrite(trace_fd, "\n");

            // 检测 ecall (opcode 0x00000073) 作为测试终止信号
            if (rvfi_insn == 32'h00000073) begin
                $display("[TB] ECALL detected at PC=%08x, test done at cycle %0d", rvfi_pc_rdata, cycle_count);
                $fclose(trace_fd);
                $finish;
            end

            // 检测 tohost 写入：RISCV-DV write_tohost 写非零值到 tohost 表示测试完成
            if (tohost_addr != 0 && |rvfi_mem_wmask && rvfi_mem_addr == tohost_addr && rvfi_mem_wdata != 0) begin
                $display("[TB] tohost write detected: MEM[%08x]=%08x, test done at cycle %0d",
                         rvfi_mem_addr, rvfi_mem_wdata, cycle_count);
                $fclose(trace_fd);
                $finish;
            end
        end
    end

    // 超时和结束条件
    always @(posedge clk) begin
        if (resetn) cycle_count <= cycle_count + 1;

        if (cycle_count > MAX_CYCLES) begin
            $display("[TB] TIMEOUT after %0d cycles", MAX_CYCLES);
            $fclose(trace_fd);
            $finish;
        end

        if (trap) begin
            $display("[TB] TRAP at cycle %0d, last_PC=%08x", cycle_count, rvfi_pc_rdata);
            $fclose(trace_fd);
            $finish;
        end
    end

    // 可选波形 dump（通过 +dump plusarg 启用）
    initial begin
        if ($test$plusargs("dump")) begin
            $dumpfile("dump.vcd");
            $dumpvars(0, testbench_vcs);
        end
    end

endmodule
