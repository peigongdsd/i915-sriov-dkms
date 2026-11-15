# Meteor Lake native VF: v8 result and v8.1 unload fix

## Observed result

The supplied v8 capture used guest source
`7b67c2f436d8118ef2d3b96686237955cdbd8d6c`, Linux 7.3.3, on the ThinkBookX
Meteor Lake system. Host generation 207 used PF source
`b0aa9a833dbabdf260da7c6364be7aea03693d40`, srcversion
`C382211885F88F26CBE709C`, boot ID
`f611422e-1e50-423b-b80f-87b4defe1930`. Windows was off. The host VF remained
on vfio-pci and appeared at `0000:01:00.0` in the guest.

The first VM exited after an init-script failure before module loading. The
corrected VM performed one native probe, using `mtl_vf_native=1` with both old
diagnostic options off. It reached:

- Native probe return 0, DRM registration, renderD128 and normal PM setup.
- GT0 and GT1 initialization, with 1050 and 15 memirq dispatches at their
  respective checkpoints.
- Ten initialization jobs across rcs0, bcs0, ccs0, vcs0 and vecs0, each with
  positive waits and fence status 1.
- IGT 2.6 query-engines, query-gt-list, query-config and query-mem-usage success.
- IGT `xe_exec_store basic-store` success on system memory, including checking
  the value written by the GPU.

During normal unload, several CT clears were acknowledged. The next reported
failure was:

```
GuC mmio request 0xf015005: failure 0xa hint 0x0
VFPROBE: bootstrap handshake failed (-6); holding probe and BO; keep VM and VF assigned
```

The later hung-task stack places the blocked rmmod in
`xe_gt_sriov_vf_bootstrap_update()` through `vf_bootstrap_unmap_node()`,
`xe_ggtt_vf_bootstrap_unmap_bo()`, `xe_ttm_bo_delete_mem_notify()`,
`ttm_bo_release()` and `devres_release_all()`. There was no unload return,
reload, second store or shutdown. The stack is evidence of late BO destruction;
it does not identify the particular BO or the last reset that preceded it.

QMP last reported the VM running. The host monitor flagged no new GPU error;
two GuC relay rate-limit messages were present. These captures do not establish
host stability under other workloads. No GDB session or independent PTE readback
was performed. This analysis and patch preparation did not operate the held VM.

## Source diagnosis

The action is VF2GUC MMIO relay (`0x5005`), carrying the PF handshake opcode.
`0xa` is `XE_GUC_RESPONSE_INVALID_STATE`; the MMIO helper returns `-ENXIO`
(`-6`). The rejected message is the handshake before the GGTT update. It is
not evidence that this particular clear was submitted to or applied by the PF.
Previously mapped backing still requires a successful clear before release.

V8 invalidates the cached PF relay handshake in `vf_reset_guc_state()`, but
its late MMIO path then negotiates only the PF interface. The normal
`vf_guc_fini_hw()` devres action resets the GuC VF state without performing
another version handshake. BOs allocated earlier can be released afterwards.
Normal submission teardown also calls `xe_guc_softreset()`; v8 did not
invalidate the relay cache at that second reset entry point.

The missing GuC interface restoration matches the captured INVALID_STATE.
V5.1 already used the existing `vf_handshake_with_guc()` after its diagnostic
reset. V8.1 applies that prerequisite lazily at the native MMIO boundary,
without importing the diagnostic reset-and-clear sequence into normal unload.
Hardware validation is still needed to establish that this resolves the
observed unload and that no later cleanup failure remains.

## V8.1 implementation

When native MMIO GGTT updates need a fresh relay connection, first call
`vf_handshake_with_guc()`, then perform the existing PF handshake and update.
The existing helper requires the previously negotiated GuC interface version.
Client soft reset invalidates the cached native relay state before issuing its
ordinary request, as VF reset already does. The first MMIO use establishes both
interfaces; following batches reuse them. This also makes the early MMIO
connection explicitly establish the prerequisite, even when bootstrap has
already negotiated the GuC version.

CT updates take their existing branch before this negotiation, so steady-state
submission gains no handshake. No reset, PTE retry, new teardown sequence,
timeout extension or scheduler/PM replacement is added. Reset results and the
late GuC restoration receive diagnostic messages for the next capture.

The software tests compile the actual update, version-negotiation, unmap and
client-soft-reset functions against simulated firmware replies. They reproduce
the old handshake rejection and check restoration order, cached reuse, version
mismatch, failed negotiation and unchanged reset returns. They cannot validate
firmware reset timing, interrupt delivery or kernel devres concurrency.

Local validation passed 80 bootstrap/lifetime, 18 CT and 14 relay cases.
The 80 bootstrap/lifetime cases also passed ASan and UBSan. Both modules built
with debug information against the available Linux 7.3.4 build tree. This is
build validation only; the next guest run must rebuild against its exact 7.3.3
tree. No v8.1 module was loaded on hardware during this preparation.

The inherited indefinite hold on unresolved mapping ownership is still an
experimental limitation. This patch fixes the demonstrated missing transition;
it does not complete production reset/error recovery or claim upstream readiness.

## Next run

Follow `xe-mtl-vf-native-test.md` after separately arranging recovery of the held
v8 VM. Keep the host PF unchanged and build v8.1 against the exact guest kernel.
Repeat full probe, queries and basic-store; then require normal unload return,
one reload, another checked store and guest shutdown. Preserve complete serial
and host logs. The same native implementation remains the target for later
host VF testing.
