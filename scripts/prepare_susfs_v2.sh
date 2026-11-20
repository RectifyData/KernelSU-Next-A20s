#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
BASE_COMMIT="2c092bb53c44f4fc921c1f191140552fb1aca633"
SUSFS_REPO="https://github.com/wxx9248/susfs4ksu.git"
SUSFS_REF="71345ded5af28f55d76ebcdc7a9df9cea56111e1"

cd "$ROOT"

# Drop the old SUSFS v1.5.x integration while preserving unrelated A20s changes.
old_susfs_files=(
  fs/Makefile
  fs/dcache.c
  fs/namei.c
  fs/namespace.c
  fs/notify/fdinfo.c
  fs/overlayfs/inode.c
  fs/overlayfs/overlayfs.h
  fs/overlayfs/readdir.c
  fs/overlayfs/super.c
  fs/proc/cmdline.c
  fs/proc/fd.c
  fs/proc/task_mmu.c
  fs/proc_namespace.c
  fs/readdir.c
  fs/stat.c
  fs/statfs.c
  include/linux/mount.h
  include/linux/sched.h
  kernel/kallsyms.c
  kernel/sys.c
)

git checkout "$BASE_COMMIT" -- "${old_susfs_files[@]}"
rm -f fs/sus_su.c include/linux/sus_su.h fs/susfs.c include/linux/susfs.h include/linux/susfs_def.h

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
git -C "$tmp" remote add origin "$SUSFS_REPO"
git -C "$tmp" fetch -q --depth 1 origin "$SUSFS_REF"
git -C "$tmp" checkout -q FETCH_HEAD

cp "$tmp/kernel_patches/fs/susfs.c" fs/susfs.c
cp "$tmp/kernel_patches/include/linux/susfs.h" include/linux/susfs.h
cp "$tmp/kernel_patches/include/linux/susfs_def.h" include/linux/susfs_def.h

python3 scripts/apply_susfs_v2.py "$tmp/kernel_patches/50_add_susfs_in_kernel-4.9.patch"

cfg="arch/arm64/configs/a20s_eur_open_defconfig"
# Remove v1-only switches and ensure the v2 feature set is enabled.
sed -i \
  -e '/CONFIG_KSU_SUSFS_AUTO_ADD_SUS_KSU_DEFAULT_MOUNT=/d' \
  -e '/CONFIG_KSU_SUSFS_AUTO_ADD_SUS_BIND_MOUNT=/d' \
  -e '/CONFIG_KSU_SUSFS_AUTO_ADD_TRY_UMOUNT_FOR_BIND_MOUNT=/d' \
  -e '/CONFIG_KSU_SUSFS_SUS_OVERLAYFS=/d' \
  -e '/CONFIG_KSU_SUSFS_TRY_UMOUNT=/d' \
  "$cfg"

grep -q '^CONFIG_KSU_SUSFS_SUS_MAP=y$' "$cfg" || echo 'CONFIG_KSU_SUSFS_SUS_MAP=y' >> "$cfg"

grep -q '#define SUSFS_VERSION "v2.3.0"' include/linux/susfs.h
echo "Prepared SUSFS v2.3.0 for Linux 4.9."
