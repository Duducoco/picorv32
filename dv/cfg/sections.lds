OUTPUT_ARCH("riscv")
ENTRY(_boot)

SECTIONS {
	. = 0x80000000;
	.text.boot : { *(.text.boot) }
	. = ALIGN(0x200);      /* Reserve space for boot + IRQ handler */
	.text : { *(.text*) }
	.data : {
		*(.data*)
	}
	.bss : {
		*(.bss*)
	}
	end = .;
}
