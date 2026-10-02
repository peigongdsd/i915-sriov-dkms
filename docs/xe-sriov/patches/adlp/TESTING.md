# ADL-P Xe SR-IOV validation

This is a hardware test plan for the ADL-P timestamp-workaround backport. No command below has been run against a GPU in this study. Kernel installation, host configuration, VF creation and VM startup are performed by the user in the target test environment.

The patch fixes duplicate emission of Wa_16010904313 in Xe's context restore code. Successful compilation does not establish that it fixes the reported failed vGPU. Keep the first failure stage and the guest driver explicit.

## Collecting a result

The [read-only collector](../../collect-adlp-debug.sh) captures boot identity, full kernel logs, the selected files listed below, and any existing devcoredump matching the supplied BDF. From the repository root, run on the host and separately inside the Linux guest:

```sh
sudo bash docs/xe-sriov/collect-adlp-debug.sh host 0000:00:02.0 /tmp/adlp-host-failed
sudo bash docs/xe-sriov/collect-adlp-debug.sh guest 0000:00:08.0 /tmp/adlp-guest-failed
```

Replace the examples with the actual host PF and guest VF BDFs. Use a fresh output path for every baseline/patched run. Each command creates that directory and `<OUT>.tar.gz`, refusing existing outputs. Read `collection-status.txt` for missing files, permissions and timeouts. Run immediately after the first failure; failed probe may leave no guest debugfs files, but boot logs are still collected. The collector does not mount debugfs, provision VFs, reset devices, enable tracing or install anything. It is a Linux collector; use `host` for the Linux PF when the guest is Windows and preserve Windows driver/device/error information separately.

## What the patch can change

| Host PF | Guest VF | Code affected by a Linux Xe patch |
|---|---|---|
| Xe | Linux Xe | Host Xe contexts and guest Xe contexts, when both kernels include the patch. This is the primary test. |
| Xe | Windows Intel driver | Linux PF contexts only. The Windows driver builds guest VF contexts; it does not execute Linux `xe_lrc.c`. A Linux guest fix does not prove a Windows guest fix. |
| i915-sriov-dkms | Its known-working guest driver | Existing working control. Preserve its precise driver/firmware versions; this is a separate implementation. |

Start with one VF, default provisioning, no migration, and otherwise identical host/guest configuration. For the first **Linux VF** comparison, preserve upstream's CCS-disabled baseline: the upstream ADL-P engine descriptor does not expose CCS0. Its absence is not a failed Linux test. **Windows is a separate compatibility test:** current DKMS recommends `xe.xelp_enable_ccs=1` for affected Windows guests on Xe_LP. That existing option enables CCS0 and its register programming; `i915.xelp_enable_ccs=1` cannot enable it in Xe. Confirm `/sys/module/xe/parameters/xelp_enable_ccs` reports `Y`, and retain the boot's CCS-enable message. See the [Windows Code 43 follow-up](../../adlp-windows-code43-triage.md) for the supplied log and the first targeted retest. Do not require Linux VF success before trying this Windows-specific configuration correction.

## Build and identity record

Record all of the following for the baseline and patched run:

- This branch starts from DKMS upstream `f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88` and adds the timestamp fix as `32d16259df98d7153daaa9b8c461c2eaa0d24394` (upstream `38631a7bce195b88814b93bf2b6d3e48c827fef2`). The local module build used Linux 7.2.8 headers. Mainline `ce1e0223d8ad4211275c82a17ed6d43ab81e13d9` is the separate source-audit snapshot cited below. Include the actual built driver commit and kernel configuration for both host and Linux guest; distinct release suffixes help identify booted artifacts.
- PF/VF PCI vendor/device IDs and BDFs, hypervisor and VM definition, guest OS/driver version, boot command line, loaded `xe` module path/version/srcversion, and GuC firmware actually reported by the PF. “Latest” package names do not identify the loaded binary.
- BIOS/firmware version and IOMMU mode. Keep these constant during the two-run comparison.
- `CONFIG_DEBUG_FS`, `CONFIG_DRM_XE`, `CONFIG_PCI_IOV` on the host, and `CONFIG_DEV_COREDUMP`. `CONFIG_DRM_XE_DEBUG` or `CONFIG_DRM_XE_DEBUG_SRIOV` additionally expose VF runtime-register dumps; their absence only removes that diagnostic file.

Examples of identity capture, run separately on host and Linux guest after the chosen kernel is booted:

```sh
uname -a
cat /proc/cmdline
modinfo xe
lspci -Dnnk
cat /sys/module/xe/parameters/force_probe
cat /sys/module/xe/parameters/max_vfs
journalctl -k -b -o short-monotonic --no-pager > kernel-boot.txt
```

Use the actual ADL-P PCI ID for force-probe configuration; do not substitute another report's ADL-S ID. Read the host PF's `/sys/bus/pci/devices/<PF-BDF>/sriov_numvfs`, `sriov_totalvfs`, and the `virtfn0` symlink to verify that exactly one VF was provisioned and which function was assigned. The guest BDF can differ from the host VF BDF. A module file on disk is not proof that that module is the one currently running; correlate it with the booted release and logs.

For the cleanest first comparison, use baseline PF + baseline Linux VF, then patched PF + patched Linux VF with the same firmware and userspace. If the outcome changes, an optional crossed comparison (patched PF + baseline VF, then baseline PF + patched VF) localizes the necessary side. Keep both sides on the same base kernel during that experiment; the patch does not intentionally change the PF/VF ABI.

## Source-backed capture locations

Identify the right DRM debugfs root by its `name` file and the PCI BDF. Do not assume it is `/sys/kernel/debug/dri/0`: numbering differs between host and guest. Below, `D` means that device's actual DRM debugfs directory. Modern canonical GT paths are `D/tile0/gt0`; `D/gt0` is a compatibility symlink. ADL-P has one GT.

| Where | Files to preserve | Meaning |
|---|---|---|
| PF and Linux VF | `D/info`, `D/sriov_info` | Device capabilities and PF/VF mode. |
| PF and Linux VF | `D/tile0/ggtt`, `D/tile0/gt0/topology`, `D/tile0/gt0/workarounds`, `D/tile0/gt0/register-save-restore` | GGTT allocator state, virtualized topology and programmed workaround lists. The GGTT allocator dump alone is not a raw-PTE/DMA-address proof. |
| PF and Linux VF | `D/tile0/gt0/default_lrc_rcs`, `default_lrc_ccs`, `default_lrc_bcs`, `default_lrc_vcs`, `default_lrc_vecs` | Saved default context image per engine class, after successful capture. An absent engine can print `No default LRC for class ...`. |
| PF and Linux VF | `D/tile0/gt0/uc/guc_info`, `D/tile0/gt0/uc/guc_ctb` | GuC/interface state and CTB state. |
| PF only | `D/tile0/gt0/hw_engines`, `D/tile0/gt0/uc/guc_log` | Physical engine state and GuC firmware log. These files are deliberately not exposed by Xe VF. |
| PF only | `D/sriov/pf/vfs`, `D/sriov/pf/versions` | VF summary and PF service versions. |
| PF only | `D/sriov/pf/tile0/ggtt_provisioned`, `D/sriov/pf/tile0/ggtt_available` | Assigned and available GGTT intervals. |
| PF only | `D/sriov/pf/tile0/gt0/contexts_provisioned`, `doorbells_provisioned`, `runtime_registers`, `adverse_events` | Provisioning, runtime-register export, and GuC adverse-event counters. |
| PF only | `D/sriov/vf1/tile0/ggtt_quota`, `D/sriov/vf1/tile0/gt0/contexts_quota`, `doorbells_quota` | Quotas of the first VF; these are not generic guest paths. Read only for the initial comparison. |
| Linux VF only | `D/tile0/gt0/vf/self_config`, `abi_versions`, and optionally `runtime_regs` | The guest's actual allocation/ABI and mediated register snapshot. `runtime_regs` depends on debug configuration. |

Preserve copies before workload execution and immediately after the first failure. Do not recursively read every debugfs file: some read handlers, such as control/debug hooks, have side effects. The table names the intended diagnostic files.

The path registrations are verified in [xe_gt_debugfs.c](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_gt_debugfs.c#L221), [xe_guc_debugfs.c](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_guc_debugfs.c#L112), [xe_gt_sriov_vf_debugfs.c](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_gt_sriov_vf_debugfs.c#L25), [xe_sriov_pf_debugfs.c](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_sriov_pf_debugfs.c#L340), and [xe_tile_sriov_pf_debugfs.c](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_tile_sriov_pf_debugfs.c#L80).

Capture a devcoredump immediately when present by reading `/sys/class/drm/card<N>/device/devcoredump/data`, or `/sys/class/devcoredump/devcd<M>/data` after verifying its `failing_device` symlink. It is the first captured hang, can outlive reset recovery, and expires. Preserve it before any reset/reboot; a missing dump does not prove no failure occurred. See [xe_devcoredump.c](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_devcoredump.c#L32).

## Stage 1: first Linux VF context, before Mesa

Save complete host and guest kernel logs from VF creation through VF probe. Retain the first DMAR/IOMMU fault, requester BDF and address, first CAT/GuC error, engine name, GuC context ID and errno. Later reset messages can be consequences.

The initial default-context job in [xe_gt.c](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_gt.c#L385) uses a kernel queue with no VM, submits a GGTT batch, and switches to a second context to save the result. It is not a Mesa VM_BIND test. An `hwe rcs0: emit_wa_job failed (-ETIME)` means that this early stage has failed; skip userspace performance tests until it succeeds.

Current Xe deliberately triggers an engine watchdog reset while obtaining a clean VF default context. One such event can be expected; failure to recover, CAT/DMAR errors, repeated reset storms, or probe failure are not expected. Record the event sequence rather than treating every reset line as equivalent.

If probe fails, the VF's debugfs tree/default-LRC files may never be available. Host logs and any devcoredump remain useful. A successful PF `default_lrc_rcs` dump is not a substitute for the failed VF's context. If another diagnostic patch is required, capture the following **before the initial queue/batch are freed**:

- Stage (`initial WA`, `expected watchdog/reset`, `NOP context switch`, `default image saved`), engine class/instance, VFID and GuC ID.
- Batch/ring/LRC/HWSP GGTT addresses and their DMA/IOMMU addresses; PF-owned PTE VFID/present bits. Match the first DMAR address to these objects rather than to a guessed page table.
- CPU-side context-image ring head/tail, completion sequence/fence status, `CTX_CS_INDIRECT_CTX` and `CTX_CS_INDIRECT_CTX_OFFSET`. Read context memory through Xe helpers; do not issue privileged PF-only MMIO reads from the VF.

Existing tracepoints `xe:xe_sched_job_create`, `xe:xe_sched_job_exec`, `xe:xe_sched_job_run`, `xe:xe_sched_job_timedout` and `xe:xe_sched_job_set_error` include GuC ID, GT ID, sequence numbers and batch address ([xe_trace.h](https://github.com/torvalds/linux/blob/ce1e0223d8ad4211275c82a17ed6d43ab81e13d9/drivers/gpu/drm/xe/xe_trace.h#L236)). They are useful if tracing is armed before the failing probe; starting a recorder after probe failure cannot recover those earlier events.

The default-LRC debug dump skips the hardware-status page and numbers dwords within register state. `CTX_CS_INDIRECT_CTX_OFFSET` is dword `0x17` in that state layout, not byte offset `0x17` in the raw BO. Preserve the whole decoded dump. If separately testing the pending offset hypothesis, `0xd` is the field value and `0x340` is its bits-[15:6] register encoding. This backport does not add that speculative change.

## Stage 2: per-engine Linux VF execution

After the VF probes and its render node is usable, run IGT in the Linux guest containing only the intended Xe VF, or select that device using the installed IGT build's documented device selector. Record the IGT version and full dynamic-subtest output. Start with the existing `xe_exec_basic` cases:

```sh
xe_exec_basic --list-subtests
xe_exec_basic --run-subtest once-basic
xe_exec_basic --run-subtest twice-basic
xe_exec_basic --run-subtest many-execqueues-basic
xe_exec_basic --run-subtest many-execqueues-many-vm-basic
```

Run these in order, saving host/guest logs and stopping at the first failed stage. The current official [xe_exec_basic.c](https://gitlab.freedesktop.org/drm/igt-gpu-tools/-/blob/master/tests/intel/xe_exec_basic.c) iterates every enumerated engine and verifies a GPU-written `0xc0ffee` result. `once-basic` separates basic user submission from probe; multiple-queue/multiple-VM cases exercise the context switches this patch changes. Preserve individual render/copy/video/VEBox results, including unsupported/skipped cases. These tiny MI jobs do not certify rendering, codec correctness or OpenCL support.

Only after these pass, run one known reproducible render/Vulkan workload and one media decode/encode workload already used with the working i915 VF, confirming that each actually selected the VF rather than software rendering. Then add repeated guest start/stop and a second VF as separate stages; do not mix them into the first single-VF result. A handful of successes is insufficient for an intermittent regression: use the same previously failing workload and exposure time for both builds and record the counts.

## Interpreting the comparison

| Observation | Next conclusion/action |
|---|---|
| Patched Linux VF still fails in initial `emit_wa_job` with the same first fault | The real timestamp fix was insufficient. Continue the GGTT/context/GuC/reset localization; do not label the vGPU fixed. |
| Probe succeeds but `once-basic` fails | Investigate user VM_BIND/PPGTT and first user submission, with the per-engine failure and coredump. |
| Single submissions pass; context-switch tests improve only with the patched VF | Consistent with the repaired VF context-restore path; repeat the original workload before claiming resolution. |
| Linux VF succeeds; Windows guest still fails | Separate Windows guest context/engine enumeration requirements from Linux VF code. A Linux-only `xe_lrc.c` patch is not a Windows guest implementation. |
| Host faults without any usable guest render node | Correlate host requester/IOVA ownership and first VF job; guest Mesa changes cannot repair a pre-probe kernel failure. |

The working baseline, failing baseline and patched result should each retain an identity manifest, full first-failure logs, selected debugfs snapshots, devcoredump if available, and per-engine IGT output. Report the result as “fix verified” only for the configurations and workloads that were actually exercised.

For provenance and the rationale behind these boundaries, see the [study notes](../../upstream-xe-notes.md), [official full-history refs](../../xe-full-advertised-refs.txt), and full Xe path-history index retained in the local study workspace. The MTL media-coherency backport is a separate phase and does not enable MTL/ARL SR-IOV by itself.
