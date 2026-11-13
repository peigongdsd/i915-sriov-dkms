# MTL first VF mapping: findings after v2

## Evidence and its limits

The downstream report for `fe1ff865e1b622164453bf4d2ec3a6d9a17ec3d1`
identifies the first mapping caller as `memirq_alloc_pages()`, through BO
creation and `__xe_ggtt_insert_bo_at()`. Direct GDB inspection and driver
logging agree on a 4096-byte BO, flags `0x260a2`, and GGTT range
`[0x7ec00000, 0xfec00000)`. Both GTs completed discovery; the guest returned
through the deliberate failure and shut down. Host PF `02acd04` remained
running. Raw remote log files were not independently inspected here.

The flags decode to SYSTEM, GGTT, PINNED, NEEDS_CPU_ACCESS, NEEDS_UC and
GGTT_INVALIDATE in this tree. They match the observed report buffer. This
does not establish that interrupt delivery works or fails. V2 stopped before
BO validation inside the GGTT insertion function, node allocation, PTE
encoding and hardware access.

## Baseline path beyond the stop

The following follows the `e9130af` implementation in
[xe_ggtt.c](../drivers/gpu/drm/xe/xe_ggtt.c),
[xe_memirq.c](../drivers/gpu/drm/xe/xe_memirq.c), and
[xe_bo.c](../drivers/gpu/drm/xe/xe_bo.c). The diagnostic branch changes the
final action; it is not evidence of baseline execution on hardware.

1. `xe_bo_validate()` prepares backing memory. GGTT insertion then acquires
   its existing runtime-PM reference and allocates a software node.
2. `drm_mm_insert_node_in_range()` allocates within the VF's relative GGTT
   range. `xe_ggtt_node_addr()` adds the VF GGTT base. A returned relative
   offset must not be confused with that absolute GPU address.
3. NEEDS_UC selects XE_CACHE_NONE. The platform PAT lookup supplies the
   index; `xelpg_ggtt_pte_flags()` encodes PRESENT and PAT bits 52/53.
   System memory does not set the local-memory bit.
4. `xe_ggtt_map_bo()` walks the DMA scatterlist. For this one-page BO it
   emits one candidate PTE: encoded flags OR the VF's DMA address.
5. The PTE writer reaches `writeq()` through the VF's `ggtt->gsm`, set to
   its MMIO mapping plus 8 MiB. This bypasses the VF-aware register helpers
   in `xe_mmio.c`. Their access filtering cannot make this write safe.
6. With GGTT_INVALIDATE, Xe reads VF_CAP_REG as a posting barrier and then
   invokes invalidation for each GT. A returned CPU store alone would not
   prove completion of a posted write; a later read can expose the stall.

If the allocator chooses relative offset zero, the first absolute GGTT
address would be `0x7ec00000`, and the BAR byte offset would be
`0x800000 + (0x7ec00000 >> 12) * 8 = 0xbf6000`. This is a prediction, not
an observed allocation. It fits a 16 MiB BAR, but being within a mapped BAR
does not establish that an MTL VF is allowed to use that window.

The selected writer may include Wa_22019338487 accounting. Its integrated
media path performs a dummy GMD_ID write every 63 GGTT writes. A first
single-entry mapping with a zero counter would not reach that threshold.
This distinguishes it from the immediate PTE write and posting read.

## Invalidation does not supply an early completion guarantee

In [xe_guc_tlb_inval.c](../drivers/gpu/drm/xe/xe_guc_tlb_inval.c),
`send_tlb_inval_ggtt()` uses CT only when both CT and submission are enabled.
For a VF before that point, it returns `-ECANCELED` without using the PF's
MMIO invalidation path. The ordinary API normalizes this to success and
signals its local fence. This is existing Xe behavior, not proof that the
reported hang is an invalidation timeout.

A future PF-mediated update must therefore provide its own valid completion
contract, including required visibility across the shared graphics/media
GGTT. Reusing the ordinary VF return value as proof of PF completion would
be incorrect. The current working PF's strict relay reply path preserves
issue/fence failures, but the VF still needs to handle an absent reply.

## Comparison with other paths

- The inspected upstream snapshot `7e1392a42ea288d70a266f6553fe06f57f8647ea`
  has the generic BAR writer, but its MTL descriptor does not enable SR-IOV.
  Its writer is not evidence that MTL VF BAR updates are supported.
- The i915 tree has Wa_22018453856 handling that skips VF CPU GGTT mapping
  when the binder workaround is required, and routes updates through the
  PF. Its early transport uses MMIO; later updates can use CT. Separately,
  Wa_22018444074 documents MTL BAR access hangs and firmware-dependent PF
  direct-GSM access. See [intel_ggtt.c](../drivers/gpu/drm/i915/gt/intel_ggtt.c),
  [intel_iov_query.c](../drivers/gpu/drm/i915/gt/iov/intel_iov_query.c), and
  [i915_utils.c](../drivers/gpu/drm/i915/i915_utils.c).
- The working Xe PF at `02acd04` can use firmware-permitted direct GSM and
  provides MMIO/CT GGTT relay services. The PF validates relative ranges and
  rewrites VF ownership bits. A successful Windows guest does not show which
  of those services it uses; that needs a trace if it becomes relevant.
- peigongdsd/master snapshot `168f20e718076607aa4e16f9852724548961e751`
  includes VF forwarding but falls back to raw writes on map/clear failure.
  Do not carry that fallback into a fix for restricted VF BAR access.
- xbomber snapshot `817d7992f1d2a9a4798fc32cb14d1a3192d3e20a` provides
  privileged PF `MI_UPDATE_GTT` jobs through Xe's migration infrastructure
  and waits on fences. It is a useful lifetime/completion reference, not
  a reason to replace a working firmware-permitted PF CPU backend with
  additional GPU jobs.

Sources for external snapshots:
[upstream Xe](https://github.com/torvalds/linux/tree/7e1392a42ea288d70a266f6553fe06f57f8647ea/drivers/gpu/drm/xe),
[peigongdsd/master](https://github.com/peigongdsd/i915-sriov-dkms/tree/168f20e718076607aa4e16f9852724548961e751),
[xbomber](https://github.com/xbomber/xe-sriov-mtl-arl/tree/817d7992f1d2a9a4798fc32cb14d1a3192d3e20a).

Do not diagnose missing VFID bits in the VF-generated PTE as an independent
defect: supported VF apertures may preserve ownership in hardware. When
the PF writes on behalf of a VF, however, it must impose the authenticated
requester's VFID itself. Preserve the VF DMA address; do not substitute a
guest CPU address or infer a host physical address. TME being enabled is
not evidence of an encryption-related failure.

## Requirements for the eventual fix

Keep common Xe allocation, PAT encoding and resource ownership. Add only
the required MTL VF update backend, with MMIO bootstrap transport before
CT-backed buffers exist. No exact IP allowlist, raw-write fallback or
blanket PM restriction follows from this evidence.

Before wiring forwarding into a void PTE writer, establish how errors reach
the allocation caller. A failed request must not be converted to successful
BO creation. A mapping that has never been submitted can release its software
reservation immediately; one with uncertain remote completion cannot.

The existing PF queues MMIO work and snapshots local VF generations/GT
epochs. Those checks reject known stale work, but a sender timeout is not
cancellation. In particular, a request arriving after a reset could obtain
a new receive-time snapshot unless the transport/reset contract drains old
requests. That ordering has not been established by the current tests.

Use the existing reset/FLR machinery if it can demonstrably close admission,
drain or invalidate both GTs' outstanding work and prevent a late write
before address reuse. A GuC VF-state reset must not be assumed to cancel
already queued host PF work. Avoid inventing a new protocol until the
existing firmware/transport guarantees have been checked.

Clear/unmap, failed probe, reset and teardown need the same completion rule
as map. Ordinary `ggtt_node_remove()` writes scratch PTEs while the GGTT
is online before removing the node, so it is unsuitable for rolling back an entirely unsubmitted
diagnostic mapping. Permanent GEM/module references do not retain the
DRM-managed device infrastructure. Reintroducing the withdrawn retention
scheme would not solve this.

Once correctness is established, batch contiguous PTE updates and invalidate
once per completed batch as supported by the existing ABI. Avoid per-page
round trips and duplicate VF/PF invalidation. No performance or power claim
is supported by the current tests.

## Selected next experiment

[V3](xe-mtl-vf-pte-plan.md) advances only the observed one-page system BO:
validate it, allocate a node, inspect its candidate PTE, then remove the
unused software reservation and fail. It sends no PF request and performs
no PTE write, clear or GGTT invalidation for that mapping. This separates
allocation/address construction and rollback from restricted hardware
access. It still does not identify the original failing instruction.
