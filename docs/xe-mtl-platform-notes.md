# Meteor Lake SR-IOV: platform notes

These notes distinguish source contracts, observed behavior on the
ThinkBookX/Core Ultra 9 185H (`8086:7d55`), and remaining assumptions.
See the [review-series scope](xe-mtl-review-series.md) and
[v5.1 results](xe-mtl-vf-bootstrap-results.md). Successful bounded native
VF bootstrap is now demonstrated; full native VF graphics is not.

## Pinned source comparison

- Original reproduction branch:
  [peigongdsd e9130af](https://github.com/peigongdsd/i915-sriov-dkms/tree/e9130affe933dfc45309dc7a82599a1d7a38517e),
  seven commits over strongtz `bea7187037269859515dd0b9bece5c50a0bcadb9`.
- Downstream comparison:
  [peigongdsd/master at 168f20e](https://github.com/peigongdsd/i915-sriov-dkms/tree/168f20e718076607aa4e16f9852724548961e751).
- Alternative PF backend and related MTL work:
  [xbomber at 817d799](https://github.com/xbomber/xe-sriov-mtl-arl/tree/817d7992f1d2a9a4798fc32cb14d1a3192d3e20a).
- Upstream comparison:
  [Linux at 7e1392a](https://github.com/torvalds/linux/tree/7e1392a42ea288d70a266f6553fe06f57f8647ea/drivers/gpu/drm/xe).

These are snapshots, not claims about the latest branch tips. Upstream's
MTL descriptor at that revision does not set `has_sriov`. Adding a flag or
successfully creating a PCI VF is not proof of a complete native VF driver.

## Platform distinctions

| Area | Source contract or evidence | Implication |
| --- | --- | --- |
| IP discovery | Common Xe discovery uses GMD_ID; the working device reports graphics 12.71/media 13.00. | Keep admission in common discovery; an extra 12.70-only check rejects this valid device. |
| GT topology | One logical Xe tile with primary and media GTs; shared GGTT, separate GuCs/TLBs. | Shared mappings require both affected GTs' invalidation and lifecycle handling. |
| CPU GGTT access | MTL BAR access has a documented workaround; direct GSM depends on firmware permission. | Never treat a mapped, in-bounds BAR offset as permission to access VF PTEs. |
| VF privilege | A VF cannot assume the PF's physical GSM mapping or privileged GGTT command access. | Supply a PF-mediated backend rather than copying the PF address into the guest. |
| Memory widths | The descriptor uses a 46-bit DMA mask and 48-bit GPU virtual addresses. | Validate DMA and virtual address widths separately; do not import discrete-GPU local-memory/LMTT assumptions. |
| Flat CCS | `mtl_desc` does not enable flat CCS; `lnl_desc` does. | A specific descriptor difference, not proof that MTL lacks all compression or the cause of this hang. |
| VF interrupts | Xe selects memory-based VF interrupts for graphics IP >= 1250. v5.1 recorded four dispatches and successful primary-GT CT communication. | MTL does not generally lack the newer memory-interrupt mechanism. Other GT/engine classes and migration remain unvalidated. |
| GuC transport | Early MMIO and later CT are separate stages; reset requires renewed GuC version negotiation in the tested sequence. | Distinguish GuC negotiation from PF relay negotiation. |
| GSC/PXP | MTL has display and PXP; this PF path prepares media GSC and suspends/restores PXP around provisioning. | VF filtering of display/PCODE/HECI access is not missing platform hardware. |

Local sources: [descriptors](../drivers/gpu/drm/xe/xe_pci.c),
[feature predicates](../drivers/gpu/drm/xe/xe_device.h),
[VF filtering](../drivers/gpu/drm/xe/xe_device.c),
[interrupt paths](../drivers/gpu/drm/xe/xe_irq.c),
[memirq](../drivers/gpu/drm/xe/xe_memirq.c), and
[VF provisioning](../drivers/gpu/drm/xe/xe_pci_sriov.c).

MTL and ARL IDs share `mtl_desc` and `XE_METEORLAKE` in this tree. The
defensive native-VF gate therefore covers both. The available experiments
cover only the MTL-H machine, not all ARL variants or firmware policies.

## GGTT restriction and implementation choice

`i915_direct_stolen_access()` documents **Wa_22018444074**, the MTL BAR
access hang workaround. Direct GSM/DSM requires relaxed firmware
permissions. That helper excludes guests and VFs and checks
`MTL_PCODE_STOLEN_ACCESS` (`0x138914`) against `STOLEN_ACCESS_ALLOWED`.
See [i915_utils.c](../drivers/gpu/drm/i915/i915_utils.c).
The **Wa_22018453856** references in
[intel_ggtt.c](../drivers/gpu/drm/i915/gt/intel_ggtt.c) also skip a VF CPU
GGTT mapping when the binder is required.

These source workarounds support a plausible failing path; they are not a
trace of the original hang. Earlier v3 instrumentation placed the first
native mapping in `memirq_alloc_pages()`. Its computed PTE BAR offset was
inside the mapped BAR, which establishes bounds but not access permission.
v4 completed a PF-mediated single-page map/clear; v5.1 completed functional
bootstrap with that class of backend. Do not deliberately reintroduce a
direct VF PTE write merely to strengthen the attribution.

The original PF branch could keep the BAR mapping when direct access was
unavailable. This series instead requires the root tile, firmware
permission, a nonzero GSM base and a successful mapping. It returns an
error if those checks fail. Non-SR-IOV probing is unchanged.

xbomber uses privileged `MI_UPDATE_GTT` work on the existing migration
queue as another PF backend. Direct GSM uses fewer submission steps when
firmware permits it. No measured power/performance comparison exists, and
there is no binder fallback in this series for firmware that denies GSM.

## The graphics-IP rejection was a software regression

Generation 203 used a check admitting only graphics IP 1270/media 1300.
It rejected the actual 1271/1300 device before reading firmware permission,
returning `-95` with a misleading GSM-permission message. The hardware IP
had not changed. `02acd04` admitted 1271; the present candidate removes the
redundant allowlist and relies on common Xe IP discovery. Firmware denial,
wrong tile, zero base and mapping failure retain separate checks.

The failed generation-203 probe provided no evidence about permission.
The subsequent working PF, Windows guest, and v5.1 relay acknowledgements
are separate observations. Relay service and assignment invalidation
retain their media-13 predicates; removing the redundant admission check
does not establish additional media-platform support.

## Lifetime, power and evidence limits

A relay timeout means a reply was not received. It does not mean the PF
cancelled its write. An error may occur after PTE writes, including during
invalidation. Existing generation/epoch checks are useful stale-state
checks, not a transport-drain guarantee. BO, GGTT node and DMA lifetimes
must cover completion or proven quiescence through failed probe and reset.

The baseline already skips `xe_pm_runtime_init()` for all VFs. This is not
a new MTL-specific restriction in this series. GT C6 and PCI runtime PM
are distinct. The PF provisioning path already owns a runtime-PM reference;
temporary forcewake is released. No extra permanent wake or blanket PM
prohibition is added, and efficiency has not been benchmarked.

The generic VF migration code's memory-IRQ predicate admits MTL. The
v5.1 dispatch evidence strengthens the interrupt claim, but neither the
predicate nor those four dispatches validates migration or every engine.

The original reproduction pin and deployed host generation remain
historical and operational references; this offline review changes
neither. The [remaining native implementation plan](xe-mtl-native-vf-design.md)
keeps the successful bootstrap result separate from unresolved lifecycle
and workload requirements.
