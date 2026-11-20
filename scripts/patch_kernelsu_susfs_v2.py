#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KSU_REPO = ROOT / "KernelSU-Next"
KSU = KSU_REPO / "kernel"
EXPECTED_COMMIT = "8af3d4fec33be32fa5d3f8dae4f380fac45bf2cd"

def read(path: str) -> str:
    return (KSU / path).read_text()

def write(path: str, text: str) -> None:
    (KSU / path).write_text(text)

def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"{path}: anchor not found: {old[:100]!r}")
    write(path, text.replace(old, new, 1))

def insert_after(path: str, anchor: str, addition: str) -> None:
    replace_once(path, anchor, anchor + addition)

def patch_legacy_header_compat() -> None:
    """Map split scheduler headers back to linux/sched.h on this Samsung 4.9 tree."""
    split_headers = (
        "linux/sched/signal.h",
        "linux/sched/user.h",
        "linux/sched/task.h",
        "linux/sched/mm.h",
        "linux/sched/coredump.h",
    )
    for header in split_headers:
        if (ROOT / "include" / header).exists():
            continue
        needle_angle = f"#include <{header}>\\n"
        needle_quote = f'#include "{header}"\\n'
        for path in KSU.rglob("*"):
            if not path.is_file() or path.suffix not in {".c", ".h"}:
                continue
            text = path.read_text()
            new = text.replace(needle_angle, "").replace(needle_quote, "")
            if new == text:
                continue
            if "#include <linux/sched.h>" not in new and '#include "linux/sched.h"' not in new:
                new = "#include <linux/sched.h>\\n" + new
            path.write_text(new)

def patch_kconfig() -> None:
    path = "Kconfig"
    text = read(path)
    if 'menu "KernelSU - SUSFS"' in text:
        return
    menu = r'''
menu "KernelSU - SUSFS"

config KSU_SUSFS
    bool "KernelSU addon - SUSFS v2"
    depends on KSU
    depends on THREAD_INFO_IN_TASK
    default y
    help
      Enable SUSFS v2 integration for non-GKI kernels.

config KSU_SUSFS_SUS_PATH
    bool "Hide suspicious paths"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SUS_MOUNT
    bool "Hide suspicious mounts"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SUS_KSTAT
    bool "Spoof suspicious kstat"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SPOOF_UNAME
    bool "Spoof uname"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_ENABLE_LOG
    bool "Enable SUSFS logging"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_HIDE_KSU_SUSFS_SYMBOLS
    bool "Hide KernelSU and SUSFS symbols from kallsyms"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
    bool "Spoof proc cmdline or bootconfig"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_OPEN_REDIRECT
    bool "Open redirect"
    depends on KSU_SUSFS
    default y

config KSU_SUSFS_SUS_MAP
    bool "Hide suspicious mmap files"
    depends on KSU_SUSFS
    default y

endmenu

'''
    pos = text.rfind("\nendmenu")
    if pos < 0:
        raise RuntimeError("Kconfig: final endmenu not found")
    write(path, text[:pos] + "\n" + menu + text[pos:])

def patch_core_init() -> None:
    insert_after(
        "core/init.c",
        '#include "ksu.h"\n',
        '#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs.h>\n#endif\n',
    )
    insert_after(
        "core/init.c",
        '\tksu_app_profile_init();\n',
        '\n#ifdef CONFIG_KSU_SUSFS\n\tsusfs_init();\n#endif\n',
    )

def patch_selinux() -> None:
    h = "selinux/selinux.h"
    text = read(h)
    if "susfs_is_current_ksu_domain" not in text:
        block = r'''
#ifdef CONFIG_KSU_SUSFS
bool susfs_is_sid_equal(const struct cred *cred, u32 sid2);
u32 susfs_get_sid_from_name(const char *secctx_name);
u32 susfs_get_current_sid(void);
void susfs_set_zygote_sid(void);
bool susfs_is_current_zygote_domain(void);
void susfs_set_ksu_sid(void);
bool susfs_is_current_ksu_domain(void);
void susfs_set_init_sid(void);
bool susfs_is_current_init_domain(void);
void susfs_set_priv_app_sid(void);
#endif

'''
        pos = text.rfind("\n#endif")
        if pos < 0:
            raise RuntimeError("selinux.h: final endif not found")
        write(h, text[:pos] + "\n" + block + text[pos:])

    c = "selinux/selinux.c"
    text = read(c)
    if "u32 susfs_ksu_sid" not in text:
        block = r'''
#ifdef CONFIG_KSU_SUSFS
#define KERNEL_PRIV_APP_DOMAIN "u:r:priv_app:s0:c512,c768"

u32 susfs_ksu_sid;
u32 susfs_init_sid;
u32 susfs_zygote_sid;
u32 susfs_priv_app_sid;

static void susfs_set_sid(const char *secctx_name, u32 *out_sid)
{
    int err;

    if (!secctx_name || !out_sid)
        return;

    err = security_secctx_to_secid(secctx_name, strlen(secctx_name), out_sid);
    if (err) {
        pr_warn("susfs: failed resolving %s: %d\n", secctx_name, err);
        *out_sid = 0;
    }
}

bool susfs_is_sid_equal(const struct cred *cred, u32 sid2)
{
    const struct task_security_struct *tsec;

    if (!cred || !sid2)
        return false;
    tsec = selinux_cred(cred);
    return tsec && tsec->sid == sid2;
}

u32 susfs_get_sid_from_name(const char *secctx_name)
{
    u32 sid = 0;

    if (secctx_name)
        susfs_set_sid(secctx_name, &sid);
    return sid;
}

u32 susfs_get_current_sid(void)
{
    return current_sid();
}

void susfs_set_zygote_sid(void)
{
    susfs_set_sid(ZYGOTE_CONTEXT, &susfs_zygote_sid);
}

bool susfs_is_current_zygote_domain(void)
{
    return susfs_zygote_sid && current_sid() == susfs_zygote_sid;
}

void susfs_set_ksu_sid(void)
{
    susfs_set_sid(KERNEL_SU_CONTEXT, &susfs_ksu_sid);
}

bool susfs_is_current_ksu_domain(void)
{
    return susfs_ksu_sid && current_sid() == susfs_ksu_sid;
}

void susfs_set_init_sid(void)
{
    susfs_set_sid(INIT_CONTEXT, &susfs_init_sid);
}

bool susfs_is_current_init_domain(void)
{
    return susfs_init_sid && current_sid() == susfs_init_sid;
}

void susfs_set_priv_app_sid(void)
{
    susfs_set_sid(KERNEL_PRIV_APP_DOMAIN, &susfs_priv_app_sid);
}
#endif

'''
        anchor = "void escape_to_root_for_adb_root(void)\n"
        if anchor not in text:
            raise RuntimeError("selinux.c: escape_to_root anchor not found")
        write(c, text.replace(anchor, block + anchor, 1))

    rules = "selinux/rules.c"
    text = read(rules)
    if "susfs_set_priv_app_sid();" not in text:
        anchor = "\treset_avc_cache();\n#endif\n}\n\n#define KSU_SEPOLICY_MAX_BATCH_SIZE"
        replacement = (
            "\treset_avc_cache();\n#endif\n"
            "#ifdef CONFIG_KSU_SUSFS\n"
            "\tsusfs_set_priv_app_sid();\n"
            "\tsusfs_set_init_sid();\n"
            "\tsusfs_set_ksu_sid();\n"
            "\tsusfs_set_zygote_sid();\n"
            "#endif\n"
            "}\n\n#define KSU_SEPOLICY_MAX_BATCH_SIZE"
        )
        if anchor not in text:
            raise RuntimeError("rules.c: apply rules tail anchor not found")
        write(rules, text.replace(anchor, replacement, 1))

def patch_supercall() -> None:
    path = "supercall/supercall.c"
    insert_after(
        path,
        '#include <linux/utsname.h> // utsname() and uts_sem\n',
        '#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs.h>\n#endif\n',
    )
    text = read(path)
    if "magic2 == SUSFS_MAGIC" in text:
        return

    anchor = "#endif\n\n\t// Check if this is a request to install KSU fd\n"
    block = r'''#endif

#ifdef CONFIG_KSU_SUSFS
	if (magic2 == SUSFS_MAGIC && current_uid().val == 0) {
		switch (cmd) {
#ifdef CONFIG_KSU_SUSFS_SUS_PATH
		case CMD_SUSFS_ADD_SUS_PATH:
			susfs_add_sus_path(arg);
			break;
		case CMD_SUSFS_ADD_SUS_PATH_LOOP:
			susfs_add_sus_path_loop(arg);
			break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MOUNT
		case CMD_SUSFS_HIDE_SUS_MNTS_FOR_NON_SU_PROCS:
			susfs_set_hide_sus_mnts_for_non_su_procs(arg);
			break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_KSTAT
		case CMD_SUSFS_ADD_SUS_KSTAT:
		case CMD_SUSFS_ADD_SUS_KSTAT_STATICALLY:
			susfs_add_sus_kstat(arg);
			break;
		case CMD_SUSFS_UPDATE_SUS_KSTAT:
			susfs_update_sus_kstat(arg);
			break;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_UNAME
		case CMD_SUSFS_SET_UNAME:
			susfs_set_uname(arg);
			break;
#endif
#ifdef CONFIG_KSU_SUSFS_ENABLE_LOG
		case CMD_SUSFS_ENABLE_LOG:
			susfs_enable_log(arg);
			break;
#endif
#ifdef CONFIG_KSU_SUSFS_SPOOF_CMDLINE_OR_BOOTCONFIG
		case CMD_SUSFS_SET_CMDLINE_OR_BOOTCONFIG:
			susfs_set_cmdline_or_bootconfig(arg);
			break;
#endif
#ifdef CONFIG_KSU_SUSFS_OPEN_REDIRECT
		case CMD_SUSFS_ADD_OPEN_REDIRECT:
			susfs_add_open_redirect(arg);
			break;
#endif
#ifdef CONFIG_KSU_SUSFS_SUS_MAP
		case CMD_SUSFS_ADD_SUS_MAP:
			susfs_add_sus_map(arg);
			break;
#endif
		case CMD_SUSFS_ENABLE_AVC_LOG_SPOOFING:
			susfs_set_avc_log_spoofing(arg);
			break;
		case CMD_SUSFS_SHOW_ENABLED_FEATURES:
			susfs_get_enabled_features(arg);
			break;
		case CMD_SUSFS_SHOW_VARIANT:
			susfs_show_variant(arg);
			break;
		case CMD_SUSFS_SHOW_VERSION:
			susfs_show_version(arg);
			break;
		default:
			break;
		}
		return 0;
	}
#endif

	// Check if this is a request to install KSU fd
'''
    if anchor not in text:
        raise RuntimeError("supercall.c: install fd anchor not found")
    write(path, text.replace(anchor, block, 1))

def patch_setuid() -> None:
    path = "hook/setuid_hook.c"
    insert_after(path, '#include <linux/uidgid.h>\n', '#include <linux/workqueue.h>\n')
    insert_after(
        path,
        '#include "compat/kernel_compat.h"\n',
        '#ifdef CONFIG_KSU_SUSFS\n'
        '#include <linux/susfs_def.h>\n'
        '#include "selinux/selinux.h"\n'
        'extern struct work_struct susfs_extra_works;\n'
        '#endif\n',
    )

    text = read(path)
    marker = "susfs_set_current_proc_umounted();"
    if marker in text:
        return
    anchor = "    // Handle kernel umount\n    ksu_handle_umount(old_uid, new_uid);\n"
    addition = r'''
#ifdef CONFIG_KSU_SUSFS
    /*
     * SUSFS v2 keys most VFS hiding to a per-thread flag. Zygote children
     * become application UIDs during setresuid(), which is the same point
     * KernelSU uses for its mount-namespace cleanup.
     */
    if (is_zygote(current_cred()) && (new_uid % 100000) >= 10000) {
        susfs_set_current_proc_umounted();
        if (!work_pending(&susfs_extra_works))
            schedule_work(&susfs_extra_works);
    }
#endif
'''
    if anchor not in text:
        raise RuntimeError("setuid_hook.c: kernel umount anchor not found")
    write(path, text.replace(anchor, anchor + addition, 1))

def patch_boot_event() -> None:
    path = "supercall/dispatch.c"
    insert_after(
        path,
        '#include "supercall/supercall.h"\n',
        '#ifdef CONFIG_KSU_SUSFS\n#include <linux/susfs.h>\n#endif\n',
    )
    text = read(path)
    if "susfs_start_sdcard_monitor_fn();" in text:
        return
    anchor = "\t\t\t\ton_boot_completed();\n"
    addition = "#ifdef CONFIG_KSU_SUSFS\n\t\t\t\tsusfs_start_sdcard_monitor_fn();\n#endif\n"
    if anchor not in text:
        raise RuntimeError("dispatch.c: boot completed anchor not found")
    write(path, text.replace(anchor, anchor + addition, 1))

def patch_kbuild() -> None:
    path = "Kbuild"
    text = read(path)
    if "SUSFS_VERSION:" in text:
        return
    addition = r'''
# Report the SUSFS core paired with this KernelSU build.
ifneq ($(wildcard $(srctree)/include/linux/susfs.h),)
SUSFS_VERSION := $(shell sed -n 's/^#define SUSFS_VERSION "\(.*\)"/\1/p' $(srctree)/include/linux/susfs.h)
$(info -- SUSFS_VERSION: $(SUSFS_VERSION))
endif

'''
    anchor = "obj-$(CONFIG_KSU) += kernelsu.o\n\n"
    if anchor not in text:
        raise RuntimeError("Kbuild: obj anchor not found")
    write(path, text.replace(anchor, anchor + addition, 1))

def main() -> None:
    head = subprocess.check_output(
        ["git", "-C", str(KSU_REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    if head != EXPECTED_COMMIT:
        raise RuntimeError(
            f"KernelSU checkout is {head}, expected exact v3.4.0-legacy {EXPECTED_COMMIT}"
        )

    patch_legacy_header_compat()
    patch_kconfig()
    patch_core_init()
    patch_selinux()
    patch_supercall()
    patch_setuid()
    patch_boot_event()
    patch_kbuild()

    print("Patched exact KernelSU-Next v3.4.0-legacy for SUSFS v2.3.0.")

if __name__ == "__main__":
    main()
