## ZeroPi Build Guide

**Platform** </br>
The ZeroPi board designed by FriendlyELEC, uses an Allwinner SoC with ARM processor.

- Board: [ZeroPi](https://wiki.friendlyarm.com/wiki/index.php/ZeroPi) by FriendlyELEC
- SoC: Allwinner [H3](https://linux-sunxi.org/H3), "sunxi" series, [sun8i](https://linux-sunxi.org/Allwinner_SoC_Family) generation
- CPU: Cortex A7 by ARM, quad-core

----------------------------------------------------------------------------------------

**Boot Process** </br>

RBL → SPL → U-Boot → Linux

1. RBL (ROM bootloader): runs from ROM of the SoC when board is powered on
   - sets up stack, watchdog timer, system clock (using PLL)
   - searches memory devices for SPL image (in our case, first partition of SD card)
   - copies SPL from external memory device (SD card) to internal SRAM (SoC)
   - executes SPL

2. SPL (Secondary Program Loader, or MLO/Memory Loader): runs from internal SRAM (SoC)
   - inits UART console for debug messages
   - reconfigures PLL, inits DDR memory, configs boot peripherals (pin muxing)
   - searches memory devices for U-Boot image (in our case, first partition of SD card)
   - copies U-Boot image from external memory device (SD card) into DDR memory
   - passes control to U-Boot

3. U-Boot: runs from DDR memory
   - inits relevant peripherals to support loading the kernel
   - runs script to set destinations (DDR memory addresses) for Linux kernel and DTBs
   - loads Linux kernel image ```/boot/zImage``` and DTB/FDT ```/boot/dtbs``` from the
     SD card to the preset destinations in DDR memory
   - passes arguments (console settings, location of Linux RFS on SD card, and memory
     addresses of Linux kernel and the DTB/FDT in DDR memory) and transfers control to
     the Linux bootstrap loader 

4. Linux bootstrap loader: runs from DDR memory
   - uses the arguments and memory locations received from U-Boot to locate, decompress,
     config, and init the Linux kernel.

----------------------------------------------------------------------------------------

**Boot Component Details** </br>

1. RBL:
The RBL is created by the vendor, placed in the ROM and executes automatically. It has
a few simple but critical functions including the task to find and execute the SPL. We
don't need to modify this component and it's also not possible to modify it.

2. SPL:
We use the U-Boot mainline repository to create the SPL as well as the full U-Boot
bootloader. Some platforms separate these elements into the MLO (SPL) and full U-Boot
but on our platform they are compiled together into a single image.

U-Boot buckets common software architecture elements by CPU, SoC, and Board. For
example, all boards using an Arm Cortex A7 CPU (such as our ZeroPi), will use the same
CPU initialization code for compilation. Similarly, all boards using an AllWinner H3
SoC will use the same SoC initialization source code.

- CPU: ```u-boot/arch/arm/cpu/armv7/sunxi```
- SoC: ```u-boot/arch/arm/mach-sunxi```

The SPL functionality (by design) is not as complex as the full U-Boot bootloader. The
SPL only needs to know about the CPU and some of the SoC peripherals so it can
initialize these aspects and hand off control to the full U-Boot.

RBL → [ start.S → CPU inits → SoC inits ] → full U-Boot

3. U-Boot:
Board inits occur during the full U-Boot process.
- Board: ```u-boot/board/sunxi```
- Default Configuration: ```u-boot/configs/nanopi_m1_defconfig``` 

All ```sunxi``` boards use the same source for common initialization settings but the
ZeroPi does not have a specific Default Configuration. This is not unusual; multiple
boards from a particular vendor will often share the same components and thus the same
configuration settings. We use the ```NanoPi M1``` defconfig as it is very similar to
the ```ZeroPi```.

NOTE: additional customization of the Default Configuration is possible during the
compilation steps using the CLI-based ```menuconfig``` tool included with U-Boot.
 
4. Linux:

This board is fully supported by mainline Linux (linux/arch/arm/mach-sunxi)
//TODO

----------------------------------------------------------------------------------------

**High-level Requirements** </br>

This platform uses an SD card containing three elements:
- SPL and U-Boot: compiled together into a single binary
- Linux root file system: obtained from ArchLinuxARM latest (contains uImage and dtbs)
- a boot script for U-Boot: use boot.scr, compiled from boot.cmd

----------------------------------------------------------------------------------------

**SPL and U-Boot** </br>

Requirements:
//TODO


Toolchain setup:
//TODO


----------------------------------------------------------------------------------------

**SD Card Setup** </br>

Partition 1:
  - U-Boot bootloader with SPL (foo.??)

Partition 2:
  - Linux RFS (uImage)
  - boot script (boot.scr)

//TODO


----------------------------------------------------------------------------------------

Notes:

look at messages:
dmesg -T --follow
