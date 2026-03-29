# `xe` Codeflow For SR-IOV, With MTL / ARL Treatment Called Out

## 1. Where `xe` Puts The Pieces

Unlike old `i915`, `xe` does not have a single `README.sriov` file that
declares the topology. The pieces are distributed across:

- `drivers/gpu/drm/xe/xe_sriov.c`
- `drivers/gpu/drm/xe/xe_sriov_pf*.c`
- `drivers/gpu/drm/xe/xe_sriov_vf*.c`
- `drivers/gpu/drm/xe/xe_gt_sriov_pf_service.c`
- `drivers/gpu/drm/xe/xe_pci_sriov.c`
- `drivers/gpu/drm/xe/xe_ggtt.c`
- `drivers/gpu/drm/xe/xe_gt_sriov_pf_migration.c`
- `drivers/gpu/drm/xe/xe_sriov_vf_ccs.c`

That distribution is a first difference from `i915`:

- `xe` organizes SR-IOV around device/GT services and PF/VF split helpers,
  not around one central "IOV" directory only.

## 2. Early Mode Detection And Device Identity

### 2.1 Early SR-IOV Detection

Key file:

- `drivers/gpu/drm/xe/xe_sriov.c`

Key function:

- `xe_sriov_probe_early()`

The logic is:

- if the platform descriptor says `has_sriov`,
  - check VF status via `VF_CAP_REG`,
  - otherwise check PF readiness,
- else, if PCI capability exists but platform support is not enabled,
  zero the available VF count to stop accidental exposure.

This is more defensive than "PCI says SR-IOV, therefore enable it".

### 2.2 MTL / ARL Identity In `xe`

Current local `xe_pci.c` still shows:

- `INTEL_ARL_IDS(..., &mtl_desc)`
- `INTEL_MTL_IDS(..., &mtl_desc)`

So in this tree:

- ARL and MTL are still described by the same base descriptor,
- with later upstream work having already started to separate the PCI-ID macros.

That matches the Intel mailing-list history:

- first: ARL lands as MTL-like,
- later: PCI-ID separation is introduced as a cleanup/correctness step.

## 3. Early Initialization In `xe`

### 3.1 `xe_sriov_init()`

The core split is:

- PF:
  - `xe_sriov_pf_init_early()`
- VF:
  - `xe_sriov_vf_init_early()`
- then:
  - allocate a dedicated SR-IOV workqueue

This is structurally simpler than `i915`'s early `intel_iov_*` fan-out.

### 3.2 `xe_sriov_init_late()`

Late init dispatches again by role:

- PF:
  - `xe_sriov_pf_init_late()`
- VF:
  - `xe_sriov_vf_init_late()`

So `xe` also uses early/late staging, but with PF/VF service modules rather
than one explicit `intel_iov_*` umbrella.

## 4. VF Feature Masking In `xe`

One of `xe`'s strongest SR-IOV design choices is that VF capability shaping is
performed centrally in device-info setup.

Key file:

- `drivers/gpu/drm/xe/xe_device.c`

Key function:

- `vf_update_device_info()`

Current VF rules include:

- `probe_display = 0`
- `has_heci_cscfi = 0`
- `has_heci_gscfi = 0`
- `has_late_bind = 0`
- `skip_guc_pc = 1`
- `skip_pcode = 1`

This is conceptually important:

- `xe` is willing to change the device personality for VFs rather than trying
  to make every PF feature virtualizable.

That decision became stricter over time. An explicit example is:

- `drm/xe/vf: Disable CSC support on VF`
- message:
  `https://www.spinics.net/lists/stable/msg866934.html`

This is the `xe` equivalent of saying:

- if the VF cannot safely access it, stop advertising it.

## 5. PF VF-Enable Flow In `xe`

### 5.1 PF Controls VF Lifecycle Through PCI Helpers

Key file:

- `drivers/gpu/drm/xe/xe_pci_sriov.c`

Key function:

- `pf_enable_vfs()`

What it does:

1. wait for PF readiness,
2. arm a guard to stop conflicting operations,
3. hold runtime PM so PF remains in D0 while VFs exist,
4. on MTL:
   - disable GSC/PXP first,
5. provision VF resources,
6. call `pci_enable_sriov()`,
7. link VF devices to PF for resume ordering,
8. enable engine activity stats.

This is one of the clearest MTL-specific `xe` behaviors:

- MTL PF is not allowed to keep GSC/PXP running unchanged across VF enable.

### 5.2 PF Disable Flow Mirrors The Same Concern

When disabling VFs:

- reset/unprovision VFs,
- on MTL:
  - re-enable GSC/PXP,
- drop the runtime PM reference.

So the MTL-specific GSC/PXP treatment is a lifecycle rule, not a one-off init
hack.

## 6. Runtime Register Service In `xe`

Key file:

- `drivers/gpu/drm/xe/xe_gt_sriov_pf_service.c`

This is the closest `xe` equivalent to `i915`'s `intel_iov_service.c`.

### 6.1 Runtime Register Tables

`xe` defines several runtime register arrays:

- `tgl_runtime_regs`
- `ats_m_runtime_regs`
- `pvc_runtime_regs`
- `ver_1270_runtime_regs`
- `ver_2000_runtime_regs`
- `ver_3000_runtime_regs`
- `ver_35_runtime_regs`

For MTL-class graphics version `12.70`, the local tree uses:

- `ver_1270_runtime_regs`

That list is notably smaller than `i915`'s MTL runtime set.

This is one of the most concrete i915-vs-xe differences:

- `i915` MTL runtime exposure is hand-expanded for MTL,
- `xe` uses a generic `ver_1270` bucket with fewer registers.

### 6.2 What The PF Service Actually Does

The PF service:

- chooses the runtime register set based on graphics version,
- allocates storage,
- reads the registers on PF,
- serves that snapshot to VF paths that need runtime state.

So the PF still acts as the runtime-state authority, but the exposed contract
is shaped differently than in `i915`.

## 7. GGTT Update Transport In `xe`

This is the most important active SR-IOV path for MTL in this tree.

### 7.1 VF Bootstrap And Relay

Key files:

- `drivers/gpu/drm/xe/xe_ggtt.c`
- `drivers/gpu/drm/xe/xe_guc_ct.c`
- `drivers/gpu/drm/xe/xe_gt_sriov_pf_service.c`

Current local one-shot markers show the intended split:

- VF bootstrap path:
  - `xe: MTL SR-IOV GGTT path: VF MMIO bootstrap GGTT sender active before GuC CT submission`
- PF bootstrap path:
  - `xe: MTL SR-IOV GGTT path: PF MMIO bootstrap GGTT updates active`
- steady-state path:
  - `xe: MTL SR-IOV GGTT path: PF VF2PF relay GGTT updates active`

The code in `pf_process_update_ggtt_msg()` performs:

- VF-originated GGTT message decode,
- split-by-PTE-flags handling,
- `xe_ggtt_update_vf_ptes()` application to the PF-owned VF GGTT node.

### 7.2 What This Means

`xe` does carry the same broad MTL idea that old `i915` had:

- bootstrap may need MMIO,
- steady-state GGTT update should be PF-mediated,
- PF applies VF updates instead of trusting the VF to own the whole path.

This is the strongest direct conceptual inheritance from the old `i915` MTL
SR-IOV story.

## 8. PAT, Flat CCS, And Compression Context In `xe`

### 8.1 MTL PAT Setup

Key file:

- `drivers/gpu/drm/xe/xe_pat.c`

For Meteor Lake, the local table maps:

- `XE_CACHE_NONE -> 2`
- `XE_CACHE_WT -> 1`
- `XE_CACHE_WB -> 3`

And VFs cannot program PAT:

- `if (IS_SRIOV_VF(xe)) xe->pat.ops = NULL;`

That means:

- PAT is a PF-defined environment from the VF point of view.

### 8.2 `has_flat_ccs` In `xe`

The local code uses:

- descriptor-level `has_flat_ccs`,
- then runtime detection and possible override in `probe_has_flat_ccs()`.

Important policy detail from the later mailing-list discussion:

- `has_flat_ccs` is not purely "compression happens",
- it also steers which display/compression path is appropriate.

So the `xe` MTL/ARL story is partly a feature-detection story, not only a PAT
story.

## 9. Migration In `xe`

### 9.1 PF Migration Support Exists, But Is Gated

Key file:

- `drivers/gpu/drm/xe/xe_gt_sriov_pf_migration.c`

The crucial gate is:

- `GUC_FIRMWARE_VER(&gt->uc.guc) < 70.54.0`
  -> disable migration support

This is a major difference from the old `i915` story:

- `i915` documents and implements a full migration/recovery protocol,
- `xe` in this tree has migration code, but it may be completely disabled in
  practice by firmware version.

### 9.2 VF Compression Metadata Save/Restore Exists In `xe`

Key file:

- `drivers/gpu/drm/xe/xe_sriov_vf_ccs.c`

The kernel-doc block is explicit:

- save compression metadata before migration,
- migrate VM,
- rebase GGTT,
- notify `VF_RESFIX_DONE`,
- restore compression metadata afterward.

This is one place where `xe` adds a mechanism that is spelled differently from
old `i915`:

- VF CCS save/restore is a distinct documented subsystem.

## 10. Display / PM Work Around MTL / ARL In `xe`

The `xe` driver has also been accumulating non-SR-IOV platform fixes that
still matter to MTL/ARL behavior.

Examples from upstream pull and stable traffic:

- `drm/xe: Cleanup has_flat_ccs handling`
- `drm/xe: Update runtime detection of has_flat_ccs`
- `drm/xe: Fix missing conversion to xe_display_pm_runtime_resume`
- `drm/xe: Fix DSB buffer coherency`

Taken together, these say:

- `xe`'s MTL/ARL behavior is still shaped heavily by display/PM/coherency
  cleanup,
- not only by explicit SR-IOV code.

## 11. What The `xe` Codeflow Says Overall

The `xe` SR-IOV design says:

- PF/VF role detection and feature masking are first-class.
- PF lifecycle management is tightly coupled to PCI enable/disable and runtime
  PM.
- MTL SR-IOV GGTT handling is explicitly PF-mediated and split into bootstrap
  versus relay stages.
- runtime register sharing exists, but the MTL contract is currently more
  generic than in old `i915`.
- migration exists conceptually, but can be blocked by firmware gating.
- platform correctness for MTL/ARL is distributed across SR-IOV code, PAT,
  feature detection, and display/PM fixes rather than one centralized policy.
