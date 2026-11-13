# Guest-only MTL VF probe diagnostic

This describes the historical v1 test at `b7cefff`. On the v2 branch use
[the BO-mapping-stop plan](xe-mtl-vf-map-stop.md); its stop boundary and
diagnostic identity differ.

Branch: `codex/xe-mtl-vf-probe-stop-v1`.
Base: `e9130affe933dfc45309dc7a82599a1d7a38517e`.
Diagnostic identity in the kernel log: `diagnostic=mtl-stop-v1`.

This is a temporary experiment, not a native VF enablement series. It keeps
the original discovery requests and retry behavior, adds checkpoint logs,
and deliberately returns `-EOPNOTSUPP` after GGTT range discovery and
validation, before GGTT setup. It does not include the earlier rejection
from `02acd04` or the working PF branch's other changes.

## Test boundary

Keep the working host PF and its Nix generation unchanged. Replace only the
disposable Linux guest's out-of-tree Xe package, using its existing kernel
and flake inputs. Do not install this diagnostic on the host or change host
boot entries, VF autoprobe policy, or the working Windows guest.

The earlier Linux guest using `02acd04` returned `-95` at the device-level
guard. That tested clean early rejection, not this later discovery path.
The Windows Intel driver's successful graphics operation is useful PF/VFIO
evidence, but does not validate native Xe VF initialization.

PCI passthrough still uses the physical GPU. A guest hang can affect the
host; a host-local serial file alone is not sufficient capture. Stream guest
serial and host kernel logs to an independent machine, and verify reception
before loading the diagnostic. If no independent receiver is available,
prepare the build and stop before attaching/probing the VF.

## Build with the existing guest kernel

Prefer overriding the source of the existing guest-only driver derivation.
Pin the exact diagnostic commit, retain that derivation's kernel, patches,
dependencies and compiler settings, and avoid a flake-input update. Ensure
no inherited patch reinstates the early MTL VF rejection. Reuse the existing
VM and its storage; no new kernel configuration or full system activation
on the host is required.

For a direct build in the same kernel build environment:

```sh
make -C "$GUEST_KERNEL_BUILD" M="$PWD" -j"$JOBS" \
  drivers/gpu/drm/xe/xe.ko compat/intel_sriov_compat.ko
```

`GUEST_KERNEL_BUILD` must be the prepared build tree for the exact guest
kernel, including configuration, generated headers and symbol versions.
The matching version string alone is insufficient when configurations or
symbol versions differ. Do not force-load mismatched modules. Preserve the
existing module-signing/trust arrangement if the guest enforces it.

Package Xe and the matching compatibility module through the guest's
existing module mechanism, retaining ordinary dependencies. Check both the
guest root and initrd for an older Xe module that could load first. Make
loading deliberate after serial capture starts; prevent i915 or another
driver from claiming the guest VF first.

Before the probe, record the source commit, guest kernel release/build,
module path, SHA-256, vermagic and srcversion where available. Check
`modinfo -n xe` and the actual loader resolution. The baseline module version
string is unchanged, so it is not a sufficient identity check. The live
`diagnostic=mtl-stop-v1` marker is required to establish that this build ran.

## One controlled run

1. Confirm the Windows VM is stopped and has released VF1. If it is running,
   stop before the test and request a downtime decision; do not forcibly
   reclaim its device. Keep VF1 bound to host `vfio-pci`. Do not bind it to
   host Xe. Isolate any old device-add rule that could race with the intended
   setup, using a temporary arrangement rather than changing the normal host
   configuration.
2. Verify independent receipt of both guest serial and host log test markers.
   Record the host PF driver identity, boot ID and VF assignment. Start the
   existing lightweight guest with only VF1 assigned.
3. Record guest `uname -r`, PCI IDs/BDF and driver ownership. The guest BDF
   need not match the host's `0000:00:02.1`. Verify the diagnostic module
   provenance, then explicitly load/probe it once. Do not start a graphics
   workload or remove the stop guard.
4. Capture all `VFPROBE` lines, the final PCI probe result, warnings/oopses and
   host logs. After probe returns, emit a guest-alive marker, inspect the VF
   driver link and shut down normally if responsive. `modprobe` can return
   success even when an individual device's probe failed; use the PCI probe
   log and device state, not its exit status alone.
5. Verify host responsiveness and that VF1 remains bound to `vfio-pci` after
   guest shutdown. Do not automatically restart Windows or repeat a failed
   probe. Return the logs and last completed checkpoint for review.

Expected progress includes:

```text
VFPROBE: diagnostic=mtl-stop-v1 before VF_CAP pci_vf=...
VFPROBE: VF_CAP=...
VFPROBE: before reset
VFPROBE: reset returned 0
VFPROBE: before version handshake
VFPROBE: handshake returned 0
VFPROBE: before GMD_ID query
VFPROBE: GMD_ID query returned ...
VFPROBE: before VF config query
VFPROBE: before GGTT start query
VFPROBE: GGTT start query returned 0
VFPROBE: before GGTT size query
VFPROBE: GGTT size query returned 0
VFPROBE: GGTT base=... size=...
VFPROBE: VF config query returned 0
VFPROBE: stop before GGTT setup, base=... size=...
... probe with driver xe failed with error -95
```

Primary/media GT logs and early IP discovery can repeat reset/handshake
messages. An assigned guest may report `pci_vf=0`; existing `VF_CAP_REG`
detection is authoritative for this test. No render node is expected from
the failed VF probe.

The successful diagnostic outcome is the final stop marker, clean probe
failure, continued guest/host responsiveness and normal guest shutdown.
That narrows the search to later initialization for this PF/guest pairing.
It does not prove the suspected BAR PTE write caused the original host-side
hang, nor does it test CT operation, memory interrupts or GPU execution.
If it stops earlier, report the last entry/completion pair and do not
automatically retry or remove the guard.

## Local validation

The diagnostic modules are built against the available Linux 7.3.4 prepared
headers on the development host; the exact guest-kernel build is a separate
required check. No module was installed or loaded and no VF bind was run
as part of preparing this branch. Driver diff style and whitespace checks
are also performed. Build success is not hardware validation.
