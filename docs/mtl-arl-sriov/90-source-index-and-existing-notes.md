# Source Index And Existing Notes

## 1. Local Code Files Used As Primary Truth

### `i915`

- `drivers/gpu/drm/i915/README.sriov`
- `drivers/gpu/drm/i915/i915_sriov.c`
- `drivers/gpu/drm/i915/i915_utils.c`
- `drivers/gpu/drm/i915/gt/intel_gtt.c`
- `drivers/gpu/drm/i915/gt/intel_ggtt.c`
- `drivers/gpu/drm/i915/gt/iov/intel_iov.c`
- `drivers/gpu/drm/i915/gt/iov/intel_iov_query.c`
- `drivers/gpu/drm/i915/gt/iov/intel_iov_service.c`
- `drivers/gpu/drm/i915/gt/uc/intel_guc.c`
- `drivers/gpu/drm/i915/gt/uc/intel_guc_ads.c`
- `drivers/gpu/drm/i915/gt/uc/intel_guc_fwif.h`
- `drivers/gpu/drm/i915/display/intel_plane_initial.c`
- `drivers/gpu/drm/i915/display/intel_display_irq.c`
- `drivers/gpu/drm/i915/gt/uc/intel_gsc_fw.c`

### `xe`

- `drivers/gpu/drm/xe/xe_sriov.c`
- `drivers/gpu/drm/xe/xe_device.c`
- `drivers/gpu/drm/xe/xe_pci.c`
- `drivers/gpu/drm/xe/xe_pci_sriov.c`
- `drivers/gpu/drm/xe/xe_ggtt.c`
- `drivers/gpu/drm/xe/xe_guc_ct.c`
- `drivers/gpu/drm/xe/xe_gt_sriov_pf_service.c`
- `drivers/gpu/drm/xe/xe_gt_sriov_pf_migration.c`
- `drivers/gpu/drm/xe/xe_sriov_vf_ccs.c`
- `drivers/gpu/drm/xe/xe_guc.c`
- `drivers/gpu/drm/xe/xe_pat.c`
- `drivers/gpu/drm/xe/display/xe_display.c`

## 2. Commit / Mailing-List Anchors Used In The Narrative

### Old `i915` / MTL / ARL

- `drm/i915: (stolen) memory region related fixes`
  - `https://www.spinics.net/lists/intel-gfx/msg342210.html`
- `drm/i915/huc: check HuC and GuC version compatibility on MTL`
  - `https://www.spinics.net/lists/intel-gfx/msg330584.html`
- `drm/i915/pciids: separate ARL and MTL PCI IDs`
  - `https://www.spinics.net/lists/intel-gfx/msg355440.html`
- Intel LTS commits identified during the study:
  - `7f2edf7ea216980d5aaeaa0d16c892f6bd1f6334`
    - `drm/i915/gt: SR-IOV feature enablement`
  - `c031d1a2aaea6d9804a6a12af67b424642171836`
    - `drm/i915/iov: Expose early runtime registers for MTL`
  - `bcf6f14318c852a7319cf3ebeb0978432e314c0e`
    - `drm/i915/gt/iov: Add MTL WA for update VF GGTT via VF2PF relay`

### `xe` / MTL / ARL

- `[PULL] drm-xe-next` for 6.13
  - `https://www.spinics.net/lists/intel-gfx/msg358184.html`
  - useful because it groups:
    - `has_flat_ccs` cleanup/update,
    - display PM work,
    - ARL PCI-ID work,
    - SR-IOV work,
    - DSB coherency fix.
- `drm/xe/vf: Disable CSC support on VF`
  - `https://www.spinics.net/lists/stable/msg866934.html`
- `drm/xe: Fix DSB buffer coherency`
  - `https://www.spinics.net/lists/stable-commits/msg422166.html`
- review discussion about `has_flat_ccs` semantics:
  - `https://www.spinics.net/lists/intel-gfx/msg377804.html`
- stable mention of `drm/xe/pciids: separate ARL and MTL PCI IDs`
  - `https://www.spinics.net/lists/intel-gfx/msg361155.html`

## 3. Existing Local Notes That Were Folded In

The following older notes were not discarded. Their conclusions were merged
into the Markdown set above and they remain useful as raw working notes.

### `MTL_ARL_PLATFORM_ASSUMPTIONS_2026-03-28.txt`

Purpose:

- record the first pass over upstream i915 and local xe/i915 code with emphasis
  on platform assumptions rather than SR-IOV flow alone.

What it contributed here:

- the central framing that MTL is special in stolen-memory handling, ATS/cache
  suspicion, firmware pairing, and display sensitivity,
- the view that ARL is mostly "MTL-like but newer",
- the initial list of non-SR-IOV MTL/ARL commits that matter.

### `UPSTREAM_MTL_CLEANPATH_NOTES.txt`

Purpose:

- explain what the local `upstream-mtl-cleanpath` branch kept from earlier MTL
  SR-IOV experiments.

What it contributed here:

- the clean description of the current local `xe` MTL GGTT path,
- especially:
  - MTL SR-IOV enablement,
  - GSC/PXP lifecycle handling,
  - VF bootstrap and PF relay GGTT transport,
  - PF staged shadow apply,
  - direct GSM access for MTL PF.

## 4. What To Read If You Want The Fastest Path To Code Truth

If you only want the shortest path through the raw source:

1. `drivers/gpu/drm/i915/gt/iov/intel_iov.c`
2. `drivers/gpu/drm/i915/gt/iov/intel_iov_service.c`
3. `drivers/gpu/drm/i915/gt/intel_ggtt.c`
4. `drivers/gpu/drm/i915/i915_sriov.c`
5. `drivers/gpu/drm/xe/xe_sriov.c`
6. `drivers/gpu/drm/xe/xe_pci_sriov.c`
7. `drivers/gpu/drm/xe/xe_gt_sriov_pf_service.c`
8. `drivers/gpu/drm/xe/xe_ggtt.c`
9. `drivers/gpu/drm/xe/xe_gt_sriov_pf_migration.c`
10. `drivers/gpu/drm/xe/xe_sriov_vf_ccs.c`

That file order recreates the comparison in the least roundabout way.
