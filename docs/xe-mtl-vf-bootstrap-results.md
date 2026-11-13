# Meteor Lake native Xe VF: v5.1 evidence

## Result and provenance

The supplied complete captures show **one successful bounded bootstrap and
cleanup run**, followed by the intentional probe return `-EOPNOTSUPP` (`-95`).
This is evidence for functional early GGTT mappings, primary-GT CT
communication and memory-interrupt handler dispatch on this setup. It is
not a completed native VF driver or a graphics workload result.

Test: ThinkBookX, Core Ultra 9 185H, PCI `8086:7d55`, graphics/media IP
1271/1300, Linux 7.3.3. PF `0000:00:02.0`; assigned VF1 appears as
`0000:01:00.0` in the guest. Host generation 204 used PF source
`02acd0415e056e859159e4825c3119124eee9785`, loaded srcversion
`564B3B0809364ADBC743936` according to the submitted provenance.

Guest source:
[`292dec2bfa0d121df72012cb43f14c437edf5146`](https://github.com/peigongdsd/i915-sriov-dkms/tree/292dec2bfa0d121df72012cb43f14c437edf5146).
Both modules were built against the existing exact 7.3.3 tree with
`KCFLAGS=-g`, version `2026.11.05-sriov` and vermagic
`7.3.3 SMP preempt mod_unload`.

| Module | Srcversion | SHA-256 |
| --- | --- | --- |
| Xe | `22C56E7D7BA771C509E776B` | `4112562e67c47fc96f8d7dd9a4630f8b651281cf744a02e1217c71c378551436` |
| Compatibility | `812CC749D9FBDC293CE9E09` | `3388afcef0b19297ab04b3ccbfbe89d88479b9edc93481bc6a361d8c9fe75680` |

The submitted text bundle is 6,073,752 bytes with SHA-256
`0489283f38f891402ea549370eb5b971ed44112a34f03c48f7c424654204f924`.
This review inspected its complete guest serial, QMP and host-journal
sections, rather than relying only on the summary. Module identities and
build provenance are recorded outputs in the submission; the binaries
were not independently supplied or rehashed here.

All capture was host-local, with no GDB session. QEMU and socket serial
captures agree from `VF_GUEST_BEGIN` through guest power-down after text
section boundary normalization. These are two captures of one serial
stream, not independent observations of hardware state. Raw logs remain
private because they include unrelated machine identifiers and host data.

## Observed sequence

The live marker was `diagnostic=mtl-bootstrap-v5.1`. At guest time
20.320638 s, memirq initialization returned zero. The following extents
were acknowledged; each has a matching clear acknowledgement:

| VF-relative GGTT offset | Pages (4 KiB) | Map requests | Clear observed |
| --- | ---: | ---: | --- |
| `0x0` | 1 | 1 | Yes |
| `0x1000` | 256 | 1 | Yes |
| `0x101000` | 256 | 1 | Yes |
| `0x201000` | 2 | 1 | Yes |
| `0x203000` | 33 | 2 | Yes |
| `0x224000` | 1 | 1 | Yes |
| **Total** | **549** | **7** | **6 extents** |

At 20.331459 s, the primary-GT native CT handshake and runtime query
passed with `memirq_dispatches=4`. The counter establishes that the
instrumented memory-interrupt dispatch path ran; it does not identify
every interrupt's source or validate every GT/engine interrupt class.

GT0 and GT1 each acknowledged the consumer reset, then the post-reset
GuC version handshake. After the PF MMIO relay handshake was renewed,
all six mapping clears were acknowledged. At 20.338862 s, the final
marker reported all bootstrap mappings removed before devres cleanup,
with `ct_passed=1`.

The next probe result was the intended `-95`, followed by
`GUEST_ALIVE_AFTER_PROBE` and `VF_GUEST_FINISHED`. No diagnostic hold,
unexpected-reset marker, call trace or TTM cleanup warning appeared in
the inspected test interval. The post-probe interrupt snapshot was taken
after cleanup and cannot reconstruct the freed VF interrupt state.

The diskless guest was powered down using its SysRq console command,
explicitly authorized by the owner. Serial recorded `Power down`; QMP
reported guest shutdown before the host sent QEMU quit. The submission
also records QEMU exit, no remaining VFIO group-19 file-descriptor holder,
VF1 still bound to `vfio-pci`, a responsive host and Windows shut down.
This review did not access the live machine to recheck that final state.

## Why v5.1 differs from v5

The earlier v5 reached its cleanup hold after acknowledged consumer resets:
the next PF MMIO relay handshake received GuC `INVALID_STATE` (`0x0a`).
It had not re-established the GuC interface version after resetting the
consumer. GuC `MATCH_VERSION` and the PF relay ABI handshake are different
protocol steps; repeating only the latter was insufficient.

The v5.1 change
[`b0621434e5cd`](https://github.com/peigongdsd/i915-sriov-dkms/commit/b0621434e5cd9c4514cf9ce5eb16f07baa49a87d)
reuses `vf_handshake_with_guc()` after each acknowledged reset and keeps
CT disabled while clearing through MMIO. It retains Xe's interface-version
consistency checks. The new captured success supports this fix for the
tested cleanup sequence. It does not establish that a consumer reset drains
an uncertain PF GGTT request: this sequence starts with all maps acknowledged.

## Host timeouts and recovery history

The old boot's complete journal contains a PF TLB invalidation timeout at
**2026-11-13 21:59:11 Asia/Shanghai**, before the v5 guest was launched,
as well as timeouts on November 14 at 00:07:08, 00:08:07 and 00:28:02.
The later timeouts therefore cannot be attributed solely to v5 on timing
alone. This also does not prove v5 had no effect. Their cause is unresolved.

The owner performed a full shutdown and power-on before v5.1. The proposed
PF-assisted live recovery was not executed. The new boot had a no-VF
baseline at approximately 00:58:20–01:03:58 on November 14. Its submitted
kernel journal through the post-run check at approximately 01:12:59 has
no Xe TLB timeout or error-priority GPU report. An informational display
selective-fetch fallback is present; it is not a TLB timeout.

## Limits

- No direct PTE readback was performed. Functional CT use provides stronger
  evidence than a map acknowledgement alone, but not readback of every PTE.
- The guest's GGTT update traffic used the early MMIO relay. Successful
  native CT communication does not mean CT-based GGTT updates were tested.
- Media-GT CT, graphics/media workloads, full probe completion, rebind,
  multiple VFs, migration, suspend/resume and recovery races were not tested.
- Successful clears prove the acknowledged path completed in this run;
  they do not make timeouts equivalent to cancellation or make the
  diagnostic's indefinite hold acceptable in a production driver.
- No power or performance measurements were made. The diagnostic stops
  before a usable render device is registered.
