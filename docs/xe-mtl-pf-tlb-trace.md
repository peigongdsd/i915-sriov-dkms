# MTL PF invalidation tracing before guest execution

Branch: `codex/xe-mtl-pf-tlb-trace-v1`.
Base: the deployed PF source `02acd0415e056e859159e4825c3119124eee9785`.
This is a separate host diagnostic, not an update to the v7 guest branch.

## Evidence and interpretation

The supplied staged capture from boot
`ab63d596-12dd-4870-9d66-1eb3326534ca` shows:

- A clean selected no-VF window from 23:58:14 on November 14 to 00:03:27
  on November 15, 2026, Asia/Shanghai.
- VF creation at 00:03:45.990372, followed by a clean VF-only snapshot at
  approximately 00:04:54. That is only about 69 seconds of VF-only observation.
- Two VFIO reset cycles at assignment, ending at 00:05:16.899565 and
  00:05:17.011504. Each has PF VF1 FLR notifications on GT0 and GT1.
- A host invalidation timeout at 00:06:05.347077, seqno=4303 recv=4302,
  about 48.34 seconds after the second VFIO reset returned.
- QMP prelaunch with CPUs never resumed and empty guest serial captures.

V7 guest code did not run. A failure in this fresh boot does not require a
Linux VF probe in that boot. Assignment/reset and background host invalidation
handling are candidates, not established causes. The short control windows do
not exclude an intermittent no-VF or VF-only failure. The 48-second interval is
not the invalidation timeout duration: the request issue time is absent.

The original VFIO `reset done` messages do not expose every PF state-machine
transition. Capture the PF's own FLR completion as well.

## Source findings at the deployed PF pin

The additional hook in `pf_enter_vf_flr_wip()` advances a software generation
counter. It does not itself write a PTE or send an invalidation.

The rest of FLR still sanitizes VF resources through
`xe_gt_sriov_pf_config_sanitize()` -> `pf_sanitize_vf_resources()` ->
`pf_sanitize_ggtt()` -> `xe_ggtt_assign()`. In the MTL PF path this rewrites the
VF's GGTT ownership entries and uses MMIO invalidation on both GTs. Those MMIO
writes do not allocate the numbered fence shown in the timeout message. They
could still interact with other traffic; this does not exonerate FLR handling.

The reported error comes from the frontend's pending-fence timeout worker.
Its original log has no GT or request type. The fence timer and existing
`xe_tlb_inval_fence_send` trace start in fence preparation, BEFORE the backend
transport call. Therefore a frontend send record does not prove CT submission.
The deadline also includes a CT processing-delay estimate, rather than being
a universal fixed delay.

Ordinary host request classes share this frontend. The failed seqno cannot be
identified as a VF GGTT request from the journal. Nor does recv=4302 distinguish
hardware delay, firmware completion delay, CT admission/processing delay or
host handling of the completion.

## Instrumentation

This patch changes observability only. It does not change invalidation routing,
timeouts, retry policy, error propagation, MMIO writes, reset ordering or PM
references. New tracepoints are disabled unless explicitly enabled.

- Existing `xe:xe_tlb_inval_fence_{send,recv,signal,timeout}` events gain GT ID.
- `xe:xe_guc_tlb_inval_request` records GT, sequence, action, raw third dword,
  length, and begin/return around the normal CT sender. `result` is meaningful
  at return. A zero return is transport acceptance, not firmware completion.
- `xe:xe_guc_tlb_inval_response` records raw completion payload length and
  sequence before the frontend filters old/special sequence numbers. This can
  expose a completion received after the fence timed out and was removed.
- `xe:xe_sriov_pf_flr` records begin, complete and failed on each GT. Complete
  follows the normal successful PF FLR finish path.
- The existing journal timeout gains GT, fence age in milliseconds and the
  timeout worker's current deadline estimate in milliseconds.

The request's `data2` is raw ABI data. Decode it using the action before treating
it as an invalidation descriptor; the shared sender also carries page-reclaim
requests, whose third dword is an address fragment. Sequence numbers are per GT
and wrap. Correlate using device, GT, sequence and time, never sequence alone.
The existing frontend recv trace is not a raw GuC response: the handler iterates
pending fences and may trace a fence before checking whether it is covered.
Use the new response trace for the actually delivered sequence.

## Preparation and one host-only trial

Prepare this diagnostic as a separate host test generation based on the current
configuration and exact Linux 7.3.3 build tree. Record the exact commit and both
module hashes, vermagic and srcversion. Keep generation 204, its PF pin, boot
entries and the v7 guest artifacts available unchanged. Do not activate or boot
the new host driver until the user coordinates that host change. This diagnostic
requires the host PF module; replacing only the guest module has no effect.

The currently paused QEMU never executed v7 and has no v7-owned mappings to
retain. Preserve logs and confirm prelaunch before normal QMP quit. Capture
VFIO-close/reset activity, verify process exit and group release, and leave the
VF on vfio-pci. Do not separately reset or unbind the PF. If normal exit stalls,
report it without escalating automatically.

After booting the separately selected diagnostic generation:

1. Confirm the loaded diagnostic module identity, Windows off, native VF
   autoprobe disabled, and zero VFs. Confirm all named trace events exist.
2. Use a dedicated tracefs instance, without clearing or changing other tracing
   sessions. Enable the four fence events, both new GuC invalidation events,
   `xe:xe_sriov_pf_flr`, and existing `xe:xe_guc_ctb_h2g` / `xe:xe_guc_ctb_g2h`.
   Stream to a host-local file before changing VF state. Record event formats,
   trace clock, buffer size and per-CPU loss/overrun statistics. Do not enable
   unrelated event groups or per-request printk output.
3. Keep the full host journal capture active. Write stage markers into the trace
   and record matching wall-clock timestamps. Keep host desktop workload as
   similar as practical across stages and record major workload changes.
4. Observe no VF for 15 minutes, then one VF bound to vfio-pci with no QEMU for
   15 minutes, then the established QEMU started with `-S` for up to 15 minutes.
   Record creation, VFIO assignment and both GT FLR traces. These equal windows
   improve comparison; a quiet window is not proof of long-term stability.
5. Stop stage progression at the first new GPU error. Save the timeout context
   immediately and retain capture briefly to observe a late completion, without
   changing VF state. Do not resume guest CPUs or load any guest module in this
   host-only trial, even if all stages are quiet.
6. Save trace loss statistics and journal/QMP state. If a never-resumed QEMU was
   started, exit normally through QMP quit with capture still active, then
   verify process exit, group release and host status. Do not automatically
   repeat the trial. Do not use force termination if normal exit stalls.

This capture uses the user's established host-local destination; it is not
claimed to be independent off-host evidence. Tracing can perturb timing and
absence of an event is inconclusive if capture started late or records were lost.

## Questions the trace should settle

| Observation | Interpretation |
| --- | --- |
| Timeout in no-VF or VF-only stage | QEMU assignment is not necessary in that run. |
| Fence prepared, backend begin missing | Check caller/backend path, blocking and capture completeness. |
| Backend begins, return is delayed beyond the fence deadline | Transport admission/blocking is implicated; do not label it a proven firmware execution timeout. |
| Timely successful return, no raw completion by deadline | Missing/delayed firmware or host-observed completion remains; correlate CT traffic on the same GT. |
| Raw completion after timeout | Completion was observed late; latency still needs attribution. |
| Timely covering raw completion but fence expires | Inspect frontend sequence handling/concurrency, matching GT and trace ordering. |
| PF FLR complete precedes timeout | Attribute the timed-out request independently; it is not automatically the reset's own invalidation. |
| FLR begins without complete/failed | Inspect PF state-machine progression; VFIO reset return alone is insufficient. |

Do not increase the timeout, suppress the error or replace CT invalidation with
MMIO on the basis of the current capture. The purpose is to identify the failing
request and completion path before proposing a behavior change.

## Local validation

The debug Xe and compatibility modules build against local Linux 7.3.4.
Checkpatch and whitespace checks cover the instrumentation and documentation.
The build validates the generated trace-event definitions and call signatures.
No host deployment or hardware test was performed here. This logging-only patch
does not warrant a synthetic protocol test that merely mirrors its log calls.
