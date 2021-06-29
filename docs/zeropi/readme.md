## ZeroPi Build Guide
----------------------------------------------------------------------------------------

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
   - loads Linux kernel via uImage (Linux zImage with a 64-byte U-Boot header)
   - loads the appropriate DTB (Device Tree Binary)


----------------------------------------------------------------------------------------

**SD Card** </br>
Partition 1:
  - U-Boot bootloader with SPL

Partition 2:
  - Linux RFS (uImage)
  - boot script (boot.scr)

----------------------------------------------------------------------------------------

**Toolchain** </br>




----------------------------------------------------------------------------------------

Notes:

look at messages:
dmesg -T --follow
