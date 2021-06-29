## ZeroPi Build Guide

**Platform** </br>
The ZeroPi board designed by FriendlyELEC, uses an Allwinner SoC with ARM processor.

- Board: [ZeroPi](https://wiki.friendlyarm.com/wiki/index.php/ZeroPi) by FriendlyELEC
- SoC: Allwinner [H3](https://linux-sunxi.org/H3), "sunxi" series, [sun8i](https://linux-sunxi.org/Allwinner_SoC_Family) generation
- CPU: Cortex A7 by ARM, quad-core

----------------------------------------------------------------------------------------

**Boot Process** </br>
1. RBL (ROM bootloader): runs from ROM of the SoC when board is powered on
   - sets up stack, watchdog timer, system clock using PLL
   - searches memory devices for SPL/MLO
   - copies SPL/MLO from external memory device (SD card) to internal SRAM (SoC)
   - executes SPL/MLO

2. SPL (Secondary Program Loader) or MLO (Memory Loader): runs from internal SRAM (SoC)
   - inits UART console for debug messages
   - reconfigures PLL, inits DDR memory, config boot peripherals
   - copies U-Boot image from external memory device (SD card) into DDR memory
   - passes control to U-Boot

3. U-Boot: runs from DDR memory
   - inits relevant peripherals to support loading kernel
   - loads Linux kernel image from boot sources (/boot/uImage) to DDR memory
   - passes boot arguments and control to Linux bootstrap loader

4. Linux bootstrap loader: runs from DDR memory
   - loads Linux kernel from uImage (Linux zImage with a 64-byte U-Boot header)
   - loads appropriate DTB (Device Tree Binary)

----------------------------------------------------------------------------------------
**Required Components** </br>

- SPL and U-Boot: compile from mainline U-Boot repository
- Linux RFS: use ArchLinuxARM latest (contains uImage and dtbs)
- boot script: compile boot.scr (from boot.cmd) and write to /boot

----------------------------------------------------------------------------------------
**SPL and U-Boot** </br>

Requirements:
//TODO


Toolchain setup:
//TODO


Default Config:
../u-boot/configs/nanopi_m1_defconfig



----------------------------------------------------------------------------------------

**SD Card Setup** </br>

Partition 1:
  - U-Boot bootloader with SPL (foo.??)

Partition 2:
  - Linux RFS (uImage)
  - boot script (boot.scr)


----------------------------------------------------------------------------------------

Note: this board is fully supported by mainline Linux (linux/arch/arm/mach-sunxi)
and U-boot.

Notes:

look at messages:
dmesg -T --follow
