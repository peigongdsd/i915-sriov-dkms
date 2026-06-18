# Xe MTL SR-IOV Trace Plan

## Purpose

This note records the next useful debug instrumentation for the Meteor Lake
`xe` SR-IOV Windows glitch issue. It is intended to avoid re-studying the same
branch history in future sessions.

The working model is not that `xe` cannot boot or render on MTL SR-IOV. Windows
boots and graphics mostly work. The remaining issue is small stable corruption
in modern Windows composition or shared-present paths, while the same platform
works through the repo's `i915` SR-IOV path.

The most useful traces should therefore expose the contract seen by the Windows
VF and the final memory/cache policy applied to VF-visible mappings. They should
not start by re-testing GGTT transport variants unless a trace shows hard GGTT
failure.

## Source Review Status

The full driver trees are large:

- `drivers/gpu/drm/i915`: about 853 source/control files and 393k lines.
- `drivers/gpu/drm/xe`: about 496 source/control files and 127k lines.

This pass focused on the source paths that can affect the Windows VF contract:

- `drivers/gpu/drm/i915/gt/iov/intel_iov_provisioning.c`
- `drivers/gpu/drm/i915/gt/intel_ggtt.c`
- `drivers/gpu/drm/i915/gem/i915_gem_object_types.h`
- `drivers/gpu/drm/i915/gem/i915_gem_domain.c`
- `drivers/gpu/drm/i915/gem/i915_gem_clflush.c`
- `drivers/gpu/drm/i915/gt/intel_mocs.c`
- `drivers/gpu/drm/i915/display/intel_fb_pin.c`
- `drivers/gpu/drm/xe/xe_gt_sriov_pf_config.c`
- `drivers/gpu/drm/xe/xe_gt_sriov_pf_service.c`
- `drivers/gpu/drm/xe/xe_gt_sriov_pf_debugfs.c`
- `drivers/gpu/drm/xe/xe_guc_ct.c`
- `drivers/gpu/drm/xe/xe_ggtt.c`
- `drivers/gpu/drm/xe/xe_vm.c`
- `drivers/gpu/drm/xe/xe_pat.c`
- `drivers/gpu/drm/xe/xe_mocs.c`
- `drivers/gpu/drm/xe/xe_tlb_inval.c`
- `drivers/gpu/drm/xe/display/xe_fb_pin.c`

A literal every-line review of both trees is not complete in this note. The
remaining broad review should be done by subsystem, starting with the files
above and then expanding through their callers.

## Branch History Already Accounted For

The visible fork branches already explored these debug families:

- MTL SR-IOV enablement, GSC/PXP toggles, GSC forcewake, and FLR tracing.
- VF/PF MMIO relay, runtime register exposure, runtime register tracing, and
  the i915-like MTL runtime register mirror.
- GGTT bootstrap versus relay transport, literal versus coalesced PTE updates,
  direct versus staged PF apply, direct GSM access, CPU versus bind-engine
  apply, GuC/direct invalidation, and shadow/readback verification.
- Scanout alignment, scanout PAT tracing, sysmem scanout flush, and pagetable
  WC visibility.
- Import of the notable i915-like MTL RCS/CCS GuC workaround path.
- VF CCS metadata and migration logging, which likely does not drive MTL because
  MTL does not advertise xe flat CCS for this path.

Treat those as background experiments. Do not start future work by repeating
them unless a new trace shows a direct fault in the same area.

## Important i915-vs-xe Differences Seen

### i915 Object Coherency Model

`i915` tracks a global object cache/coherency state:

- `obj->pat_index`
- `obj->pat_set_by_user`
- `obj->cache_coherent`
- `obj->cache_dirty`
- read/write domains

Relevant comments in `i915_gem_object_types.h` are important. `I915_CACHE_NONE`
is treated as likely scanout-like on shared LLC systems, and the driver flushes
or keeps `cache_dirty` conservative to make display reads coherent. `I915_CACHE_WT`
is preferred for scanout when available because it keeps display coherent with
GPU writes without the same late flush cost.

`i915_gem_clflush_object()` and `i915_gem_object_prepare_{read,write}()` then
use this object state to decide whether CPU cache flushing is needed.

### xe PAT/PTE Model

`xe` is more per-bind and per-PTE:

- VM bind receives a `pat_index`.
- `xe_vm_bind_ioctl_check_args()` validates the PAT index and derives coherency
  and compression from `xe_pat`.
- `xe_vm_bind_ioctl_validate_bo()` rejects unsafe combinations such as WB CPU
  caching with no coherency, imported dma-buf with compression, and no-compress
  BOs mapped with compression.
- PTEs encode PAT bits in `xelp_pte_encode_*()`.

For a Windows VF, normal PF-side Linux `xe_vm_bind_ioctl()` is not the main
observable path. The Windows KMD runs inside the VF, and the PF mainly sees
VF GGTT update requests and GuC/VF configuration. Therefore PF-side tracing
must focus on relay/MMIO GGTT update messages and final KLV configuration.

### VF GGTT Update Visibility

The current `xe` MTL path processes VF GGTT writes through:

- `pf_process_update_ggtt_msg()` in `xe_gt_sriov_pf_service.c`
- `mmio_relay_reply_update_ggtt()` in `xe_guc_ct.c`
- `xe_ggtt_update_vf_ptes()` in `xe_ggtt.c`

The current code already tracks a PF shadow for MTL VF GGTT contents through
`vf_shadow_ptes`. This is the right place to add low-volume classification
instead of another raw packet dump.

### VF Config KLV Shape

`i915` and `xe` both push GGTT, context, doorbell, scheduling, timeout, and
threshold KLVs, but the code shape is not identical.

`i915`:

- `pf_push_config_ggtt()` pushes GGTT size and start.
- On media GT it explicitly calls `__pf_push_config_ggtt(&media_gt->iov, ...)`.
- `pf_push_configs()` encodes full config from `intel_iov_config`.

`xe`:

- `pf_push_full_vf_config()` encodes config from `xe_gt_sriov_config`.
- Media GT full config asserts it has no own GGTT region and appends the primary
  GT's GGTT KLVs.
- PF config fakes a full GGTT range except WOPCM.
- Some begin-context and begin-doorbell tags are conditional on nonzero counts.

This is not proof of a bug, but the final KLV stream should be dumped under
working `i915` and failing `xe` for the same VF so this class can be eliminated.

### Existing xe Config Debugfs Is Useful But Incomplete

`drivers/gpu/drm/xe/xe_gt_sriov_pf_debugfs.c` already exposes a debug-only
`config_blob` file under:

- `/sys/kernel/debug/dri/<BDF>/sriov/vf<N>/tile<M>/gt<K>/config_blob`

That file calls `xe_gt_sriov_pf_config_save()` and serializes the currently
provisioned VF config. This is useful as a first capture point.

However, it is not guaranteed to be byte-for-byte identical to what is pushed
to GuC by `pf_push_full_vf_config()`:

- `config_save()` calls `encode_config(..., details=false)`.
- The push path calls `encode_config(..., details=true)`.
- The media-GT push path appends the primary-GT GGTT KLVs.
- The PF self-config path fakes a full GGTT range except WOPCM.

Therefore a future trace patch should not duplicate `config_blob`, but it still
needs a push-path dump or "last pushed KLVs" buffer if exact i915-versus-xe
GuC payload comparison is the goal.

### MTL GGTT PTE Bit Facts

For the xe GGTT path:

- `XE_GGTT_PTE_ADDR_MASK` / `XE_PTE_ADDR_MASK` is bits 51:12.
- `GGTT_PTE_VFID` is bits 11:2.
- `XE_PAGE_PRESENT` is bit 0.
- `XE_GGTT_PTE_DM` is bit 1 for device memory/stolen device memory.
- `XELPG_GGTT_PTE_PAT0` is bit 52.
- `XELPG_GGTT_PTE_PAT1` is bit 53.

`xe_ggtt_prepare_vf_pte()` replaces VFID bits and forces PRESENT, while
`vf_shadow_ptes` intentionally stores entries without VFID bits. Any classifier
should report both the raw shadow flags and the final prepared flags.

For MTL/xelpg, GGTT PAT is only two bits in this path. The immediate useful
classification is therefore:

- address bits versus non-address bits
- present or clear
- DM bit
- PAT index from bits 53:52
- VFID after PF preparation
- whether an update changes only address, only flags, both, or clears

## Trace Hooks To Add First

### 1. Final VF Config KLV Dump

Add a debugfs or module-param-gated dump of the exact KLV dwords pushed to GuC.

Best `xe` hook:

- `pf_push_full_vf_config()` in `drivers/gpu/drm/xe/xe_gt_sriov_pf_config.c`

Capture:

- GT type: primary or media
- VF ID
- full raw KLV dwords
- decoded key, length, values
- whether config was a reset or refresh path
- GGTT start/size
- begin context and number of contexts
- begin doorbell and number of doorbells
- exec quantum and preempt timeout
- all threshold KLVs
- LMEM size if present

Why:

- This is cheap and directly comparable against working `i915`.
- If the streams match, stop worrying about VF provisioning shape.
- If they differ, make one minimal xe change to match i915 and test.

Implementation note:

- First read the existing `config_blob` debugfs file for each VF/GT.
- If more exact data is needed, instrument `pf_push_full_vf_config()` after the
  media-GT and PF self-config adjustments, immediately before
  `pf_push_vf_buf_klvs()`.
- Prefer a small "last pushed config" buffer in PF debug state or a ratelimited
  DRM debug dump, not a second persistent provisioning ABI.

### 2. VF GGTT PTE Classifier

Add a low-volume classifier around both relay and MMIO update paths.

Best `xe` hooks:

- `pf_process_update_ggtt_msg()` in `xe_gt_sriov_pf_service.c`
- `mmio_relay_reply_update_ggtt()` in `xe_guc_ct.c`
- `xe_ggtt_update_vf_ptes()` in `xe_ggtt.c`

Capture aggregated counts per VF and per short time window:

- update source: MMIO bootstrap or GuC relay
- mode: duplicate, replicate, duplicate-last, replicate-last
- PTE count
- VF GGTT offset range
- final encoded flag bits excluding address
- present bit set or clear
- VFID bits after PF preparation
- whether address sequence is contiguous
- whether the update changes only flags, only address, both, or clears
- mismatch between requested/shadow/readback if readback is enabled
- error return from update path

Do not log every PTE by default. Add an optional one-shot range filter:

- `vfid`
- GGTT offset start/end
- max number of raw PTE lines

Why:

- The visible bug is stable corruption, not obvious transport failure.
- A classifier can show whether the repro triggers unusual flag classes or
  high churn in a narrow GGTT range without flooding dmesg.

Implementation note:

- Keep raw decode helpers in `xe_ggtt.c`, because `struct xe_ggtt_node` is
  intentionally opaque outside that file.
- Export small helpers through `xe_ggtt.h` only for snapshot/classifier output,
  not direct access to `vf_shadow_ptes`.
- Decode the PTE using the bit facts above; do not infer cache policy from a
  guessed mask.
- The call sites are only:
  - `pf_process_update_ggtt_msg()`
  - `mmio_relay_reply_update_ggtt()`
  - `xe_ggtt_update_vf_ptes()`

### 3. VF GGTT Snapshot Trigger

Add a manual debugfs trigger to snapshot a VF's shadow GGTT range.

Best `xe` state:

- `struct xe_ggtt_node::vf_shadow_ptes`

Capture:

- raw shadow PTEs for a requested VF GGTT offset range
- decoded address and flag bits
- optional live GSM readback for the same range
- mismatch count between shadow and live readback

Why:

- Windows-side repro can be run, then the user can snapshot just after the
  glitch appears.
- This avoids continuous noisy tracing.

Implementation note:

- Add a helper in `xe_ggtt.c`, for example a printer-style function that dumps
  a bounded `pte_offset/count` range from the node.
- Wire debugfs from the VF GT directory, near existing VF config/control files
  in `xe_gt_sriov_pf_debugfs.c`.
- The debugfs file should accept only a bounded range and cap output. A full VF
  GGTT dump can be huge and is not useful for the Windows composition repro.

### 4. Late Relay/MMIO Error Trace

Keep this narrow and error-only.

Best `xe` hooks:

- `xe_gt_sriov_pf_service_process_request()`
- `pf_process_runtime_query_msg()`
- MMIO relay service in `xe_guc_ct.c`

Capture only:

- unsupported relay action/opcode
- unsupported runtime register offset
- malformed message
- timeout
- failed reply
- GuC CT send failure

Why:

- Runtime register experiments already weakened this class.
- A quiet error trace during the repro should demote relay further.

### 5. Host xe PAT/MOCS/Cache State Dump

Add a static dump at PF/VF enable time and optionally before/after repro.

Best `xe` hooks:

- existing `xe_pat_dump_sw_config()`
- existing MOCS dump helpers in `xe_mocs.c`
- `xe_pat_init_early()`
- `xe_mocs_init()` or nearby init path

Capture:

- `xe->pat.idx[XE_CACHE_NONE]`
- `xe->pat.idx[XE_CACHE_WT]`
- `xe->pat.idx[XE_CACHE_WB]`
- compression PAT indices if valid
- full programmed PAT table for primary and media GT
- MOCS `uc_index`, `wb_index`, unused-entry policy
- MOCS table values for primary and media GT

Why:

- This is needed to compare the xe policy environment with i915.
- It will not by itself prove guest surface policy, but it anchors the hardware
  tables used by the encoded PTEs and command defaults.

### 6. Conservative Diagnostic Switch

After the above traces are in place, add a blunt debug switch that makes the xe
VF-presented path safer.

Candidate behavior:

- For MTL SR-IOV PF/VF GGTT relay updates, optionally sanitize risky PTE flag
  combinations to a conservative PAT/cache class if those bits are encoded in
  the observed PTEs.
- Disable or avoid compression-related PAT choices for VF-visible mappings if
  the traced PTE format proves they are present.
- Force conservative host BO/PTE policy for PF-created shared/GGTT objects
  used by VF services.

Important:

- Do not guess the mask. First decode exactly which bits the VF PTEs carry on
  MTL.
- The diagnostic switch is judged only by whether artifact shape changes.
- It is not a performance or final-design patch.

## Suggested Debug Workflow

1. Boot with the KLV dump and static PAT/MOCS dump enabled.
2. Save logs from working `i915` and failing `xe` for the same VF provisioning.
3. Run the Windows repro with only error-level relay/MMIO logging enabled.
4. If no relay errors appear, snapshot the VF GGTT shadow range around active
   update hot spots.
5. Enable the GGTT PTE classifier during the exact repro and record aggregate
   flag classes and churn ranges.
6. Only after the trace identifies risky PTE/cache/compression classes, add the
   conservative diagnostic switch.

## What Not To Repeat First

Do not start by repeating these branch families unless a new trace points there:

- MMIO bootstrap versus relay transport.
- Literal versus coalesced PTE updates.
- PF shadow versus direct apply.
- Synchronous versus deferred PF apply.
- CPU apply versus bind-engine apply.
- Direct GSM/DSMBASE access.
- Immediate/deferred/GuC-backed GGTT invalidation.
- One isolated runtime register.
- One isolated MTL RCS/CCS GuC workaround.

Those experiments were already explored in the fork history and did not appear
to change the Windows glitch shape.

## Current Best Next Patch

The first implementation patch should be trace-only:

- Add a debugfs-gated VF config KLV dump in `xe_gt_sriov_pf_config.c`.
- Add a debugfs-gated VF GGTT PTE classifier and snapshot interface around
  `xe_ggtt_update_vf_ptes()`.
- Add narrow relay/MMIO error logging during the exact repro.

Do not add the conservative policy switch until the trace output shows which
PTE/cache/compression classes are active during the glitch.
