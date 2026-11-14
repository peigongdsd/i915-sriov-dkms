# Meteor Lake VF scratch and CT reconnection experiment, v7

Branch: `codex/xe-mtl-vf-scratch-v7`.
Frozen, hardware-tested base: `40e8e63e7cb6580dd69549a0b1858c7226a3292e` (v6).
Live identity: **`diagnostic=mtl-scratch-v7`**.
Guest module parameters: **`mtl_vf_bootstrap_test=1 mtl_vf_relay_test=0`**.
Use the exact v7 commit supplied in the handoff, not an advancing branch name.

## Scope

V7 continues through Xe's ordinary scratch allocation, GGTT hole initialization,
primary hardware-engine initialization and post-hwconfig communication reset.
It then reconnects the primary CT channel using Xe's existing memirq registration,
CT enable, PF connection and runtime-query functions. It repeats the v6 temporary
BO lifetimes after that reset, and deliberately returns `-EOPNOTSUPP` before
`xe_guc_submit_init()` is called.

This is a guest implementation checkpoint, not usable native VF support. It
creates no submission queues and runs no engine jobs. Media-GT CT initialization,
default contexts, DRM registration and graphics workloads remain beyond this
checkpoint. Both GT consumer resets are still required for final cleanup.

Why this checkpoint precedes an engine job: v6 stopped before scratch setup and
before Xe's expected post-hwconfig reset. Scratch is referenced by unallocated
GGTT holes as well as freed nodes. Clearing only tracked BO nodes cannot make
scratch backing safe to release. Queue creation would additionally introduce
asynchronous scheduler and deregistration lifetimes that this checkpoint does
not attempt to solve.

## Existing evidence

The supplied v6 report records native CT bootstrap with four memirq dispatches,
1,026 temporary pages mapped and cleared through CT, 17 dispatches by the end,
both consumer resets and post-reset GuC handshakes, acknowledged clearing of
remaining bootstrap mappings, intentional -95 and a responsive guest. The
final runtime query's success follows from the v6 marker's source placement.
The reported fresh baseline and test run had no new host GPU errors. This is
reported hardware evidence; it is not an independent audit of the complete raw
captures on the build host.

The local report of Windows VF graphics working and v6 interrupt delivery must
not be generalized to Linux engine execution. MTL already uses Xe's memory-based
interrupt infrastructure. Its GGTT access restriction is a separate issue.

## Implementation and ordering

1. Preserve v6's early MMIO mappings and primary native CT bootstrap. Keep CT
   GGTT updates enabled after the successful native connection.
2. Let `xe_ggtt_init()` allocate and zero scratch normally. Preserve Xe's PAT
   encoding and `drm_mm_for_each_hole()` traversal. Fill holes through the
   existing PF relay ABI, duplicating the same PTE in batches of at most 1,024
   pages. The scratch DMA address does not advance between entries. Existing
   BO mappings are excluded from this initial fill.
3. Continue the ordinary primary-GT initialization path. Its hardware status
   BOs use the same PF-mediated BO mapping helper. No engine workload is issued.
4. At Xe's normal post-hwconfig reset, retain all backing and use the diagnostic
   single-attempt consumer reset plus the existing GuC interface negotiation.
   End the CT GGTT phase explicitly and invalidate cached MMIO relay negotiation.
   This is an expected, serialized reset after acknowledged requests, not
   recovery from an uncertain GGTT operation.
5. Re-register memirq and CT, connect to the PF and query runtime information.
   Then allocate/release the v6 1,025-page WB and one-page UC temporary BOs.
   Their releases restore scratch through CT before backing destruction.
   Wait for each temporary node's removal. Unrelated CT-mapped BO destruction
   cannot satisfy that wait. Temporary counters are deltas, excluding hardware
   status BOs allocated earlier.
6. Query runtime again, report the temporary totals and the number of additional
   memirq dispatches since reconnection began. Stop before submission-state
   initialization and propagate the intentional -95.
7. Before devres cleanup, reset both GT consumers and renegotiate their GuC
   interfaces. Clear the **entire managed GGTT range**, including holes and
   retired nodes, with the existing ownership-only clear encoding over MMIO.
   Only after every batch is acknowledged mark the nodes and scratch unmapped.
   The managed range is bounded by Xe's GGTT allocator; it does not extend beyond
   the VF's assigned range. Scratch and BO backing may then be released.

The ordinary Xe scratch PTE encoder, allocation, hole iterator, transport,
interrupt registration and BO destruction are reused. No direct VF GGTT BAR
fallback, PF modification or permanent runtime-power reference is added.
Scratch is pinned and excluded from reclaim while any scratch translations may
remain; an unexpected early backing release or devres finalizer holds before
releasing it. Partial setup or final-clear failure also holds with the relevant
backing retained. Acknowledgment is not independent PTE readback.

## One guest run

Preserve host generation 204, PF `02acd04`, Nix pins and boot entries. Keep
Windows shut down, host VF autoprobe disabled, and VF1 `0000:00:02.1` bound to
`vfio-pci`. Isolate the old device-add rule. Use the established lightweight
Linux VM and VF assignment procedure. Do not bind this experiment to the host
VF or load it into the host PF.

Confirm that the v6 VM is shut down and its assignment released. Check the
current host GPU log and record existing errors. If an older held VM or new or
unresolved host GPU errors remain, report that state before starting; this
experiment does not supply host recovery instructions.

Rebuild Xe and compatibility modules from the exact v7 commit against the
existing exact Linux **7.3.3 guest build tree**, with `KCFLAGS=-g`. Reuse the
local flake/build infrastructure. Record the source commit, SHA-256, vermagic
and srcversion for both modules and retain their unstripped files. No host
kernel replacement, NixOS activation or boot-entry changes are required.

Use the previously selected **host-local** guest serial and host-kernel capture.
Verify capture before explicitly loading Xe with the parameters above. Retain
verbose guest console output. Do not enable automatic VM timeout teardown,
watchdog restart or panic-on-hung-task. Serial capture is sufficient; GDB is
optional, and pausing with a CT/PF response pending can manufacture a timeout.

If any diagnostic hold occurs, retain the running VM and VF assignment. Do not
reset or unbind the VF, terminate QEMU, force-remove Xe, start Windows or bypass
the hold. Save the checkpoint and logs. The hold preserves resources for an
uncertain operation; it is not production recovery. Do not retry automatically.

### Acceptance checkpoints, in order

```text
VFPROBE: diagnostic=mtl-scratch-v7 before VF_CAP ...
... early MMIO maps and memirq initialization returned 0 ...
VFPROBE: native CT handshake and runtime query passed; memirq_dispatches=N
... CT duplicate-PTE requests for holes ...
VFPROBE: scratch holes acknowledged pages=H managed_pages=M pte=...
... ordinary hardware status BO mappings ...
... primary consumer reset and post-reset GuC version handshake acknowledged ...
VFPROBE: post-hwconfig reset complete; before CT reconnection
... memirq and CT registration ...
VFPROBE: post-reset CT handshake and runtime query passed; memirq_dispatches=N
... case=0 pages=1025 and case=1 pages=1 ...
... CT clear before TTM backing release ... scratch=1 ...
... CT BO node removed for each case ...
VFPROBE: CT GGTT experiment passed maps=1026 clears=1026 memirq_dispatches=N
VFPROBE: scratch and CT reconnection experiment passed; post_reset_memirq_dispatches=D; stopping before submission init
... final consumer resets and post-reset GuC handshakes acknowledged on BOTH GTs ...
VFPROBE: entire managed GGTT cleared before scratch backing release pages=M
VFPROBE: all bootstrap GGTT mappings removed before devres cleanup; ct_passed=1
... probe returns intentional -95 ...
GUEST_ALIVE_AFTER_PROBE
VF_GUEST_FINISHED
```

Require the full sequence, `D > 0`, no hold, no suppressed reset/migration,
no allocator/TTM warning and no new host GPU errors. Zero post-reset dispatches
leaves interrupt delivery after reconnection unproven. The temporary totals
must be exactly 1,026/1,026; the cumulative CT map total can be larger because
of hardware status BOs. Scratch fills are duplicate requests (`replicate=0`).
`H` excludes allocated nodes; `M` is the entire managed range and must match
between setup and final-clear markers. Final clearing is MMIO and is summarized
only after every full-range batch has returned its expected count.

A -95 alone is not success: an earlier failure can return the same error.
Do not require v6's six persistent extents; the ordinary initialization path
now allocates additional BOs. No render node or graphics output is expected.

Only after complete cleanup and the guest-alive marker, use the established
approved diskless shutdown mechanism. Verify QMP shutdown before releasing
QEMU, then verify host health, VFIO ownership and no remaining group holder.
Return complete logs, module identities and the checkpoint summary. Perform
one run only.

## Local validation and limits

Xe and compatibility modules build with debug information against local Linux
7.3.4. Rebuild for the exact guest kernel as described above. No hardware was
exercised on the build host.

The bootstrap harness compiles the actual mapping, fill, hole initialization,
consumer-reset, reconnection, teardown and final-clear helpers against scripted
DMA/PF/TTM models. It covers scratch duplication and PAT preservation, allocated
node exclusion, reclaim, early release, partial setup/clear, both-GT reset
ordering, CT reconnection failures and temporary-lifetime accounting. The
existing MMIO and CT protocol suites remain applicable. These tests do not
establish firmware behavior, real TTM concurrency, GPU memory visibility or
engine execution. All 96 local cases pass: 64 bootstrap/lifetime cases, 18 CT
protocol cases and 14 MMIO cases. The bootstrap and CT suites also pass with
AddressSanitizer and UndefinedBehaviorSanitizer.
