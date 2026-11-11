ENTRY(_start)
SECTIONS {
    . = 0x41f00000;
    .text : { KEEP(*(.text.start)) *(.text*) *(.rodata*) }
    .data : { *(.data*) }
    __image_end = .;
    .bss 0x41f60000 (NOLOAD) : { __bss_start = .; *(.bss*) *(COMMON) . = ALIGN(4); __bss_end = .; }
    __stack_top = 0x41f80000;
    /DISCARD/ : { *(.ARM.exidx*) *(.comment) *(.ARM.attributes) }
}
