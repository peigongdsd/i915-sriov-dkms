#!/usr/bin/env bash
# Read-only ADL-P diagnostics; writes only the requested output and archive.
set -uo pipefail
umask 077
usage() {
    cat <<'EOF'
Usage: collect-adlp-debug.sh host|guest PCI_BDF OUT
       collect-adlp-debug.sh --help
Example: sudo bash collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-host-failed
Use the PF BDF on the host and the VF BDF as seen inside a Linux guest.
Creates a new OUT directory and OUT.tar.gz; refuses either existing path.
Missing files/failed probe are recorded in collection-status.txt. Reads are timed.
Does not mount filesystems, create VFs, reset devices, enable tracing or install.
EOF
}
if [[ $# == 1 && ($1 == --help || $1 == -h) ]]; then usage; exit 0; fi
if [[ $# != 3 || ($1 != host && $1 != guest) ]]; then usage >&2; exit 2; fi
role=$1
bdf=${2,,}
out=${3%/}
if [[ ! $bdf =~ ^[[:xdigit:]]{4}:[[:xdigit:]]{2}:[[:xdigit:]]{2}\.[0-7]$ || -z $out ]]; then
    printf 'Invalid PCI BDF or output path.\n' >&2; exit 2
fi
for tool in timeout tar gzip cat uname date readlink mkdir; do
    command -v "$tool" >/dev/null || { printf 'Required tool missing: %s\n' "$tool" >&2; exit 2; }
done
if [[ -e $out || -L $out || -e $out.tar.gz || -L $out.tar.gz ]]; then
    printf 'Output directory or archive already exists.\n' >&2; exit 2
fi
mkdir -- "$out" || exit 2
out=$(cd -- "$out" && pwd -P) || exit 2
status=$out/collection-status.txt
printf 'role=%s\nbdf=%s\neuid=%s\n' "$role" "$bdf" "$EUID" > "$status"
capture() {
    local label=$1 seconds=$2 rc
    shift 2
    timeout -k 2s "${seconds}s" "$@" > "$out/$label" 2> "$out/$label.stderr"
    rc=$?
    printf '%s exit=%s\n' "$label" "$rc" >> "$status"
}
read_file() {
    if [[ -r $2 ]]; then capture "$1" 8 cat -- "$2"
    else printf '%s missing-or-unreadable=%s\n' "$1" "$2" >> "$status"; fi
}
capture date.txt 5 date -u --iso-8601=seconds
capture uname.txt 5 uname -a
read_file cmdline.txt /proc/cmdline
read_file os-release.txt /etc/os-release
capture module-file.txt 10 modinfo xe
capture pci.txt 10 lspci -Dnnk -s "$bdf"
capture kernel-journal.txt 30 journalctl -k -b -o short-monotonic --no-pager
capture kernel-dmesg.txt 10 dmesg
for item in version srcversion taint parameters/force_probe parameters/max_vfs parameters/guc_log_level parameters/xelp_enable_ccs; do
    read_file "module-${item//\//_}.txt" "/sys/module/xe/$item"
done
pci=/sys/bus/pci/devices/$bdf
pci_real=$(readlink -f -- "$pci" 2>/dev/null) || pci_real=
for item in vendor device revision subsystem_vendor subsystem_device sriov_numvfs sriov_totalvfs; do
    read_file "pci-$item.txt" "$pci/$item"
done
for item in driver physfn virtfn0 iommu_group; do
    capture "pci-$item-link.txt" 5 readlink -f -- "$pci/$item"
done
shopt -s nullglob
# Capture matching first-hang data before spending time on debugfs.
for dump in /sys/class/devcoredump/devcd*; do
    failing=$(readlink -f -- "$dump/failing_device" 2>/dev/null) || continue
    if [[ -n $pci_real && $failing == "$pci_real" ]]; then
        capture "${dump##*/}-data.txt" 30 cat -- "$dump/data"
    fi
done
debug=
for candidate in /sys/kernel/debug/dri/*; do
    [[ -r $candidate/name ]] || continue
    name=$(timeout -k 2s 3s cat -- "$candidate/name" 2>/dev/null) || continue
    if [[ $name == xe\ * && $name == *"$bdf"* ]]; then debug=$candidate; break; fi
done
if [[ -n $debug ]]; then
    printf 'debugfs=%s\n' "$debug" >> "$status"
    files=(name info sriov_info tile0/ggtt)
    gt=tile0/gt0
    for item in topology workarounds register-save-restore default_lrc_rcs default_lrc_ccs default_lrc_bcs default_lrc_vcs default_lrc_vecs uc/guc_info uc/guc_ctb; do
        files+=("$gt/$item")
    done
    if [[ $role == host && ! -e $pci/physfn && -e $pci/sriov_totalvfs ]]; then
        files+=("$gt/hw_engines" "$gt/uc/guc_log" sriov/pf/vfs sriov/pf/versions)
        for item in ggtt_provisioned ggtt_available; do files+=("sriov/pf/tile0/$item"); done
        for item in contexts_provisioned doorbells_provisioned runtime_registers adverse_events; do
            files+=("sriov/pf/tile0/gt0/$item")
        done
        files+=(sriov/vf1/tile0/ggtt_quota sriov/vf1/tile0/gt0/contexts_quota sriov/vf1/tile0/gt0/doorbells_quota)
    elif [[ $role == guest ]]; then
        for item in self_config abi_versions runtime_regs; do files+=("$gt/vf/$item"); done
    else
        printf 'PF-only reads skipped: supplied host device is not an identifiable PF.\n' >> "$status"
    fi
    for item in "${files[@]}"; do read_file "debug-${item//\//_}.txt" "$debug/$item"; done
else
    printf 'No matching Xe debugfs root; boot logs retained (failed probe/unmounted debugfs/permissions).\n' >> "$status"
fi
# Noclobber also protects the archive against a file appearing during collection.
if ! (set -C; tar -C "$out" -czf - . > "$out.tar.gz"); then
    printf 'Archive creation failed; collected files remain in %s\n' "$out" >&2; exit 1
fi
printf 'Saved %s\nReview collection-status.txt for missing reads/timeouts.\n' "$out.tar.gz"
