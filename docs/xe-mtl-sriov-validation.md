# Validation and deployment boundary

## Hardware evidence inherited from the experiments

| Revision | Environment | Established result | Limit |
| --- | --- | --- | --- |
| `70dd8d6` | Assigned Linux VF | PF-mediated map and restore acknowledged | No graphics execution or independent PTE readback |
| `40e8e63` | Assigned Linux VF | Native memirq/CT, 1,026 mapped and cleared pages, acknowledged cleanup | Deliberate diagnostic stop |
| `c0ca6cb` | Linux 7.3.3 guest | Full probe, four queries, checked store, unload/reload and another store | No guest compositor or sustained workload |
| `c0ca6cb` | Linux 7.3.3 native host VF | Probe, queries, checked stores, VF rebind | Later Vulkan discovery entered the retained-operation failure path |
| `d50cc0c` | Linux 7.3.3 native host VF | Four queries, checked store, 600-frame VF Wayland cube, VF-only unbind/rebind, second checked store and 600-frame VF cube | Nine deadline receive kicks during teardown; no kicks in rendering or rebind |

For the completed v8.2 run: boot `6f9c078d-1716-4b82-91bb-9c567b497ba5`,
Xe srcversion `C82D35713782D96D95034A8`, generation `210-xe-native-v82`.
The full host capture archive SHA-256 is
`f70d2a5b15ec6abe79794e1becf5afe1dc57c6585648b22e72cd038a838758b9`.
All 22 CPUs reported zero trace loss and no new GPU error was recorded.
The first cube mistakenly selected the PF; only the corrected and post-rebind
runs count as VF graphics evidence. Chrome launching is not a controlled GPU
validation result.

## Local software checks

Run from the repository root with a C compiler and Python 3:

```sh
python3 tests/run_xe_mtl_ggtt.py
python3 scripts/test-xe-mtl-vf-ggtt.py
python3 scripts/test-xe-mtl-vf-ct.py
CFLAGS='-fsanitize=address,undefined -fno-sanitize-recover=all' python3 scripts/test-xe-mtl-vf-ggtt.py
CFLAGS='-fsanitize=address,undefined -fno-sanitize-recover=all' python3 scripts/test-xe-mtl-vf-ct.py
```

Local consolidation results: **44 native GGTT/lifetime cases**, **29 CT/relay
cases**, and **four PF suites** passed. The native suites passed both normally
and under ASan/UBSan; the PF harness enables both sanitizers by default.
Checkpatch on the complete code diff with 40 context lines reported zero errors
and warnings (`--no-tree --no-signoff --ignore FILE_PATH_CHANGES`). The additional
context is needed for the existing multiline invalidation macro.

The PF suites compile the actual driver range, GSM-admission, invalidation and
service helpers with captured I/O. The native suites compile the actual mapper,
clear/retention/interface and transport helpers with scripted replies. They
cover fragmented DMA, batch limits, PAT/ownership bits, partial completion,
scratch lifetime, reset-interface restoration and waiter lifetime. They do not
model real kernel locking, interrupts, hardware cache ordering or PF concurrency.

Build the Xe and compatibility modules against the exact target kernel build
tree. This consolidation is locally checked against Linux 7.3.4; the ThinkBookX
is Linux 7.3.3 and needs its own build. Record the source revision, build flags,
SHA-256, srcversion and vermagic. With `KERNEL_BUILD` set to that build directory:

```sh
make -C "$KERNEL_BUILD" M="$PWD" KCFLAGS=-g -j8 drivers/gpu/drm/xe/xe.ko compat/intel_sriov_compat.ko
```

A module hash differs when stripping or signing
changes the bytes; keep those identities separate.

## Evaluation of this candidate

Use `mtl_vf_native=1` and omit the removed bootstrap/relay test parameters.
The probe log identifies `mtl-native-clean-v1`. Keep a known-working boot entry.
On a display host, install the candidate for the next user-coordinated boot;
do not hot-unload the display PF. The current user-authorized normal-profile
installation is pinned to **tested v8.2**, not this newly consolidated source.

Start capture before native VF binding. Verify the actual loaded module and
PCI driver association. Keep the old VFIO device-add rule from racing explicit
Xe binding. Select the VF by PCI identity, and rediscover its render node and
Vulkan index after rebind.

For the setup used in the successful run, disabling Mesa's implicit device
selection (`NODEVICE_SELECT=1`) consistently for both device enumeration and
`vkcube` corrected the mismatched ordering. Do not hardcode index 1 for another
machine or assume opening a VF descriptor proves rendering on it. Check DRM
fdinfo and VF CT/relay activity. VF engine cycle counters are absent in this
Xe path, so do not require those counters as the only selection evidence.

Exercise normal probe, four IGT queries (`query-engines`, `query-gt-list`,
`query-config`, `query-mem-usage`), checked system-memory `basic-store`, and
VF-selected Wayland rendering. With clients closed, perform one normal VF-only
unbind/rebind and repeat store/render. Retain the display PF throughout.
Classify completion as unassisted, receive-kick-assisted, or retained failure.

Optional trace events are `xe_guc_ct_rx`, `xe_memirq_rx`, `xe_guc_relay_rx`,
`xe_guc_ctb_h2g` and `xe_guc_ctb_g2h`. Use a cross-CPU comparable clock such as
`mono`, record per-CPU loss counters and retain full journals. Dynamic debug in
`xe_ggtt.c` and `xe_gt_sriov_vf.c` provides detailed mappings without continuous
normal-level per-batch printing.

A retained failure does not authorize freeing its backing. Preserve its state
and logs before recovery; do not run an automatic reset/unbind loop. The release
blocker is documented in [readiness](xe-mtl-sriov-readiness.md).
