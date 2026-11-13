# MTL VF memory-interrupt validation plan

Status: **not run**. Xe's `GRAPHICS_VERx100 >= 1250` predicate selects the
memory-based interrupt path for MTL; it does not verify that the path works
with the target's GuC, PF provisioning and VF GGTT mappings.

The rewritten branch deliberately rejects native MTL/ARL VFs and cannot run
this test. The pinned `e9130af` baseline can hang before reaching interrupt
initialization. Removing the gate alone is not a valid interrupt test: the
GGTT mapping problem must first be resolved or localized with separate
diagnostics. A hang before report-page setup leaves IRQ support **unknown**.

## Preparation

Keep the normal Nix configuration and Xe pin unchanged. Use a separately
identified diagnostic build only for a deliberate reproduction. Record the
kernel, driver commit, PCI ID, graphics/media IP versions, both GuC firmware
versions and IRQ mode. Keep VF autoprobe disabled and ensure the old VFIO
device-add rule cannot race with the intended native bind.

Before binding, prove that the off-host receiver captures a test message
from this boot. Use serial or a previously verified netconsole path, and
keep the captured build identity with the log. A local journal or local
trace buffer is insufficient for a machine hang. No binding is automated by
these notes.

## Smallest useful observations

Prefer existing debug infrastructure. `CONFIG_DRM_XE_DEBUG_MEMIRQ` enables
report-page/source/status diagnostics in `xe_memirq.c`; the applicable DRM
debug logging must also be enabled. Keep the capture brief because this can
log on every interrupt. Add bounded setup checkpoints only where existing
messages do not establish success:

| Stage | Observation | What it establishes |
| --- | --- | --- |
| Selection | VF identity, reported IP version, `xe_device_uses_memirq()` result and installed IRQ handler. | Which path the driver selected, not hardware support. |
| Allocation | Return from `xe_memirq_init()`, GGTT offset/size and report-page enable state. | The driver allocated/enabled its pages, not that the GPU can access them. |
| GuC setup | Return values of both `xe_guc_self_cfg64()` calls in `xe_memirq_init_guc()`, separately for primary and media GuC. | Whether firmware accepted source/status addresses. Acceptance alone is not delivery. |
| CT setup | Return from `xe_guc_ct_enable()` after report-page registration. | Communication setup progressed; still not proof of an IRQ. |
| Delivery | Entry into `vf_mem_irq_handler`, a consumed GuC source entry in `xe_memirq_handler`, and dispatch to the corresponding GuC. | An interrupt reached the VF and a report-page source was observed. |
| Useful completion | Correlate a normal G2H response with `xe_guc_ctb_g2h` and completion of the operation that expected it. | Delivery reaches the CT consumer rather than merely incrementing an IRQ count. |
| Engine | Submit a minimal normal Xe workload on a provisioned engine and correlate its report-page source, engine IRQ dispatch and completed fence. Repeat for a media engine if provisioned. | The tested engine path works; render success alone does not validate media. |

Use an ordinary expected GuC response, not a synthetic write to interrupt
registers or report pages. Preserve the exact response/action identity in
the capture. Existing CT tracepoints help correlation, but they must be
streamed off-host if they are needed to diagnose a hang.

`memirq_dispatch_guc()` and `memirq_dispatch_engine()` deliberately assume
the normal status interrupt bit when dispatching; debug mode can print an
`ASSUME` message when it is absent. Therefore absence of that status bit is
not, by itself, failure. The source entry, actual IRQ context, subsequent
dispatch and completed operation are the useful combined evidence. Do not
add a second reader which consumes/clears source bytes and steals events
from the existing handler.

## Interpretation

- Setup rejected by GuC: inspect returned error, ABI/firmware version and
  addresses before concluding the hardware lacks memory-based interrupts.
- No IRQ and no source observation: could be incorrect GGTT mapping,
  unstarted GuC, masking, transport failure or absent interrupt support.
  This result alone does not distinguish them.
- IRQ entry without the expected source: check source layout, primary/media
  offsets and the triggering event. `/proc/interrupts` alone is not proof.
- Source and dispatch without completion: investigate CT/engine handling
  and response identity; do not immediately replace the IRQ backend.
- One successful response and workload establish only the tested delivery
  paths on that firmware. Reset recovery, suspend, migration and sustained
  workloads require separate evidence.

After one captured failure, stop and inspect the last completed stage before
another deliberate bind. No permanent polling loop, new legacy interrupt
backend or power-management restriction is justified by the current evidence.
