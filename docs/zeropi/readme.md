## ZeroPi Build Guide

### Platform </br>
The ZeroPi board designed by FriendlyELEC, uses an Allwinner SoC with ARM processor.

- Board: [ZeroPi](https://wiki.friendlyarm.com/wiki/index.php/ZeroPi) by FriendlyELEC
- SoC: Allwinner [H3](https://linux-sunxi.org/H3), "sunxi" series, [sun8i](https://linux-sunxi.org/Allwinner_SoC_Family) generation
- CPU: Cortex A7 by ARM, quad-core

----------------------------------------------------------------------------------------

### Summary </br>

Our platform uses an SD card containing three elements:
1. SPL and U-Boot: compiled together into a single binary
2. Linux root file system: obtained from ArchLinuxARM latest (contains uImage and dtbs)
3. The U-Boot script ```boot.scr```, compiled from boot.cmd

----------------------------------------------------------------------------------------

### Quick Start </br>

//TODO: commands only, no context



----------------------------------------------------------------------------------------

### SD Card: Partition </br>

SD Card: SanDisk 16GB micro (Class 10)

Note this process completely rewrites the SD card; all existing data will be lost.

```zsh

# confirm SD card name 'sdX', for example, 'sdc' below

% lsblk
NAME        MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
sda           8:0    1     0B  0 disk 
sdb           8:16   1     0B  0 disk 
sdc           8:32   1  14.8G  0 disk 
nvme0n1     259:0    0 465.8G  0 disk 
├─nvme0n1p1 259:1    0   512M  0 part /boot
├─nvme0n1p2 259:2    0     8G  0 part [SWAP]
└─nvme0n1p3 259:3    0 457.3G  0 part /

# write zeros to the beginning of the card (replace 'sdX' with your SD card name)

% sudo dd if=/dev/zero of=/dev/sdX bs=1M count=8
[sudo] password for root: 
8+0 records in
8+0 records out
8388608 bytes (8.4 MB, 8.0 MiB) copied, 3.1184 s, 2.7 MB/s

# use fdisk to partition the rest of the card
% sudo fdisk /dev/sdX
[sudo] password for root: 

Welcome to fdisk (util-linux 2.37).
Changes will remain in memory only, until you decide to write them.
Be careful before using the write command.

Command (m for help): 

# create a new empty DOS partition table
Command (m for help): o
Created a new DOS disklabel with disk identifier 0xe1cbda54.

# verify all previous partitions were removed
Command (m for help): p
Disk /dev/sdc: 14.84 GiB, 15931539456 bytes, 31116288 sectors
Disk model: CardReader SD2  
Units: sectors of 1 * 512 = 512 bytes
Sector size (logical/physical): 512 bytes / 512 bytes
I/O size (minimum/optimal): 512 bytes / 512 bytes
Disklabel type: dos
Disk identifier: 0xe1cbda54

# create a new primary partition, save changes and exit
Command (m for help): n
Partition type
   p   primary (0 primary, 0 extended, 4 free)
   e   extended (container for logical partitions)
Select (default p): p
Partition number (1-4, default 1): 1
First sector (2048-31116287, default 2048): 2048
Last sector, +/-sectors or +/-size{K,M,G,T,P} (2048-31116287, default 31116287): 

Created a new partition 1 of type 'Linux' and of size 14.8 GiB.

Command (m for help): w
The partition table has been altered.
Calling ioctl() to re-read partition table.
Syncing disks.

# verify the new partition 'sdX1', for example 'sdc1' below:
% lsblk
NAME        MAJ:MIN RM   SIZE RO TYPE MOUNTPOINTS
sda           8:0    1     0B  0 disk 
sdb           8:16   1     0B  0 disk 
sdc           8:32   1  14.8G  0 disk 
└─sdc1        8:33   1  14.8G  0 part 
nvme0n1     259:0    0 465.8G  0 disk 
├─nvme0n1p1 259:1    0   512M  0 part /boot
├─nvme0n1p2 259:2    0     8G  0 part [SWAP]
└─nvme0n1p3 259:3    0 457.3G  0 part /

# create the ext4 filesystem, this will take a minute or so
% sudo mkfs.ext4 /dev/sdX1
[sudo] password for root: 
mke2fs 1.46.2 (28-Feb-2021)
Creating filesystem with 3889280 4k blocks and 972944 inodes
Filesystem UUID: 113314f0-b772-40ec-869e-8f5ddd9305ab
Superblock backups stored on blocks: 
	32768, 98304, 163840, 229376, 294912, 819200, 884736, 1605632, 2654208

Allocating group tables: done                            
Writing inode tables: done                            
Creating journal (16384 blocks): done
Writing superblocks and filesystem accounting information: done  

```
----------------------------------------------------------------------------------------

### SPL and U-Boot </br>

```zsh

# install toolchain

# per aur, install gcc in stages to avoid circular dependencies with glibc versions
% yay -S arm-linux-gnueabihf-gcc-stage1

# conflict note: 'y' to remove gcc-stage1 and replace with gcc-stage2
% yay -S arm-linux-gnueabihf-gcc-stage2

# conflict note: 'y' to remove glibc-headers and replace with glibc
# conflict note: 'y' to remove gcc-stage2 and replace with gcc
% yay -S arm-linux-gnueabihf-gcc

# clone U-Boot mainline repo

% git clone https://source.denx.de/u-boot/u-boot.git
Cloning into 'u-boot'...
remote: Enumerating objects: 783410, done.
remote: Counting objects: 100% (11019/11019), done.
remote: Compressing objects: 100% (4724/4724), done.
remote: Total 783410 (delta 7759), reused 8355 (delta 6230), pack-reused 772391
Receiving objects: 100% (783410/783410), 157.51 MiB | 8.07 MiB/s, done.
Resolving deltas: 100% (651893/651893), done.

# compilation steps

# cd to u-boot directory, remove any previously compiled files if needed
% make CROSS_COMPILE=arm-linux-gnueabihf- distclean

# apply board default configuration
% make CROSS_COMPILE=arm-linux-gnueabihf- nanopi_m1_defconfig
  HOSTCC  scripts/basic/fixdep
  HOSTCC  scripts/kconfig/conf.o
  YACC    scripts/kconfig/zconf.tab.c
  LEX     scripts/kconfig/zconf.lex.c
  HOSTCC  scripts/kconfig/zconf.tab.o
  HOSTLD  scripts/kconfig/conf

  configuration written to .config

# optional: run menuconfig to customize settings other than default config
% make CROSS_COMPILE=arm-linux-gnueabihf- menuconfig

# install the 'swig' package (required for compilation step)
sudo pacman -S swig

# compile
% make CROSS_COMPILE=arm-linux-gnueabihf- -j$(nproc)

# confirm 'u-boot-sunxi-with-spl.bin' was created:
% ls
api        disk      Kbuild       README      u-boot.cfg          u-boot.map
arch       doc       Kconfig      scripts     u-boot.cfg.configs  u-boot-nodtb.bin
board      drivers   lib          spl         u-boot.dtb          u-boot.srec
build      dts       Licenses     System.map  u-boot-dtb.bin      u-boot-sunxi-with-spl.bin
cmd        env       MAINTAINERS  test        u-boot-dtb.img      u-boot-sunxi-with-spl.map
common     examples  Makefile     tools       u-boot.dtb.out      u-boot.sym
config.mk  fs        net          u-boot      u-boot.img
configs    include   post         u-boot.bin  u-boot.lds

```

----------------------------------------------------------------------------------------

### boot script </br>

U-Boot automatically looks for and loads ```boot.scr``` and ```uEnv.txt```.
Our platform only uses ```boot.scr```.

Create a file ```boot.cmd``` containing the source below (from the [Arch Wiki](https://wiki.archlinux.org/title/NanoPi_M1)):

```zsh

part uuid ${devtype} ${devnum}:${bootpart} uuid
setenv bootargs console=${console} root=PARTUUID=${uuid} rw rootwait

if load ${devtype} ${devnum}:${bootpart} ${kernel_addr_r} /boot/zImage; then
  if load ${devtype} ${devnum}:${bootpart} ${fdt_addr_r} /boot/dtbs/${fdtfile}; then
    if load ${devtype} ${devnum}:${bootpart} ${ramdisk_addr_r} /boot/initramfs-linux.img; then
      bootz ${kernel_addr_r} ${ramdisk_addr_r}:${filesize} ${fdt_addr_r};
    else
      bootz ${kernel_addr_r} - ${fdt_addr_r};
    fi;
  fi;
fi

if load ${devtype} ${devnum}:${bootpart} 0x48000000 /boot/uImage; then
  if load ${devtype} ${devnum}:${bootpart} 0x43000000 /boot/script.bin; then
    setenv bootm_boot_mode sec;
    bootm 0x48000000;
  fi;
fi

```

Compile ```boot.scr``` from ```boot.cmd``` using ```mkimage``` in the ```uboot-tools``` package.

```zsh
# install uboot-tools
% sudo pacman -S uboot-tools

# compile boot.scr
% # mkimage -A arm -O linux -T script -C none -a 0 -e 0 -n "ZeroPi Boot Script" -d boot.cmd boot.scr

```

----------------------------------------------------------------------------------------

### SD Card: Write </br>

// mount the file system

// download and extract linux root file system

// write spl and u-boot

// write boot script 

----------------------------------------------------------------------------------------

### Boot Process </br>

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
     nconfig, and init the Linux kernel.

----------------------------------------------------------------------------------------

### Boot Component Details </br>

**RBL:** </br>
The RBL is created by the vendor, placed in the ROM and executes automatically. It has
a few simple but critical functions including the task to find and execute the SPL. We
don't need to modify this component and it's also not possible to modify it.

**SPL:** </br>
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

**U-Boot:** </br>
Board inits occur during the full U-Boot process. All ```sunxi``` boards use the same
source for common initialization settings but the ZeroPi does not have a specific
Default Configuration. This is not unusual; multiple boards from a particular vendor
will often share the same components and thus the same configuration settings. We use
the ```NanoPi M1``` defconfig as it is very similar to the ```ZeroPi```.

- Board: ```u-boot/board/sunxi```
- Default Configuration: ```u-boot/configs/nanopi_m1_defconfig``` 

NOTE: additional customization of the Default Configuration is possible during the
compilation steps using the CLI-based ```menuconfig``` tool included with U-Boot.
 
**Linux:** </br>

This board is fully supported by mainline Linux (linux/arch/arm/mach-sunxi)
//TODO

----------------------------------------------------------------------------------------


Notes:

look at messages:
dmesg -T --follow
