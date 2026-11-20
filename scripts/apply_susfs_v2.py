#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SKIP_FILES = {
    "drivers/input/input.c",
    "fs/exec.c",
    "fs/internal.h",
    "fs/open.c",
    "fs/proc/cmdline.c",
    "fs/read_write.c",
    "kernel/reboot.c",
}

KEEP_HUNKS = {
    # The remaining hunks in this file are SukiSU/ReSukiSU hook glue. The A20s
    # tree already carries KernelSU-Next manual hooks, so duplicating them
    # breaks the exact v3.4.0-legacy integration.
    "fs/stat.c": {18, 52},
    # Samsung's namespace.c has an extra fslog include. Add the SUSFS include
    # block below instead and keep the functional mount hunks.
    "fs/namespace.c": {120, 140, 202, 647, 983, 1038, 1063, 3020, 3596},
    # Samsung's inotify formatting differs from the generic 4.9 baseline.
    "fs/notify/fdinfo.c": {12, 20, 71, 101},
    # Samsung SELinux adds a vendor block after classmap.h; insert declarations
    # below and keep the AVC spoofing logic hunk.
    "security/selinux/avc.c": {158},
}

def split_sections(text: str) -> list[tuple[str, str]]:
    starts = [m.start() for m in re.finditer(r"(?m)^diff --git a/", text)]
    out = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(text)
        section = text[start:end]
        m = re.match(r"diff --git a/(\S+) b/\S+\n", section)
        if not m:
            raise RuntimeError("cannot parse patch section")
        out.append((m.group(1), section))
    return out

def filter_hunks(path: str, section: str) -> str:
    if path in SKIP_FILES:
        return ""
    allowed = KEEP_HUNKS.get(path)
    if allowed is None:
        return section

    first_hunk = section.find("@@ ")
    if first_hunk < 0:
        return section
    header = section[:first_hunk]
    parts = re.split(r"(?m)(?=^@@ )", section[first_hunk:])
    kept = []
    for hunk in parts:
        if not hunk.startswith("@@ "):
            continue
        m = re.match(r"@@ -(\d+)", hunk)
        if m and int(m.group(1)) in allowed:
            kept.append(hunk)
    return header + "".join(kept) if kept else ""

def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"{path}: anchor not found: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1))

def insert_after(path: Path, anchor: str, addition: str) -> None:
    replace_once(path, anchor, anchor + addition)

def manual_vendor_adaptations() -> None:
    ns = ROOT / "fs/namespace.c"
    insert_after(
        ns,
        '#include <linux/task_work.h>\n',
        '#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs_def.h>\n#endif\n\n',
    )
    insert_after(
        ns,
        '#include "internal.h"\n',
        '\n#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT\n'
        'extern bool susfs_is_current_ksu_domain(void);\n'
        'extern struct static_key_true susfs_is_sdcard_android_data_not_decrypted;\n'
        '#endif\n',
    )

    cmdline = ROOT / "fs/proc/cmdline.c"
    insert_after(
        cmdline,
        '#include <linux/seq_file.h>\n',
        '\n#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n'
        '#include <linux/jump_label.h>\n'
        'extern struct static_key_false susfs_is_fake_cmdline_or_bootconfig_buffer_set;\n'
        'extern void susfs_spoof_cmdline_or_bootconfig(struct seq_file *m);\n'
        '#endif\n',
    )
    replace_once(
        cmdline,
        'static int cmdline_proc_show(struct seq_file *m, void *v)\n{\n',
        'static int cmdline_proc_show(struct seq_file *m, void *v)\n{\n'
        '#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG\n'
        '\tif (static_branch_likely(&susfs_is_fake_cmdline_or_bootconfig_buffer_set)) {\n'
        '\t\tsusfs_spoof_cmdline_or_bootconfig(m);\n'
        '\t\treturn 0;\n'
        '\t}\n'
        '#endif\n',
    )

    avc = ROOT / "security/selinux/avc.c"
    insert_after(
        avc,
        '#include "classmap.h"\n',
        '\n#ifdef CONFIG_KSU_SUSFS\n'
        '#include <linux/jump_label.h>\n'
        'extern u32 susfs_ksu_sid;\n'
        'extern u32 susfs_priv_app_sid;\n'
        'extern struct static_key_false susfs_is_avc_log_spoofing_enabled;\n'
        '#endif\n',
    )

    fdinfo = ROOT / "fs/notify/fdinfo.c"
    text = fdinfo.read_text()
    anchor = '\tinode = igrab(mark->inode);\n\tif (inode) {\n'
    if "susfs_sus_kstat_spoof_inotify_fdinfo(&ino, &dev);" not in text:
        block = r'''
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
		if (susfs_is_current_app_uid()) {
			bool is_fuse = false;

			if (susfs_is_inode_sus_kstat(inode, &is_fuse)) {
				unsigned long ino = inode->i_ino;
				dev_t dev = inode->i_sb->s_dev;
				u32 mask = mark->mask & IN_ALL_EVENTS;

				susfs_sus_kstat_spoof_inotify_fdinfo(&ino, &dev);
				seq_printf(m, "inotify wd:%x ino:%lx sdev:%x mask:%x ignored_mask:%x ",
					   inode_mark->wd, ino, dev, mask, mark->ignored_mask);
				show_mark_fhandle(m, inode);
				seq_putc(m, '\n');
				iput(inode);
				return;
			}
		}
#endif

#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
		if (likely(susfs_is_current_proc_umounted())) {
			struct mount *mnt = real_mount(file->f_path.mnt);

			if (mnt->mnt_id >= DEFAULT_KSU_MNT_ID) {
				struct path path;
				char *pathname = kmalloc(PAGE_SIZE, GFP_KERNEL);
				char *dpath;
				u32 mask = mark->mask & IN_ALL_EVENTS;

				if (!pathname)
					goto orig_flow;
				dpath = d_path(&file->f_path, pathname, PAGE_SIZE);
				if (IS_ERR(dpath))
					goto out_kfree;
				if (kern_path(dpath, 0, &path))
					goto out_kfree;
				if (!d_backing_inode(path.dentry))
					goto out_path_put;

				seq_printf(m, "inotify wd:%x ino:%lx sdev:%x mask:%x ignored_mask:%x ",
					   inode_mark->wd, d_backing_inode(path.dentry)->i_ino,
					   d_backing_inode(path.dentry)->i_sb->s_dev,
					   mask, mark->ignored_mask);
				show_mark_fhandle(m, d_backing_inode(path.dentry));
				seq_putc(m, '\n');
				path_put(&path);
				kfree(pathname);
				iput(inode);
				return;
out_path_put:
				path_put(&path);
out_kfree:
				kfree(pathname);
			}
		}
orig_flow:
#endif
'''
        if anchor not in text:
            raise RuntimeError("fdinfo: inotify insertion anchor not found")
        text = text.replace(anchor, anchor + block, 1)
        fdinfo.write_text(text)

def main() -> int:
    if len(sys.argv) != 2:
        print("usage: apply_susfs_v2.py <upstream-4.9-patch>", file=sys.stderr)
        return 2

    patch = Path(sys.argv[1]).read_text()
    filtered = "".join(filter_hunks(path, section) for path, section in split_sections(patch))
    filtered_path = ROOT / ".susfs-v2-filtered.patch"
    filtered_path.write_text(filtered)

    proc = subprocess.run(
        ["git", "apply", "--reject", "--whitespace=nowarn", str(filtered_path)],
        cwd=ROOT,
        text=True,
    )

    rejects = sorted(ROOT.rglob("*.rej"))
    if rejects:
        for reject in rejects:
            print(f"unexpected reject: {reject.relative_to(ROOT)}", file=sys.stderr)
            print(reject.read_text(), file=sys.stderr)
        return 1
    if proc.returncode:
        print("git apply returned failure without reject files", file=sys.stderr)
        return proc.returncode

    manual_vendor_adaptations()
    filtered_path.unlink(missing_ok=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
