# ADL-P Windows Code 43: supplied-log follow-up

2026-10-02. MTL work is paused at the user's request. This note analyzes the supplied 82-line host log; the assistant has not reproduced this machine's failure. The exact running driver commit, Windows driver version, Windows hypervisor state and complete host log were not supplied with that excerpt.

**Latest user result:** enabling the correct Xe CCS option still leaves Windows with Code 43. The configuration correction alone is therefore insufficient. The ordered CCS test below is retained as the historical experiment, not a recommendation to repeat it. Collect the current failing boot before further parameter or driver changes; the archive will also establish effective CCS state and the loaded module identity. No new host or Windows trace accompanied this result.

## First actionable finding

The active ADL-P PF driver is **Xe**, but the boot command line contains `i915.xelp_enable_ccs=1`. At 8.725 seconds the log explicitly says i915 ignored that unknown parameter. This cannot enable Xe's independent parameter. Current DKMS defaults `xe.xelp_enable_ccs` to false, and its September 16 change recommends `xe.xelp_enable_ccs=1` for Windows guest problems on Xe_LP, including ADL.

The absence of Xe's `Enabling experimental CCS0 on Xe_LP` message in this excerpt supports checking CCS first. It does not replace reading the effective parameter: a separate modprobe configuration could set it even when the boot command line does not.

Sources: [current base README](https://github.com/strongtz/i915-sriov-dkms/blob/f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88/README.md#L55), [maintainer explanation, PR 484](https://github.com/strongtz/i915-sriov-dkms/pull/484), [parameter definition](https://github.com/strongtz/i915-sriov-dkms/blob/f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88/drivers/gpu/drm/xe/xe_module.c#L88), and [existing implementation](https://github.com/strongtz/i915-sriov-dkms/commit/2024842930ebacf088929be43af0ce79b33cf0e7).

This is a strong configuration lead, **not yet a demonstrated explanation of Code 43**. The option is a DKMS extension, not a stock upstream Xe parameter. It adds CCS0 to the engine mask, enables its RCU_MODE programming through existing RTP, and selects the associated 47-bit GPU virtual-address configuration. This is not an IOMMU DMA-width change. The current published ADL-P branch already contains it; no new driver patch is needed to try the correct option.

The subsequently supplied `hardware-configuration.nix` confirms that Xe is loaded in the initrd and `pkgs.xe-sriov` is selected. Its `options xe` line has no `xelp_enable_ccs` override; the boot argument at line 147 targets i915. It also configures `kvm_intel nested=0`. These are configuration facts, not proof of the running module values; check `/sys/module/kvm_intel/parameters/nested` if nested virtualization remains in question. The exact implementation of `pkgs.xe-sriov` is outside this file, so it does not establish the source commit or whether the timestamp backport is in the installed module.

A corrected local copy changes only the CCS comment and the one boot argument. `nix-instantiate --parse` passed. No NixOS build or activation was performed. The small [configuration patch](patches/adlp/adlp-xe-ccs.patch) is published with this note; the full machine-specific configuration is retained locally, not in the public repository.

## What the supplied log establishes

| Host time | Evidence | Interpretation |
|---|---|---|
| 2.599 s | ADL-P PCI `8086:46a6`, PF mode, D0 display stepping | The ADL-P PF probes under the DKMS Xe module. The banner alone does not identify the exact built commit. |
| 2.634 s | ADL-P GuC `70.49.4` | Actual firmware identity for this PF. DG2's later `70.53.0` belongs to a different GPU. |
| 8.995–9.146 s | VF1: 2 GiB GGTT, 32768 context IDs, 128 doorbells; one VF enabled | Provisioning completed; this does not establish successful Windows driver initialization. |
| 93.335 s | RCS reset, GuC ID 57, timed-out `.org.gnome.Naut` job, coredump created | A host userspace render queue hung. This is not a Linux VF's initial `emit_wa_job` failure and does not identify a Windows guest context. |
| 107.943 and 108.072 s | `VF1 FLR` | GuC reported VF function-level resets. These messages do not say FLR failed, and do not identify who requested it. |

The RCS reset state `0x3` is the host queue's REGISTERED and ENABLED bits. The large sequence number `4294967169` is Xe's intentional initial fence sequence (`-127` as unsigned), not evidence of sequence-number corruption. The reset handler obtains this queue from the Linux host's GuC submission registry. A shared-engine interaction remains possible, but the log cannot prove that Windows caused the host hang or that the host hang caused Code 43.

The two migration-disabled notices are feature limitations, not startup failures. One is about memory-based interrupts; the other requires GuC 70.54 for migration. Neither establishes that this ADL-P guest needs a GuC upgrade to start. Keep firmware fixed for the first configuration comparison.

The excerpt appears filtered. The absence of DMAR/IOMMU or VFIO errors here does not establish their absence from the full boot log. Host timestamps also do not establish when Windows displayed Code 43; record VM start and failure times for the next run.

## Ordered retest

### 1. Save the current failure before rebooting

From the repository root on the ADL-P host, using the current branch's collector:

```sh
sudo bash docs/xe-sriov/collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-before-ccs
```

It creates `/tmp/adlp-before-ccs.tar.gz`. The supplied log explicitly identifies `/sys/class/drm/card0/device/devcoredump/data`; the collector matches the PCI device rather than assuming card numbering. Capture immediately if the dump still exists: these dumps expire. A missing expired dump is not proof there was no hang. The updated collector includes the effective `xelp_enable_ccs` value and the saved CCS context image if available.

### 2. Check and, if necessary, correct the Xe option

```sh
cat /sys/module/xe/parameters/xelp_enable_ccs
```

- `N`: test the correct Xe option below.
- `Y`: this setting is already active; the mistyped boot argument is not the explanation by itself. Retain that result and continue with Windows status/full host diagnostics.
- Missing file: identify the loaded module build before assuming this DKMS extension exists in it.

In the host's existing NixOS `boot.kernelParams`, replace the attempted `i915.xelp_enable_ccs=1` with:

```nix
"xe.xelp_enable_ccs=1"
```

Preserve the existing IOMMU, force-probe, VF-count and unrelated settings. Build the boot configuration using the machine's normal NixOS workflow and reboot the host. This parameter is read-only after module initialization; do not try to write `Y` to sysfs or unload the active display driver. Use the same patched driver build and GuC firmware for this comparison.

After boot, verify:

```sh
cat /sys/module/xe/parameters/xelp_enable_ccs
sudo journalctl -k -b --no-pager | rg 'Enabling experimental CCS0|Restricting VA bits|alderlake_p|Using GuC firmware|Enabled .* VFs'
```

Expect `Y` and the ADL-P CCS-enable message. If the PF now fails probing with a CCS `emit_wa_job` timeout, stop this test and save its first error; do not interpret failure to reach the VM as Windows Code 43.

Cold-start the same Windows VM with one VF. Keep its Intel driver, PCI topology, RAM and Hyper-V settings unchanged in this first comparison, so only the Xe CCS configuration changes. Keep a previous boot generation available because this option is experimental. A clean host boot also prevents the earlier PF hang from contaminating the next result.

### 3. Record the first new result

Run the host collector immediately after either successful guest startup or the first failure, using a fresh output path:

```sh
sudo bash docs/xe-sriov/collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-after-ccs
```

Record whether the PF hung before the guest was started, while Windows was loading the GPU driver, or only afterwards. If the host hangs again without any guest running, native ADL-P Xe stability needs its own coredump analysis. A host-only timestamp fix remains relevant to that path, but its existence does not establish a cure.

For libvirt, also retain the exact active VM definition (`virsh dumpxml <domain>`) and the VM's startup log. Do not infer nested Hyper-V merely from QEMU's Hyper-V enlightenment flags.

Inside Windows, run these read-only commands in PowerShell and retain their output:

```powershell
Get-CimInstance Win32_PnPSignedDriver |
  Where-Object DeviceClass -eq 'DISPLAY' |
  Format-List DeviceName, DeviceID, DriverVersion, DriverDate, InfName

$intelDisplay = Get-PnpDevice -Class Display -PresentOnly |
  Where-Object InstanceId -like 'PCI\VEN_8086*'
$intelDisplay | Format-List Status, FriendlyName, InstanceId, Problem
foreach ($gpu in $intelDisplay) {
  Get-PnpDeviceProperty -InstanceId $gpu.InstanceId -KeyName `
    'DEVPKEY_Device_ProblemCode', 'DEVPKEY_Device_ProblemStatus' |
    Format-List KeyName, Data
}

bcdedit /enum '{current}'
Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard |
  Format-List VirtualizationBasedSecurityStatus, SecurityServicesConfigured, SecurityServicesRunning
```

Also save the Windows System event log and any available DxgKrnl startup-error event, including the full XML/status and timestamp. `DEVPKEY_Device_ProblemStatus` supplies an NTSTATUS in addition to generic Code 43; see [Microsoft's property definition](https://learn.microsoft.com/en-us/windows-hardware/drivers/install/devpkey-device-problemstatus). Decimal 3221225485 corresponds to `0xC000000D` (`STATUS_INVALID_PARAMETER`), but that status is still not unique to the nested-classifier defect. Absence of one particular event number is not proof of success.

### 4. If CCS is active and Code 43 persists, separate the nested case

The supplied host configuration sets `nested=0`, so this is secondary to the CCS correction; do not enable nesting for the first retest. If the effective host/VM configuration nevertheless allows Windows Hyper-V/VBS to run, make a separate controlled boot with Windows' hypervisor launch disabled. In an elevated Windows terminal, first retain the current setting and then use:

```powershell
bcdedit /enum '{current}'
bcdedit /set '{current}' hypervisorlaunchtype off
```

Restart Windows fully; for this comparison do not resume a saved VM state or hibernation image. WSL2, Hyper-V guests and VBS protections will be unavailable during this diagnostic boot. Restore the recorded prior value afterwards: typically `bcdedit /set '{current}' hypervisorlaunchtype auto`, or `bcdedit /deletevalue '{current}' hypervisorlaunchtype` if the setting was originally absent. See [Microsoft's BCDEdit reference](https://learn.microsoft.com/en-us/windows-hardware/drivers/devtest/bcdedit--set).

Hold the corrected PF CCS configuration fixed across this pair. If disabling the Windows hypervisor changes failure to success, that prioritizes the independently observed Windows classification path. Intel still acknowledges that defect in [KB 000102878](https://www.intel.com/content/www/us/en/support/articles/000102878/graphics.html). The KB's named hardware is newer than ADL-P; our separate 7092 binary analysis supports investigating the same classification issue in the ADL driver lane, but does not establish that it caused this user's failure.

`HypervisorPresent=True` inside a KVM guest is insufficient to prove that Windows launched its own hypervisor. Likewise, host `kvm_intel.nested=Y` only enables a host capability. Keep these distinct from the guest's boot policy and actual VBS/Hyper-V activity.

## If further PF/VF tracing is needed

Capture `sriov/pf/versions`, `sriov/pf/tile0/gt0/adverse_events`, `runtime_registers`, and GuC state during startup before VF teardown. A VF FLR clears its negotiated ABI and monitoring counters, so a post-teardown zero does not prove that the guest never negotiated or encountered an event. The collector already captures the selected snapshots.

Existing `xe:xe_guc_ctb_h2g` and `xe:xe_guc_ctb_g2h` tracepoints expose the outer action, message length and buffer positions. They do **not** expose the entire relay payload/VFID/inner query, so they cannot alone establish what Windows requested. Detailed relay debug output is compiled out without `CONFIG_DRM_XE_DEBUG_SRIOV`; enabling dynamic debug cannot recover omitted callsites. Request a targeted trace only if the simpler configuration and Windows-state comparison leave initialization unresolved.

Current DKMS's ADL runtime-register export already includes `0x9144`. Working i915 additionally exports `CTC_MODE` and `TIMESTAMP_OVERRIDE`; no evidence yet shows that the installed Windows driver fails because those two are absent from Xe's reply. Do not blindly port that table before capturing the actual guest request and failing stage.

## Status of the earlier patch

The branch's accepted timestamp correction remains a legitimate Linux Xe fix. It changes Linux-created contexts; Windows builds its own VF contexts. This new case does not validate that patch as a Windows startup repair. The correct existing Xe CCS option has now been tried without resolving Code 43. The immediate next step is a fresh host capture and the Windows device startup status; a nested-Hyper-V discriminator remains conditional on evidence that Windows actually launches its hypervisor. No additional kernel workaround or MTL change was introduced for this log.
