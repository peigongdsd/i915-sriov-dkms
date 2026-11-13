# Meteor Lake SR-IOV: platform notes

These notes describe the source inspected for the ThinkBookX / Core Ultra 9
185H, PCI ID `8086:7d55`. They distinguish driver contracts from hardware
validation. No native Xe VF has been successfully tested by this work.
See [branch status](xe-mtl-vf-gsm-v1.md) before using this branch.

## Source versions

- Reproduction baseline: [peigongdsd e9130af](https://github.com/peigongdsd/i915-sriov-dkms/tree/e9130affe933dfc45309dc7a82599a1d7a38517e),
  seven commits over strongtz `bea7187037269859515dd0b9bece5c50a0bcadb9`.
- Comparison: [peigongdsd/master at 168f20e](https://github.com/peigongdsd/i915-sriov-dkms/tree/168f20e718076607aa4e16f9852724548961e751).
- Alternative design: [xbomber at 817d799](https://github.com/xbomber/xe-sriov-mtl-arl/tree/817d7992f1d2a9a4798fc32cb14d1a3192d3e20a).
- Upstream snapshot: [Linux at 7e1392a](https://github.com/torvalds/linux/tree/7e1392a42ea288d70a266f6553fe06f57f8647ea/drivers/gpu/drm/xe).

The branch retains the experimental baseline. Its `has_sriov` flag for MTL
is not proof of upstream support: the upstream snapshot's `mtl_desc` does
not set that flag. Neither PCI SR-IOV capability nor successful VF creation
establishes a working native VF driver.

## What differs, and what does not

| Area | MTL contract in the inspected source | Consequence |
| --- | --- | --- |
| Graphics/media IP | Common Xe discovery selects IP descriptors from GMD_ID; the direct-GSM mapping adds no version allowlist. The user's working ThinkBookX driver reports 12.71 / 13.00. | Keep IP selection in the common path. Successful discovery does not establish firmware permission. |
| Topology | One logical Xe tile with primary and media GTs. GGTT is shared; GuCs, TLBs, resets and low-level power controls are per GT. | A shared GGTT update needs both affected GTs' invalidation and lifecycle handling. |
| CPU GGTT access | i915 documents an MTL BAR access hang workaround. Direct GSM access requires firmware permission. | An unavailable direct mapping is not permission to fall back to BAR writes. |
| VF access | A VF cannot assume access to the PF's physical GSM mapping or privileged GGTT update commands. | A working PF update method does not automatically provide a VF update method. |
| Memory | MTL is integrated; the Xe descriptor uses a 46-bit DMA mask and 48-bit GPU virtual addresses. | Do not import discrete-GPU local-memory/LMTT assumptions or equate DMA and virtual address widths. |
| Flat CCS | `mtl_desc` does not enable flat CCS; `lnl_desc` does. | This is a specific feature difference, not evidence of a GGTT hang or absence of all compression on MTL. |
| VF interrupts | Both baseline and inspected upstream use `GRAPHICS_VERx100 >= 1250` for memory-based interrupts. MTL 1270 and 1271 satisfy this software predicate. | This is an assumption made by the driver, not validation on this hardware/firmware. Neither working delivery nor absence of support has been demonstrated. |
| GuC communication | Early MMIO bootstrap and later CT transport are separate stages. | Failure before CT readiness does not mean MTL lacks GuC or CT support. |
| Display/security | MTL has display and PXP; the baseline explicitly handles media-GT GSC/PXP around VF enablement. | Restrictions on VF display, PCODE and HECI access are not missing platform hardware. |

Sources: [platform descriptors](../drivers/gpu/drm/xe/xe_pci.c),
[tile design](../drivers/gpu/drm/xe/xe_tile.c),
[feature predicates](../drivers/gpu/drm/xe/xe_device.h),
[VF feature filtering](../drivers/gpu/drm/xe/xe_device.c),
[interrupt paths](../drivers/gpu/drm/xe/xe_irq.c), and
[PF enable/disable](../drivers/gpu/drm/xe/xe_pci_sriov.c).
The upstream memory-interrupt predicate is also visible in the
[pinned upstream header](https://github.com/torvalds/linux/blob/7e1392a42ea288d70a266f6553fe06f57f8647ea/drivers/gpu/drm/xe/xe_device.h).

MTL and ARL PCI IDs share `mtl_desc` and `XE_METEORLAKE` in this tree.
That explains why the defensive native-VF gate covers both. It does not
establish that every ARL variant has the same IP revisions or has been tested.

## GGTT access: the important restriction

`i915_direct_stolen_access()` documents **Wa_22018444074**: MTL BAR accesses
can hang, and direct GSM/DSM access is conditional on firmware relaxing
permissions. The predicate excludes guests and VFs and checks
`MTL_PCODE_STOLEN_ACCESS` (`0x138914`) against `STOLEN_ACCESS_ALLOWED`.
See [i915_utils.c](../drivers/gpu/drm/i915/i915_utils.c).

The companion **Wa_22018453856** references in
[intel_ggtt.c](../drivers/gpu/drm/i915/gt/intel_ggtt.c) skip the VF's GGTT
CPU mapping when the binder is required. These are source-documented
restrictions; they are not a captured explanation of this machine's hang.

The baseline Xe PF maps GSM directly when permission is present, but can
otherwise retain its BAR mapping. This branch rejects SR-IOV PF probe when
the root-tile requirement, permission, nonzero GSM base or mapping is absent.
It does not add a GPU binder fallback. Non-SR-IOV probing is unchanged.

The user reported that NixOS generation 203, using `73c7714`, reached stage 2
and the graphical target despite Xe failing in the initrd with `-95`
(`EOPNOTSUPP`). That revision admitted only graphics IP 1270. The reported
1271 / 1300 pair was rejected before reading the GSM permission register;
its combined error message incorrectly suggested a firmware restriction.
`02acd04` first widened the check to admit 1271. The subsequent simplification
removes the graphics/media allowlist entirely: `xe_probe_ips()` already
requires a recognized graphics descriptor and explicitly allows absent media
support before GGTT initialization. Direct GSM mapping has no demonstrated
need for a second IP restriction. Root-tile and firmware failures still have
distinct diagnostics. Media-13 checks in the relay and invalidation paths
are separate and unchanged; this is not a claim of support for additional
VF configurations. This boot does not establish GSM permission
or successful direct-GSM access. These observations are user-supplied;
the target journal was not independently inspected here.

xbomber provides a different PF backend using privileged `MI_UPDATE_GTT`
batches on the existing migration queue. That introduces job/fence and
bootstrap dependencies. It is a candidate when CPU access is unavailable,
not evidence that this machine requires that backend. Direct GSM avoids that
extra submission work when firmware permits it; no power or performance
benefit has been measured here.

## Probe ordering and plausible failure

The baseline native path is roughly:

1. PCI probe maps MMIO and `xe_sriov_probe_early()` reads `VF_CAP_REG`.
2. VF discovery uses GuC MMIO bootstrap and VF configuration queries.
3. GGTT discovery establishes the VF allocation; early GGTT-backed buffers
   are needed before later CT communication is available.
4. The baseline GGTT writer still reaches the BAR-backed PTE window.

Step 4 conflicts with the MTL VF access restriction and is a plausible
failing path. Missing off-host trace means steps 1-3 and other failures are
not ruled out. The baseline already has PF GGTT relay services, but that
alone does not make its native VF writer use them.

The rewritten branch rejects host-enumerated native VFs before MMIO. For an
assigned guest VF without `pdev->is_virtfn`, it rejects immediately after
existing MMIO VF detection. The guest check therefore still depends on that
initial MMIO access; it cannot prove every possible early fault is avoided.

## Lifecycle and power: avoid false assumptions

A relay timeout proves only that a reply was not received. It does not prove
the PF has cancelled a queued PTE write. Address reuse after such a timeout
needs a completion or quiescence guarantee covering the PF worker and both
GTs. Retaining a GEM reference does not retain the DRM-managed GGTT/TTM
infrastructure. Permanent BO/module references are not a complete solution.

The baseline already skips `xe_pm_runtime_init()` for **all VFs**. That is
a driver limitation, not a new MTL restriction introduced by this branch.
GT C6 and PCI runtime PM are different mechanisms. No additional blanket
PM restriction or permanent wake reference is added.

Similarly, the generic VF migration code checks memory-based IRQ support;
MTL passes that software predicate. This does not establish working interrupt
delivery on the target, or migration correctness for
the experimental relay. Migration remains unvalidated, rather than being
declared impossible because of an absent interrupt feature.

## Evidence still needed

Keep the `e9130af` Nix pin as the reproduction baseline. Before another
deliberate native bind, isolate the old VFIO device-add rule and capture
logs off-host. Instrument before/after VF detection, each GuC bootstrap
exchange, GGTT configuration and the first PTE access. A last checkpoint
before a write can localize a hang; it does not prove the write completed.

For future native forwarding, separately establish handling of late PF
requests, CT shutdown, both-GT reset, probe unwind and rebind before adding
batching or advertising performance. Prefer existing Xe fences, reset and
resource ownership once their ordering contract has been demonstrated.

The [VF interrupt test plan](xe-mtl-vf-memirq-test.md) separates capability
selection, firmware acceptance and actual interrupt delivery. Do not mark
memory-based VF interrupts as tested from the version predicate alone.
