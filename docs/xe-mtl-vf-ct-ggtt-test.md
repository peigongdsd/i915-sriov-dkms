# Meteor Lake VF CT GGTT experiment, v6

Branch: `codex/xe-mtl-vf-ct-ggtt-v6`.
Base: the hardware-tested v5.1 diagnostic at
`292dec2bfa0d121df72012cb43f14c437edf5146`.
Live identity: **`diagnostic=mtl-ct-ggtt-v6`**.
Load the guest module with **`mtl_vf_bootstrap_test=1`**; leave
`mtl_vf_relay_test` off. Both default off.

This is a runnable guest experiment, not full native VF support. It tests
PF-mediated GGTT mapping and ordinary BO destruction while the primary GT's
normal CT channel is active. It deliberately stops before scratch-page setup,
media-GT CT initialization, engine submission or DRM registration.

## Evidence and purpose

The supplied v5.1 capture records native CT handshake/runtime-query success,
four GuC memirq dispatches, both consumer resets and post-reset GuC version
handshakes, and acknowledged clearing of all six bootstrap extents (549 pages).
The guest returned the intentional -95 and remained responsive. That establishes
one successful bootstrap/cleanup run. It did not exercise CT GGTT updates or
engine execution. MTL already uses Xe's memory-based interrupt infrastructure;
its GGTT access restrictions are a separate issue.

V6 preserves that early MMIO mapping and final cleanup sequence. It adds two
temporary BO lifetimes between the successful native CT query and the deliberate
probe stop. No PF changes, firmware changes or host kernel replacement are
needed. The working host PF remains `02acd04`, generation 204.

The separate `codex/xe-mtl-vf-range-v1` branch is preparatory work over the clean
PF review series. This experiment extends the tested v5.1 branch instead of
replacing its working containment and cleanup with an untested lifetime design.
It carries forward the range/PTE validation, but does not claim to complete that
branch's production integration or recovery contract. The diagnostic commits
should not be presented as a production upstream series.

## Implemented experiment

1. Follow the existing v5.1 sequence: early BO mappings via MMIO, memirq setup,
   primary CT registration, native PF handshake and runtime query.
2. Use `xe_bo_create_pin_map_novm()` to allocate a 1,025-page system-memory BO
   with ordinary Xe WB PAT selection. The existing GGTT allocator and DMA
   cursor form requests through the PF's existing `UPDATE_GGTT32` CT ABI.
   Adjacent DMA pages coalesce, with at most 1,024 pages per request; fragmented
   backing produces additional requests.
3. Release it through `xe_bo_unpin_map_no_vm()`. The existing diagnostic TTM
   `delete_mem_notify` hook now clears through CT before DMA backing can be
   released. Mapped diagnostic BOs are excluded from eviction/shrinking during
   the unpin-to-delete interval. Wait for software GGTT node removal, including
   deferred TTM/node destruction, before advancing.
4. Repeat with a one-page BO using Xe's `NEEDS_UC` selection. Record its relative
   address; same-address reuse is observable but is not an acceptance condition.
5. Query runtime information again through normal Xe CT. Require 1,026 mapped
   and 1,026 cleared temporary pages, then enter the existing deliberate stop.
6. Stop the bootstrap consumers on both GTs, renegotiate the GuC interfaces,
   clear the remaining bootstrap mappings via MMIO, then permit devres cleanup.

Neither temporary BO's address is registered with a firmware consumer or used
in an engine workload. CT map/clear acknowledgements exercise the PF handler and
its required invalidations. They do not independently read back PTEs or establish
GPU access to those temporary BOs. The count of memirq dispatches is recorded;
CT success alone is not proof of interrupt delivery if the count is zero.

The PF source already supports the CT request format. V6 reuses the existing
request descriptor and PTE encoding, RID matching, CT buffers, interrupt path,
BO allocator, PAT selection and TTM lifecycle. It adds no direct VF GGTT BAR
access, per-PTE invalidation or permanent power-management reference.

## Completion and failure rules

The single-attempt CT helper uses the common Xe sender, including ring-space
and fence-allocation waits before submission. It does not replay a submitted
request after GuC RETRY. The single-attempt relay helper similarly returns PF
RETRY rather than resending. GuC BUSY shares a one-second response deadline;
PF BUSY shares the existing 2,500 ms relay response deadline. Queue admission
can take additional time. Ordinary Xe callers retain their existing behavior.

An error or malformed reply does not prove cancellation. Every GGTT error,
short/wrong-count reply, lost CT channel or observed reset holds the operation
and its backing; it does not issue a rollback, fall back to MMIO, or release
resources. A missing temporary-node removal also holds before changing CT state.
An allocation failure conservatively holds because allocation failure cleanup
may itself have been deferred. A final runtime-query failure is not reported
as success and does not proceed into consumer reset.

The normal stop is reachable only after the two temporary lifetimes complete.
The consumer reset is used with no GGTT request outstanding. It is not a promise
that reset cancels a timed-out PF request. Production recovery, arbitrary BO
movement, suspend/resume, external reset and general unbind are unfinished.

## Single guest run

Use the exact commit supplied with the handoff, rather than an advancing branch
name. Do not reuse an old VM that is held in a previous diagnostic. Confirm a
fresh healthy host state and that the previous assignment has been released by
an established recovery or power-cycle procedure before starting.

Preserve host generation 204, PF `02acd04`, Nix pins and boot entries. Windows
must remain shut down. VF1 `0000:00:02.1` stays owned by `vfio-pci` on the host.
Keep automatic host Xe binding disabled and isolate the older device-add rule.
Use the established guest assignment procedure; do not reset, unbind or change
VF ownership during this experiment. Record host baseline errors rather than
assuming that responsiveness alone establishes GPU health. New or unresolved
host GPU errors should be reported before another probe.

Reuse the lightweight Linux VM and exact Linux 7.3.3 guest build tree. Rebuild
both Xe and compatibility modules with `KCFLAGS=-g`. Record the exact source
commit, module SHA-256, vermagic and srcversion. Retain unstripped modules.
No replacement guest kernel or NixOS activation is required.

Use the previously selected host-local serial and host-kernel capture, and
state that capture is host-local. Verify capture before explicitly loading Xe
in the guest with `mtl_vf_bootstrap_test=1`, `mtl_vf_relay_test=0` and verbose
console logging. Do not let the module load before capture is ready.

Disable automatic VM timeout teardown, guest watchdog restart and
panic-on-hung-task. If a hold appears, keep the VM running and VF assigned;
do not terminate QEMU, shut down the guest, reset/unbind the VF, force-remove
Xe, start Windows or bypass the hold in GDB. Save the last checkpoint and
report it. These holds are experimental resource containment, not recovery.

Serial capture is sufficient; GDB is optional. If used, a breakpoint at
`xe_ggtt_vf_ct_test()` before the first temporary allocation is useful. Do not
pause or single-step while a CT/relay response is pending, because doing so
can create artificial timeouts. Use this run's module symbols and addresses.

### Required successful checkpoints

```text
VFPROBE: diagnostic=mtl-ct-ggtt-v6 before VF_CAP ...
... early MMIO mappings and memirq initialization returned 0 ...
VFPROBE: native CT handshake and runtime query passed; memirq_dispatches=N
VFPROBE: before CT BO allocation case=0 pages=1025
VFPROBE: CT GGTT acknowledged page=... pages=... replicate=1
... additional map batches as needed ...
VFPROBE: before ordinary CT BO release case=0 relative=...
VFPROBE: CT GGTT acknowledged page=... pages=1024 replicate=0
VFPROBE: CT GGTT acknowledged page=... pages=1 replicate=0
VFPROBE: CT clear before TTM backing release relative=... pages=1025
VFPROBE: CT BO node removed case=0
VFPROBE: before CT BO allocation case=1 pages=1
... CT map, ordinary release, CT clear and node removal for case=1 ...
VFPROBE: CT GGTT experiment passed maps=1026 clears=1026 memirq_dispatches=N
... both GT consumer reset and post-reset GuC version acknowledgements ...
... remaining bootstrap mapping clears ...
VFPROBE: all bootstrap GGTT mappings removed before devres cleanup; ct_passed=1
... Xe probe returns the intentional -95 ...
GUEST_ALIVE_AFTER_PROBE
VF_GUEST_FINISHED
```

Require every phase, matching map/clear ranges, no hold or suppressed
reset/migration, no allocator/TTM warning, and no new host Xe errors. A final
-95 by itself is not success. The early-bootstrap extent count may vary;
account for every mapped extent rather than requiring the old six addresses.
The temporary CT totals must be exactly 1,026 pages in each direction.

Only after completed cleanup and the guest-alive marker, shut the guest down
normally using the established diskless guest shutdown mechanism. Verify QMP
reports shutdown before releasing QEMU, then verify host health and VFIO
ownership. Do one run; do not automatically retry. Return complete serial,
host-kernel and optional GDB logs, module identities and a checkpoint summary.

## Local validation

The modules build with debug information against local Linux 7.3.4. The testing
host must rebuild against its exact Linux 7.3.3 tree. No hardware was exercised
on the build host.

Offline tests compile the actual C helpers, replacing hardware/TTM services
with scripted models:

- `scripts/test-xe-mtl-vf-relay.py`: the existing 14 MMIO protocol cases.
- `scripts/test-xe-mtl-vf-ct.py`: 18 CT/relay cases, including GuC/PF RETRY,
  timeout, bounded BUSY, failure, late/wrong-RID replies, success overtaking
  BUSY, explicit EBUSY/ENOMSG failures, and unchanged ordinary CT retries.
- `scripts/test-xe-mtl-vf-bootstrap.py`: 46 mapping/lifetime cases, including
  the existing 18 bootstrap cases, CT batching, fragmented DMA, malformed
  responses, reset observations, partial-map/clear response loss, no MMIO
  fallback, range/PTE validation, reclaim exclusion and deferred destruction.

The new CT and extended bootstrap suites pass with AddressSanitizer and
UndefinedBehaviorSanitizer. These models check decisions and ordering; they do
not exercise real TTM concurrency, interrupts, firmware or DMA visibility.
Checkpatch and whitespace checks accompany the exported commits.

A successful v6 run would establish the CT GGTT/BO-lifetime step needed before
continuing normal VF initialization. Full scratch setup, both GTs, default
contexts, submission and workloads still need implementation and testing.
