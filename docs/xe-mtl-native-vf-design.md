# Native Xe VF on MTL: remaining implementation contract

The v5.1 run has answered the immediate bootstrap question. A VF can use
PF-mediated GGTT mappings to initialize normal Xe memirq and primary-GT
CT, and can clear those mappings after acknowledged consumer resets and
renewed GuC negotiation. The missing production work is **GGTT update
integration and lifetime/recovery**, not a replacement guest kernel or
another interrupt backend.

Do not turn off the final diagnostic stop and call the driver complete.
The diagnostic deliberately limits probe progress, bypasses ordinary
paths, and holds forever on uncertain completion. Those restrictions made
the experiment interpretable; they are not production error handling.

## Proposed native-VF series after the PF foundation

### 1. Introduce a range update operation with completion/error semantics

Reuse Xe's GGTT allocator, PTE encoding and resource cursor. Keep direct
platform operations for existing platforms, but allow the MTL VF backend
to submit a range and report failure. A `void` per-PTE callback cannot
express failure or efficiently batch a remote request. Audit every
map, scratch clear, node removal, BO move and probe-unwind caller before
switching the VF backend.

Specify separately whether an operation failed before submission or has
uncertain completion. A generic negative return after submission must
not let a caller reuse the GGTT node or unmap the DMA backing. Where an
existing teardown API cannot return errors, move completion earlier into
an ownership stage that can wait or initiate supported recovery.

### 2. Implement the bounded early transport and batching

Before CT buffers are mapped, use the existing GuC MMIO channel and the
PF's established update format. Serialize the scratch-register exchange,
validate replies and updated counts, and split ranges at ABI limits,
DMA discontinuities and PTE-attribute changes. Reuse the v5.1-tested
contiguous-run and duplicate-clear encoding; do not send one request and
two GT invalidations per page.

Uncertain PTE requests must not inherit the ordinary MMIO helper's automatic
replay. A negotiation retry and replay of an already-submitted update are
different operations. The small wire magic field is not a durable generation
or timeout-cancellation protocol.

### 3. Define ownership across normal CT operation and teardown

Choose an explicit transport transition with no update in flight. The
existing PF supports a CT request format, but that path still needs
end-to-end validation. Alternatively, continued MMIO use after CT starts
would need an explicit firmware/locking contract; v5.1 disallows it.
Avoid a duplicate workqueue and second lifetime system where the existing
Xe fences and GGTT node/BO ownership can express the required ordering.

Do not free or repurpose a GGTT range or DMA mapping until its final clear
and all required invalidations have completed, or a documented reset/drain
has made any old update impossible. A GEM/module reference by itself does
not keep DRM-managed TTM and GGTT infrastructure alive after failed probe.
Do not add a permanent reference leak or skip DMA unmapping to conceal an
unresolved remote update.

### 4. Integrate reset and failure completion before enabling the VF

The observed clean shutdown order is:

1. Finish all outstanding updates and stop their callers.
2. Stop consumers on both GTs using the supported VF reset operation.
3. Re-establish GuC version negotiation after each reset, with CT still off.
4. Renew PF relay negotiation, clear owned mappings and await completion.
5. Release the backing memory and ordinary Xe-managed resources.

This is a demonstrated successful sequence, not a general recovery proof.
For an uncertain update, a recovery barrier must cover the entire chain:

`VF submission -> GuC relay -> PF receive/worker -> PTE write -> both-GT invalidation -> reply`

A receive-time generation snapshot covers only requests already received
by the PF. A VF consumer reset does not by itself establish that an older
firmware-held relay request is gone. Specify and verify the reset/drain
contract or introduce an agreed protocol extension before permitting
address reuse. Do not infer this guarantee from acknowledgement counts,
CT disablement, PCI reset log messages or a delay.

Review failed probe, ordinary remove, asynchronous reset, PF reset, CT
restart, FLR, reprovisioning and migration against the same ownership rule.
The diagnostic holds and reset suppression must disappear only once the
normal Xe recovery path has an explicit completion policy.

### 5. Enable native MTL VF probing last

Only remove the defensive gate after range updates, clears, error
propagation and recovery ownership are implemented together. Keep other
platform behavior unchanged, retain existing PM ownership, and do not
extend the MTL-H evidence to every device sharing the MTL/ARL descriptor.
Full probe, command submission and recovery validation are distinct from
the bootstrap result already obtained.

## What can be concluded without another experiment

The tested first GGTT mapping came from `memirq_alloc_pages()` for a 4 KiB
BO. The earlier BAR offset calculation was in bounds; bounds alone never
established VF permission. Replacing that access with PF-mediated updates
allowed the later memirq and CT stages to work. Together with the source
workarounds, this makes unsupported VF GGTT access a strong explanation
for the original failing path. The original hang still has no captured
faulting MMIO instruction, so it should not be presented as a proved
hardware root cause.

The source and logs justify the sequence and split above. They do not
justify a complete production transport-drain contract. That is why this
review delivers a clean PF series and freezes the successful diagnostic,
instead of adding an unvalidated native enablement commit. No further
hardware run is scheduled or required to review these artifacts.
