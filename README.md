# KernelSU-Next for Samsung Galaxy A20s (SM-A207F / msm8953)

[![Kernel Version](https://img.shields.io/badge/Kernel-4.9.227--perf%2B-blue.svg)](https://github.com/)
[![KernelSU-Next](https://img.shields.io/badge/KernelSU--Next-v3.2.0--legacy-success.svg)](https://github.com/KernelSU-Next/KernelSU-Next)
[![SELinux](https://img.shields.io/badge/SELinux-Enforcing-brightgreen.svg)]()
[![Target OS](https://img.shields.io/badge/Android-11%20(One%20UI)-orange.svg)]()
[![Device](https://img.shields.io/badge/Device-Samsung%20Galaxy%20A20s-purple.svg)]()

Custom kernel for the **Samsung Galaxy A20s** (`SM-A207F` / `msm8953` / `sdm450`) with built-in **KernelSU-Next legacy** root support, full **SELinux Enforcing** compatibility, and performance fixes.

---

## 📱 Supported Devices

| Device Model | Codename | Platform | Android Version |
| :--- | :--- | :--- | :--- |
| **Samsung Galaxy A20s** (`SM-A207F`) | `a20s` / `a20sxx` | Qualcomm Snapdragon 450 (`msm8953`) | Android 11 (One UI 3.1) |
| **Samsung Galaxy A20s** (`SM-A207M`) | `a20s` | Qualcomm Snapdragon 450 (`msm8953`) | Android 11 (One UI 3.1) |
| **Samsung Galaxy A20s** (`SM-A2070`) | `a20s` | Qualcomm Snapdragon 450 (`msm8953`) | Android 11 (One UI 3.1) |

---

## ✨ Features

- **KernelSU-Next Legacy Integrated**: Built directly into the kernel source (`v3.2.0-legacy`) running in **Manual Hook Mode** for Linux 4.9.
- **SELinux Enforcing Supported**: Full root privilege separation under `u:r:ksu:s0` without requiring permissive mode.
- **OverlayFS Enabled (`CONFIG_OVERLAY_FS=y`)**: Full support for systemless root modules (ZygiskNext, ZygiskKSU, etc.).
- **Connectivity & Battery Drain Fix**: `CONFIG_CNSS_GENL=y` enabled to fix the Qualcomm `cnss-daemon` ~61% CPU spinning loop.
- **Samsung SAR Compatible Installer**: Custom AnyKernel3 configuration configured for System-as-Root boot partitions without ramdisk unpack errors.

---

## 📦 Downloads & Releases

- **Kernel Package**: Download **`KSU-Next-Kernel-A20s.zip`** from the [Releases](https://github.com/) section.
- **Boot Fix**: **`Fixboot.zip`** (Required for Samsung A20s boot compatibility).
- **Manager App**: Download the latest **KernelSU-Next Manager APK** from the [KernelSU-Next Releases](https://github.com/KernelSU-Next/KernelSU-Next/releases).

---

## 🚀 Installation Guide

> [!WARNING]
> Unlocking your bootloader will wipe your device data and trip Samsung Knox (`0x1`). Always backup your critical files before flashing custom kernels.

### Prerequisites:
1. Bootloader unlocked on your Samsung Galaxy A20s.
2. Custom Recovery installed (**TWRP** or **OrangeFox**).
3. Downloaded `KSU-Next-Kernel-A20s.zip` and `Fixboot.zip` onto an SD Card or internal storage.

### Step-by-Step Flashing:

1. **Boot into Recovery**:
   - Power off your phone.
   - Hold `Volume Up + Power` until the TWRP / OrangeFox splash screen appears.
2. **Backup (Recommended)**:
   - Go to **Backup** and create a backup of your `Boot` and `DTBO` partitions.
3. **Flash Kernel**:
   - Tap **Install** and select `KSU-Next-Kernel-A20s.zip`.
   - Swipe to confirm flash.
4. **Flash Fixboot (Crucial)**:
   - Select `Fixboot.zip`.
   - Swipe to confirm flash. *(This step fixes the Samsung A20s boot verification/encryption bug).*
5. **Reboot**:
   - Wipe `Dalvik / ART Cache` (optional but recommended).
   - Tap **Reboot System**.
6. **Install Manager**:
   - Once booted into Android, install the **KernelSU-Next Manager APK**.
   - Open the app and verify that the status displays **Working (BUILT-IN (LEGACY))**.

---

## 🛠️ Building from Source

### Requirements
- OS: Linux (Debian 12 / Ubuntu 22.04 LTS / WSL2)
- Build Tools: `make`, `bc`, `bison`, `flex`, `cpio`, `zip`, `python3`
- Toolchains: AArch64 GCC 4.9 & ARM32 GCC 4.9

### Compilation Steps:

```bash
# 1. Clone kernel repository & toolchains
git clone <your-kernel-repo-url> -b main kernel_a20s
cd kernel_a20s

# 2. Setup KernelSU-Next legacy driver
curl -LSs "https://raw.githubusercontent.com/KernelSU-Next/KernelSU-Next/next/kernel/setup.sh" | bash -s legacy

# 3. Export toolchain variables
export ARCH=arm64
export CROSS_COMPILE=/path/to/toolchains/gcc-arm64/bin/aarch64-linux-android-
export CROSS_COMPILE_ARM32=/path/to/toolchains/gcc-arm32/bin/arm-linux-androideabi-

# 4. Generate defconfig & compile
make O=out a20s_eur_open_defconfig
make -j$(nproc) O=out

# Output binary will be at: out/arch/arm64/boot/Image.gz-dtb
```

---

## ❓ Troubleshooting & FAQ

* **Q: The phone is stuck at the Samsung boot logo.**  
  **A:** Make sure you flashed `Fixboot.zip` immediately after `KSU-Next-Kernel-A20s.zip` before rebooting into system.

* **Q: KernelSU Manager says "Unsupported" or "Not Installed".**  
  **A:** Verify that you flashed `KSU-Next-Kernel-A20s.zip` without errors and installed the **KernelSU-Next** Manager (not standard KernelSU).

* **Q: Root is not working in ADB Shell.**  
  **A:** In the KernelSU-Next Manager, go to the Superuser tab and grant root permission to `Shell` (UID 2000) or your target app.

---

## 📜 Credits & Acknowledgements

- [yiesko/android_kernel_samsung_a20s](https://github.com/yiesko/android_kernel_samsung_a20s) for the Samsung Galaxy A20s kernel source tree and patches.
- [KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next) by **rifsxd** and contributors.
- [KernelSU](https://github.com/tiann/KernelSU) by **tiann**.
- [AnyKernel3](https://github.com/osm0sis/AnyKernel3) by **osm0sis**.
- **Samsung Open Source Release Center (OSRC)** for the base kernel source.
