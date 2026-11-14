# MTL Media-GT shared-memory coherency backport

Branch: `codex/xe-mtl-pf-media-coherency-v1`.
Trace baseline: `f4fd5f286c5bca41dd4ca29cf590eaa50d5f23c0`.
Underlying PF baseline: `02acd0415e056e859159e4825c3119124eee9785`.

This branch adds the allocation workaround from Tales A. Mendonça's posted
[v6 patch 3/3](https://lore.kernel.org/intel-xe/20260922144634.55130-4-talesam@gmail.com/).
The code commit preserves its author and original review/test trailers. Those
trailers describe the original patch, not a new ThinkBookX hardware test. The
backport preserves its code changes, with context offsets adjusted. The prior
trace commits remain separate; the allocation fix also applies independently
to the underlying PF baseline.

## Evidence and hypothesis

Trial 206 used the trace baseline and recorded a GT1 invalidation timeout for
sequence 9227, with age 2265 ms and deadline 2250 ms. Its CT sender returned
success and a raw completion was subsequently recorded. All sampled trace loss
counters were zero. Both no-VF and VF-only windows were quiet; the paused window
was shortened to 7 minutes 17 seconds at the user's request. A first v5.1 guest
then completed its diagnostic cleanup. The timeout occurred after a fresh guest
started but before its probe. This is not a clean no-prior-guest-probe control.

Action 0x7000, data2 0x80000001, length 7 identifies a host ASID-based PPGTT
range invalidation. It does not identify a VF GGTT relay update. The next send
sampled an H2G descriptor head immediately before the timed-out request's slot.
That sample could reflect stale CPU data; it does not prove GuC non-consumption.
The trace used the per-CPU `local` clock, so exact cross-CPU latencies are limited.

The published workaround addresses stale CPU reads of memory written by the
standalone Media 13.0 GT's GuC. It is a specific candidate for the observed PF
failure. It has not yet been validated on this ThinkBookX and does not establish
the cause of the original native VF direct-GGTT probe hang.

## Scope and source audit

- The existing `MEDIA_VERSION(1300)` OOB rule matches the media GT on MTL/ARL,
  not the primary GT. It does not add a graphics-IP whitelist or reject 1271.
- `xe_gt_init_early()` processes GT OOB rules before `xe_uc_init_noalloc()` and
  before the later allocating `xe_uc_init()` / `xe_guc_init()` paths. The new
  helper can therefore query the active workaround at all affected call sites.
- The helper supplies `XE_BO_FLAG_NEEDS_UC` to seven allocation sites: H2G CTB,
  G2H CTB, ADS, log, SLPC data, engine activity metadata and activity data.
- Existing TTM creation selects CPU UC for this flag. Existing GGTT insertion
  and restoration select `XE_CACHE_NONE` and the platform's corresponding PAT
  index. No new PTE encoding or invalidation backend is introduced.
- CPU UC is intentionally stricter than i915's CPU WC plus GPU UC mapping.
  Replacing this flag with `FORCE_WC` alone would leave the GGTT cache policy WB.
  This backport retains the reviewed policy instead of adding another BO flag.
- The separate ADS UM queue already requests `NEEDS_UC`; ADS post-hwconfig
  initialization retains the original BO. CT relocation to VRAM is dGPU-only.
- Memory-based interrupt storage already requests `NEEDS_UC`. MTL supports
  memory-based VF interrupts; this coherency issue and VF GGTT restrictions
  must not be described as a lack of memory-based interrupts.
- This fix does not expand LRC/ring coverage or enable native VF probing. The
  published v6 discussion leaves LRC changes outside this patch. Future media
  VF bring-up still needs its own allocation and lifecycle audit.

The workaround runs at allocation time and uses normal Xe mappings thereafter.
It adds no periodic worker, re-notify loop, forced-awake lifetime, or per-request
cache flush. Uncached accesses can have a cost; no performance or power
measurement on this ThinkBookX is claimed. Broadly uncaching other BOs would
exceed the reviewed scope.

## Prepare the host candidate

1. Preserve generations 204 and 206, their existing entries, the current boot
   default, the original Nix pin/configuration, and all v5.1/v7 guest artifacts.
   This is a host PF change; changing only the guest module cannot test it.
2. Before any later host boot, preserve the current fresh VM's evidence and
   verify its identity and serial state. It was reported at the probe prompt
   without a probe. For that state, perform normal QMP quit with host logging
   active, then verify process exit and VFIO group release. If a probe has since
   run, evaluate its actual cleanup state first. Do not force termination if
   normal exit stalls, or separately reset/unbind the PF.
3. Build Xe and compatibility modules from the exact delivered branch commit
   against the existing host Linux 7.3.3 build tree with `KCFLAGS=-g`. Record
   source identity, SHA-256, srcversion, vermagic and debug-section presence.
   Record stripped initrd identities separately if the packaging strips them.
4. Prepare a separately named, signed diagnostic boot entry using the installed
   Lanzaboote workflow. Record any rebuilt kernel image/certificate differences.
   Keep the existing entries and default. Coordinate the reboot with the user;
   preparation is not authorization for automatic activation or reboot.

## One comparison run after the coordinated boot

Use the capture mechanics in `xe-mtl-pf-tlb-trace.md`, with the refinements below.
The purpose is a host regression comparison; this is not a full VF acceptance run.

1. Verify the loaded candidate module identity, Windows off, disabled native VF
   autoprobe and zero VFs. Read each GT's existing `workarounds` debugfs file:
   22016122933 must appear for GT1 and not GT0 on this machine. Resolve the actual
   DRM/GT paths instead of assuming card numbering. This verifies rule selection,
   not an independent readback of every CPU mapping or PTE.
2. Create a dedicated trace instance. Select `mono` (or `global` if unavailable)
   before enabling events, and record the selected clock. Capture the same nine
   events, their formats, buffer size, start/end and error-time loss statistics,
   full journal and stage markers. Start host-local streaming before VF changes.
3. Observe 15 minutes with no VF, 15 minutes with VF1 on vfio-pci and no QEMU,
   then 15 minutes with the established guest assigned but CPUs paused (`-S`).
   Keep workload similar and record deviations. A shortened window must be
   reported as such, not counted as the full stage.
4. If these stages are clean, reproduce the additional trial-206 sequence once:
   resume the existing v5.1 diskless guest and run its established bootstrap
   diagnostic from 292dec2bfa0d121df72012cb43f14c437edf5146. Preserve the exact guest
   module hashes/configuration where available. Require native CT/runtime-query
   success, both GT consumer-reset and version acknowledgements, six mapping
   clears, expected -95 and guest-alive marker before normal QMP exit. Capture
   release and verify no group holder remains.
5. Start one fresh instance of that same guest, boot to its probe prompt, and
   leave the probe unsent. Observe for 15 minutes while capturing host activity.
   This reproduces the state in which trial 206 failed. Do not substitute v7 or
   add graphics workloads to this comparison.
6. At the first new GPU error, stop stage progression and save context promptly;
   continue capture briefly for late completions. Distinguish informational
   provisioning messages from actual failures. If a guest diagnostic is active
   or held, retain assignment until its cleanup is established. A fresh instance
   that never probed can exit normally via QMP with capture active. Never escalate
   a stalled normal exit to force termination automatically.
7. After a clean run, normally exit the fresh guest with capture still active,
   verify process/group release, observe host logs for a further 15 minutes,
   then save final trace statistics and identities. Do not retry automatically.

A clean run supports this candidate under the recorded workload; it does not
prove long-term absence of a rare failure. Report request/response counts by GT,
late completions, timeout/error counts, FLR completion and capture loss. If a
similar error persists, keep the evidence and reassess coherency/transport; do
not increase the timeout or add periodic notifications to hide it.

## Local validation boundary

The allocation changes are checked against the posted v6 patch and the local
rule, BO, GGTT and initialization paths. Build and style results accompany the
delivered commit. Local builds use Linux 7.3.4; the testing agent must rebuild for
host 7.3.3. No host activation, hardware trial, graphics workload, or performance
measurement is part of this backport preparation.
