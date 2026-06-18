# Xe MTL SR-IOV Trace Results - 2026-06-18

## Context

This note records the first live boot using the `upstream-mtl-pf-debug-trace`
branch after NixOS was confirmed to pin:

- `github:peigongdsd/i915-sriov-dkms/upstream-mtl-pf-debug-trace`
- commit `ce2699abf786cec2981c28fc5102557cca0d350d`
- subject `xe/sriov: add bounded PF debug tracing`

The live module was loaded from the Nix store as an `xe-sriov` module, while
the local working tree was initially on `upstream-mtl-cleanpath`. The local
checkout is therefore not proof of the live booted source.

The VM was booted and the Windows guest was operated during collection. Polling
kernel logs made the desktop laggy, so future root/debugfs captures should be
single batched `run0 bash -lc '...'` commands that write bounded snapshots.

## Live Device State

The host was using `xe` for the PF:

- PF `0000:00:02.0` bound to `xe`
- VF `0000:00:02.1` bound to `vfio-pci`
- `i915` loaded but not bound to the GPU

SR-IOV debugfs reported:

- mode: SR-IOV PF
- total supported VFs: 7
- enabled VFs: 1
- VF1 GGTT quota: 2.00 GiB
- VF1 GGTT provisioned range: `0x7ee00000-0xfedfffff`

## Captured Files

Uncommitted local logs are under `trace-logs/`.

Important files:

- `xe-vm-boot-window-20260618-172823.log`
- `xe-dmesg-warnerr-20260618-173630.log`
- `xe-tracefs-no-reg-repro-20260618-173520.log`
- `xe-debugfs-pat-mocs-20260618-173317.log`
- `xe-debugfs-pat-mocs-resample-20260618-173516.log`
- `xe-live-vf1-gt0-trace_service.log`
- `xe-live-vf1-gt1-trace_service.log`
- `xe-live-vf1-gt0-trace_ggtt.log`
- `xe-live-vf1-gt1-trace_ggtt.log`

Do not commit the raw `trace-logs/` directory unless explicitly requested.

## Debugfs Trace Interface Status

The debug branch did expose the expected files under:

- `/sys/kernel/debug/dri/0000:00:02.0/sriov/vf1/tile0/gt0/`
- `/sys/kernel/debug/dri/0000:00:02.0/sriov/vf1/tile0/gt1/`

Important files:

- `trace_config`
- `trace_service`
- `trace_ggtt`
- `trace_ggtt_flags`
- `trace_ggtt_log_budget`
- `trace_ggtt_raw_budget`
- `trace_ggtt_snapshot_start`
- `trace_ggtt_snapshot_count`
- `trace_service_flags`
- `trace_service_log_budget`

The first file-list capture missed these per-GT trace files because it did not
inspect the correct depth/paths. The branch was not missing from the booted
system.

## VF1 Service Counters

VF1 GT0 `trace_service`:

```text
requests: 1630
errors: 0
handshake: 3
runtime: 4
ggtt: 1623
unknown: 0
mmio_requests: 4438
mmio_errors: 0
mmio_handshake: 0
mmio_runtime: 0
mmio_ggtt: 4438
mmio_unknown: 0
last_action: 0x102
last_opcode: 0x2
last_ret: 0
```

VF1 GT1 `trace_service`:

```text
requests: 6
errors: 0
handshake: 2
runtime: 4
ggtt: 0
unknown: 0
mmio_requests: 0
mmio_errors: 0
```

Interpretation:

- The exact repro window did not show late relay/service errors.
- VF1 GGTT activity is concentrated on GT0.
- GT1 only handled handshake/runtime in this capture.
- The repeated `xe_guc_relay: callbacks suppressed` lines are volume noise, not
  evidence of failed relay processing by themselves.

## VF1 Config Trace Gap

VF1 `trace_config` read as zero for both GT0 and GT1 in this boot, while PF
`trace_config` showed one pushed self-config KLV blob. Source review explains
why this is possible:

- The original debug hook only recorded `pf_push_full_vf_config()`.
- Normal provisioning also pushes incremental KLVs through
  `pf_push_vf_buf_klvs()`.
- Those incremental pushes include GGTT, contexts, doorbells, scheduling, and
  threshold updates used while provisioning a VF.

The debug branch has been updated after this capture to record config KLVs at
the common `pf_push_vf_buf_klvs()` helper. On the next boot, VF1
`trace_config` should show incremental provisioning pushes instead of staying
zero unless a full config push occurs.

The branch has also been updated to keep a compact last-64 VF GGTT update
history in `trace_ggtt`. This avoids live printk/trace polling while preserving
the most recent range, source, mode, PAT mask, flag mask, and first/last PTE
summary for post-repro inspection.

## VF1 GGTT Counters

VF1 GT0 `trace_ggtt`:

```text
updates: 6061
ptes: 555062
errors: 0
source_relay: 1623
source_mmio: 4438
mode_duplicate: 6043
mode_replicate: 3
mode_duplicate-last: 15
mode_replicate-last: 0
pat0: 2048
pat1: 0
pat2: 552679
pat3: 335
raw_present: 555062
raw_clear: 0
final_present: 555062
dm: 0
addr_only: 28635
flags_only: 0
addr_and_flags: 2139
no_change: 0
clears: 0
contiguous: 2342
non_contiguous: 3719
last_source: mmio
last_mode: duplicate
last_num_copies: 23
last_count: 1
last_n_ptes: 24
last_offset: 10481
last_end: 10505
last_ret: 24
last_pat_mask: 0x4
last_raw_flags_mask: 0x20000000000001
last_final_flags_mask: 0x20000000000005
```

VF1 GT1 `trace_ggtt`:

```text
updates: 0
ptes: 0
errors: 0
shadow_snapshot:
error: -ENOENT
```

The sampled GT0 shadow snapshot showed live GGTT PTEs matching the prepared
final PTEs for entries 0..31. No sampled mismatch was present.

Interpretation:

- This capture weakens dropped GGTT update, bad VFID preparation, and immediate
  shadow/live mismatch theories for the sampled range.
- It does not prove every affected Windows surface has correct attributes.
- The classifier currently summarizes PAT and flags globally; it does not map a
  specific corrupt on-screen surface to a specific PTE range.

## PAT/MOCS Findings

MTL `xe_pat_init_early()` maps:

- `XE_CACHE_NONE` -> PAT index 2
- `XE_CACHE_WT` -> PAT index 1
- `XE_CACHE_WB` -> PAT index 3

The live `pat_sw_config` matched this mapping on both GT0 and GT1.

VF1 GT0 GGTT updates were overwhelmingly PAT2:

- PAT2: 552679 PTEs
- PAT0: 2048 PTEs
- PAT3: 335 PTEs
- PAT1: 0 PTEs

On MTL, PAT2 means `XE_CACHE_NONE` in this driver. Therefore the VF GGTT stream
seen by the PF is mostly uncached, not write-back. A small number of PAT3
write-back entries are present and should be examined in a focused capture if
the corrupt surface can be correlated to a GGTT range.

MOCS debugfs showed an asymmetry:

- GT0 LNCFCMOCS entries were programmed with nonzero values.
- GT1 LNCFCMOCS entries read as all zeros.
- A later resample showed the same result.

This may be normal for the media GT path, but because the visual bug is in
modern composition/video/present paths, it should be compared against the
working i915 environment or against expected xe MTL media-GT programming before
being dismissed.

## Tracefs Correlation

`xe-tracefs-no-reg-repro-20260618-173520.log` event counts:

```text
1965 xe_guc_ctb_h2g
1093 xe_tlb_inval_fence_recv
1014 xe_tlb_inval_fence_signal
1014 xe_tlb_inval_fence_send
1014 xe_guc_ctb_g2h
951 xe_exec_queue_submit
```

H2G action counts:

```text
951 gt0: 0x1000
507 gt0: 0x7000
507 gt1: 0x7000
```

G2H action counts:

```text
507 gt0: 0x7001
507 gt1: 0x7001
```

TLB invalidation accounting:

```text
send: 1014
signal: 1014
recv: 1093
```

Interpretation:

- Exec submissions are normal GT0 activity.
- TLB invalidations are paired across GT0/GT1 and every send was signaled.
- The extra recv count likely reflects pre-existing or overlapping trace state,
  not an unsignaled send in this capture.
- No tracefs event name indicating timeout, GT reset, scheduler timeout, page
  fault, CAT error, or wedged state was found in the repro capture.

## Boot-Time Warnings

During boot, before the VF was bound to `vfio-pci`, the VF-side probe emitted:

- `Did not find MCR register 0xb158 in any MCR steering table`
- WARN in `xe_gt_mcr_get_nonterminated_steering`
- repeated `GuC mmio request 0xf025005: failure 0xa hint 0x0`
- `VF explicit clear failed (-ENXIO), falling back to raw writes`

These messages came from `xe 0000:00:02.1`, not the PF. Since the configured
udev flow later binds the VF to `vfio-pci`, this may be a host-side autoprobe
side effect rather than the Windows guest bug. It is still worth eliminating by
ensuring VF autoprobe is disabled before enabling VFs, or by comparing whether
i915 ever probes the VF in the same way before vfio binding.

## What This Capture Weakens

The following are weaker after this boot:

- Late VF2PF relay failure during the exact repro.
- Unsupported relay opcode or unsupported MMIO opcode during the exact repro.
- GGTT update failure or ERANGE/EINVAL path during the repro.
- Raw VF GGTT PTE clear/drop during the repro.
- Immediate sampled shadow/live GGTT mismatch.
- GT reset, scheduler timeout, or wedged-state explanation.

## What Remains Suspicious

The strongest remaining areas are still policy/contract-level:

- Windows guest surface cache/PAT/MOCS/compression contract.
- Whether the small PAT3 population maps to present/composition surfaces.
- Whether GT1/media MOCS state is expected to have zero LNCFCMOCS on this boot.
- Whether Windows chooses different DWM/DComp/DirectComposition capabilities
  under xe than under the working i915 PF.
- Whether the final GuC VF config KLV stream differs from i915 in a subtle but
  behaviorally relevant way.

## Second Boot With Config Push Hook

After rebuilding and booting commit `2c46b49ffaa63db22654dd6067052ecaf05194c4`,
the VM was started and a bounded snapshot was collected at:

- `trace-logs/xe-vf1-postboot-20260618-182246/`

Confirmed live state:

- local and booted branch: `upstream-mtl-pf-debug-trace`
- local and booted commit: `2c46b49 xe/sriov: extend PF debug trace coverage`
- PF `0000:00:02.0` bound to `xe`
- VF `0000:00:02.1` bound to `vfio-pci`

VF1 GT0 service counters:

```text
requests: 710
errors: 0
ggtt: 703
mmio_requests: 4066
mmio_errors: 0
mmio_ggtt: 4066
last_ret: 1
```

VF1 GT1 service counters:

```text
requests: 6
errors: 0
ggtt: 0
mmio_requests: 0
```

VF1 GT0 GGTT counters:

```text
updates: 4769
ptes: 535821
errors: 0
source_relay: 703
source_mmio: 4066
pat0: 2048
pat1: 0
pat2: 533438
pat3: 335
history_seq: 4769
```

The new config push hook worked: `trace_config` was no longer zero. Both GT0
and GT1 showed:

```text
pushes: 3
errors: 0
last_num_klvs: 2
{ key 0x8a0a : 32b value 0 } # begin_db_id
{ key 0x0006 : 32b value 128 } # num_doorbells
```

This exposed a limitation in commit `2c46b49`: `trace_config` retained only the
last KLV blob, so the earlier GGTT/context/scheduler provisioning pushes were
overwritten by the final doorbell push. The branch was therefore extended again
after this boot to keep a bounded config-push history ring and per-PAT GGTT
history rings. On the next boot, `trace_config` should preserve all three
provisioning pushes and `trace_ggtt` should preserve rare PAT0/PAT3 update
ranges even if normal PAT2 churn overwrites the generic last-64 history.

The warning/error pattern remained boot-time VF autoprobe noise:

- VF-side MCR warning from `xe 0000:00:02.1` during host VF probe.
- VF-side `GuC mmio request 0xf025005: failure 0xa` and explicit clear
  fallback before the VF was rebound to `vfio-pci`.
- No runtime PF service/GGTT errors were captured while the Windows VM was
  running.

## NixOS VF Guest Harness Freeze

After the Windows VM was stopped, a first NixOS VF guest harness was built to
test the Linux guest xe VF path with the same host-pinned versions:

- host kernel: `7.0.12`
- host module package: `xe-sriov-module-2026.05.06-7.0.12`
- `nixpkgs`: `134c6973427a26f0b8924e7bb1a2ce5a9249d903`
- `i915-sriov`: `2c46b49ffaa63db22654dd6067052ecaf05194c4`

The host hard-froze during the first launch attempt and had to be rebooted. The
previous-boot journal shows the launch stopped at:

```text
Started NixOS xe SR-IOV VF guest.
Disk image does not exist, creating the virtualisation disk image...
Virtualisation disk image created.
Creating Nix store image...
```

There was no subsequent `qemu-system-*` line, no VFIO open/reset line at the
launch timestamp, and no `vfio-pci 0000:00:02.1` FLR after the VM launcher
started. The last recorded launcher phase was the generated NixOS VM script's
just-in-time `tar | mkfs.erofs` Nix store image creation, before QEMU reached
VF passthrough.

Interpretation:

- This reboot is not evidence that the Linux xe VF guest path wedged the GPU.
- The freeze happened before VFIO attach, so it is a host VM-launch/storage
  failure around the generated EROFS store image path.
- The harness was changed to use a host Nix store 9p mount
  (`mountHostNixStore = true`, `useNixStoreImage = false`) and to provide a
  no-VF smoke-test VM config before retrying VF passthrough.
- The regenerated no-VF and VF launchers were inspected after rebuild: neither
  contains `Creating Nix store image`, `mkfs.erofs`, or `store.img`; the no-VF
  config has no `host=0000:00:02.1`, while the VF config keeps that VFIO device.

## Next Low-Noise Captures

Batch root commands with one `run0 bash -lc '...'` invocation. Avoid live
polling unless absolutely necessary.

Recommended next debugfs batch:

```sh
base=/sys/kernel/debug/dri/0000:00:02.0/sriov/vf1/tile0
out=trace-logs/xe-vf1-debugfs-$(date +%Y%m%d-%H%M%S)
mkdir -p "$out"
for gt in gt0 gt1; do
  dir="$base/$gt"
  for f in trace_service trace_ggtt trace_config; do
    cat "$dir/$f" > "$out/$gt-$f.txt"
  done
done
```

Recommended focused GGTT snapshot after a visible artifact:

```sh
base=/sys/kernel/debug/dri/0000:00:02.0/sriov/vf1/tile0/gt0
echo 0 > "$base/trace_ggtt_snapshot_start"
echo 256 > "$base/trace_ggtt_snapshot_count"
cat "$base/trace_ggtt" > "trace-logs/xe-vf1-gt0-trace_ggtt-window.txt"
```

If a suspicious GGTT range is identified, set `trace_ggtt_filter_start` and
`trace_ggtt_filter_count`, then enable small log budgets only:

```sh
echo 0x7 > "$base/trace_ggtt_flags"
echo 32 > "$base/trace_ggtt_log_budget"
echo 16 > "$base/trace_ggtt_raw_budget"
```

Turn budgets back to zero after the repro.

## Next Code Work

Useful next instrumentation should not be a broad printk stream. Add bounded
structured debugfs state instead:

- The branch now has a generic last-64 update history plus per-PAT history
  rings in `trace_ggtt`.
- Optional range-filtered shadow/live snapshot beyond the first 32 PTEs.
- The branch now has a compact config-push history ring for each VF and GT,
  recorded in the actual push path, not just `config_blob`.
- A MOCS/PAT compare helper that prints GT0 and GT1 together and flags all-zero
  LNCFCMOCS on media GT.

Useful next experiment:

- Build a diagnostic branch that forces a conservative VF-visible surface
  policy, starting with removing or remapping the small write-back/PAT3 GGTT
  population to the safer uncached path, then testing whether the artifact
  shape changes.
