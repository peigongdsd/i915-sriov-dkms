# Guest-only MTL VF BO mapping diagnostic, v2

Branch: `codex/xe-mtl-vf-map-stop-v2`, based on v1 commit
`b7cefff4539649ce00ac7dce0397e54d50701885` and ultimately `e9130af`.
Live identity: `diagnostic=mtl-map-stop-v2`.

This is temporary diagnostic code, not native VF enablement. It removes
v1's stop before early GGTT setup and rejects MTL-family VF BO insertion
instead. It does not deliberately execute a GGTT PTE write.

## Evidence motivating this boundary

The downstream report says that v1, built for the exact Linux 7.3.3 guest,
completed VF capability detection, both GTs' GuC reset/version handshake,
GMD_ID queries and configuration queries. Both GTs reported GGTT base
`0x7ec00000`, size `0x80000000`; the end is `0xfec00000`, below
`GUC_GGTT_TOP` (`0xfee00000`). The guest reached the stop, returned `-95`,
printed an alive marker and shut down normally. The host remained responsive
with VF1 bound to `vfio-pci`. The second run used GDB and captured the earlier
info-level checkpoints missing from the first run.

Those are downstream-reported observations; the raw host/guest logs were
not independently inspected here. The captures were host-local. They do
not prove working PTE access, interrupts, CT communication or graphics.
The reported working PF is still generation 204 at `02acd04`, not the
later PF branch tip. Preserve that tested host configuration.

## What v2 changes

- Early GGTT initialization now runs normally. A checkpoint records its
  successful return before later device initialization.
- `xe_tile_init()` logs entry/return around memory-interrupt initialization.
- `xe_ggtt_vf_probe_stop()` logs the BO size, flags and GGTT range and calls
  `dump_stack()`. It is deliberately not inlined to provide a GDB breakpoint.
- Both `__xe_ggtt_insert_bo_at()` and `xe_ggtt_insert_node_transform()` reject
  MTL-family VF requests before node allocation or PTE population. The normal
  BO path also stops before its `xe_bo_validate()` call.
- Existing error paths handle the failed allocation. No BO GGTT node is
  installed by the rejected request. Normal cleanup must still be verified
  on hardware; this is not a blanket guarantee about earlier initialization.

The expected first caller is the memory-interrupt report buffer allocation:

```text
xe_tile_init
  xe_memirq_init
    memirq_alloc_pages
      xe_managed_bo_create_pin_map / BO creation
        __xe_ggtt_insert_bo_at
          xe_ggtt_vf_probe_stop
```

Confirm this from the trace rather than assuming it. The buffer needs a GGTT
mapping before interrupts can operate. An expected failure while allocating
it is not evidence that the platform lacks memory-based interrupts. The
guard rejects requests, rather than silently skipping writes and reporting
success with an unusable mapping.

## Build and module identity

Reuse the existing lightweight guest, its exact kernel and flake inputs.
Override only the guest's driver package source at the supplied v2 commit.
Do not install this on the host, change host pins/boot entries or rebuild a
different guest kernel. Ensure the guest initrd cannot load the older module.

Retain the existing build flags and add `-g` to the module's compiler flags
if full debug information is absent. A direct build can use:

```sh
make -C "$GUEST_KERNEL_BUILD" M="$PWD" KCFLAGS=-g -j"$JOBS" \
  drivers/gpu/drm/xe/xe.ko compat/intel_sriov_compat.ko
```

If `KCFLAGS` is already set, append `-g` rather than discarding required
flags. Keep the unstripped `xe.ko` for GDB even if the guest package strips
its installed copy. Verify `.debug_info` and `.debug_line` with `readelf`.
The companion compatibility module must match this source/kernel build.
Do not override version checks to force-load modules.

Record the source SHA, kernel identity, module paths, hashes, vermagic and
srcversion. The live v2 identity is required; unchanged package version
strings are insufficient.

## One test, preserving the working host

1. Use VF1 only after the Windows VM has released it; do not forcibly take
   an active guest's device. Keep the host VF bound to `vfio-pci` and the PF
   on the working generation-204 driver. Verify current state rather than
   assuming the earlier report is still current.
2. Stream both guest serial and host kernel logs to an independent receiver
   and verify a test marker. The earlier host-local captures survived, but
   cannot be relied upon for a host-wide hang. If the receiver is unavailable,
   prepare the build and report the blocker before hardware testing.
3. Capture info messages with guest `loglevel=7` or equivalent, avoiding the
   threshold-6 issue from v1. Keep loading deliberate and identify the guest
   BDF dynamically. Isolate any driver-binding rule that races with the test.
4. Optionally reuse the QEMU GDB setup and `nokaslr`. Load the new unstripped
   module symbols at this run's actual section addresses; do not reuse the
   old module text base. Break at `xe_ggtt_vf_probe_stop`, collect the stack
   and available BO fields, then continue normally through its error return.
   Do not jump over the guard, change its result or step into a PTE write.
5. Probe once, without a graphics workload. Capture the stop and its printed
   stack, the final PCI probe error, and any other warnings. `dump_stack()`
   is intentional diagnostic output, not itself an oops. An allocation error
   mentioning the memory-interrupt buffer is expected if that is the caller.
6. Emit `GUEST_ALIVE_AFTER_PROBE`, inspect driver ownership, and shut down
   normally if responsive. Verify host health and VF1's `vfio-pci` binding.
   Do not repeat a failing probe or automatically restart Windows.

Expected distinguishing messages are:

```text
VFPROBE: diagnostic=mtl-map-stop-v2 before VF_CAP ...
... existing VF discovery checkpoints ...
VFPROBE: early GGTT setup completed
VFPROBE: before memirq initialization
VFPROBE: stop before GGTT BO insertion, size=... flags=... base=... range=...
... diagnostic stack trace ...
VFPROBE: memirq initialization returned -95
... probe with driver xe failed with error -95
GUEST_ALIVE_AFTER_PROBE
```

Do not equate `modprobe` exit status with a device's probe result. Success
for this experiment means the mapping stop, expected error, responsive
guest/host and completed shutdown. A different caller is useful evidence;
an earlier hang should be localized by the last checkpoint and GDB stack.
Neither outcome alone proves the original failing instruction.

Return all logs, module identity, caller/BO fields, the last completed
checkpoint and cleanup/host-health results. Further PTE access or forwarding
work requires a separate decision; this branch does not implement it.

## Development validation

Xe and the compatibility module built successfully against the available
Linux 7.3.4 prepared headers with `KCFLAGS=-g`. The unstripped Xe module
contains `.debug_info`, `.debug_line` and the `xe_ggtt_vf_probe_stop` symbol.
Driver patch style and whitespace checks passed. Inspection confirmed both
guards precede validation/node allocation. These checks do not replace the exact
Linux 7.3.3 guest build or any hardware test. No local module load, bind or
host configuration change is part of preparing this branch.
