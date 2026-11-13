# Meteor Lake SR-IOV: review series

This is a review candidate for the **PF/VFIO foundation**, with normal native
Xe VF probing still rejected. It is not a finished native VF driver or a
drop-in upstream submission. The separate v5.1 experiment has now completed
native VF bootstrap and cleanup on hardware; its diagnostic machinery is
intentionally absent from this series.

The intended upstream direction is to reuse Xe's GGTT allocator, BO/TTM
ownership, GuC transport, fences, workqueues and power management. MTL needs
a permitted GGTT update backend and a complete remote-update lifetime
contract. It does not need another general interrupt implementation.

## Base and composition

Base: [strongtz bea718703726](https://github.com/strongtz/i915-sriov-dkms/commit/bea7187037269859515dd0b9bece5c50a0bcadb9).
This is a DKMS tree containing other downstream changes. Porting to upstream
requires a separate rebase and review against an explicitly selected Linux
revision; successful builds here do not establish upstream applicability.

| Order | Driver commit | Purpose |
| --- | --- | --- |
| 1 | `16e99118e0da` | Serialize VF MMIO exchanges and bound firmware RETRY replies. |
| 2 | `209282d94aef` | Supply legacy MTL VF runtime registers, including sibling-GT lookup. |
| 3 | `d85a4e02303d` | Require firmware-permitted direct GSM access for MTL PFs. |
| 4 | `3e30ba662cf9` | Preserve strict GGTT invalidation errors without changing ordinary callers. |
| 5 | `a3dc37cfdf13` | Validate and service VF GGTT relay requests, with two-GT completion checks. |
| 6 | `7988f91d6115` | Add the MTL render color-cache register whitelist entry. |
| 7 | `9c7c93a6168a` | Prepare GSC/PXP around provisioning using existing PF PM ownership. |
| 8 | `7d46ace2100f` | Enable the MTL PF and reject the incomplete ordinary native VF path together. |

Offline tests and these review documents follow as separate commits. The
runtime-register definitions are included with their first use, and PF
enablement is last. Each of the eight driver trees builds independently.
Commit messages link their earlier peigongdsd sources and identify the
xbomber/i915 origins where applicable. No contributor sign-off is invented;
provenance and DCO review are still needed before mailing upstream.

The final `drivers/` tree is byte-identical to
`9846418d548a777eff1f8c9d4bb6a42770cd336c`. This is a dependency-ordered
recomposition, not another hardware-tested runtime change. Compared with
the tested host PF `02acd0415e056e859159e4825c3119124eee9785`, the only
driver difference is removal of the redundant graphics/media IP allowlist
before the GSM permission read. The tested 1271/1300 pair passed that older
allowlist; this source equivalence does not validate other IP combinations.

The old PF branch and diagnostic branch remain intact. In particular,
[v5.1 at 292dec2](https://github.com/peigongdsd/i915-sriov-dkms/tree/292dec2bfa0d121df72012cb43f14c437edf5146)
remains the exact guest test reference. Do not replace the deployed host
source or diagnostic reference merely to match the new commit layout.

## Design choices

- Reuse the existing CPU PTE operations when firmware permits direct GSM.
  There is no fallback to the affected BAR window and no GPU binder in this
  series. xbomber's migration-queue binder is a distinct backend with its
  own submission/bootstrap dependencies, useful to consider if direct CPU
  access is unavailable.
- Use one PF validator for the existing MMIO and CT relay formats. Verify
  VF-relative bounds, expansion, 46-bit DMA addresses and PAT bits before
  writes, and derive the VF ownership bits from the request origin.
- A successful relay update requires strict invalidation completion for
  both affected GTs. Ordinary Xe TLB callers keep their existing policy.
- Keep MMIO GGTT servicing outside the G2H handler because invalidation
  itself waits on GuC CT. Reuse the existing SR-IOV workqueue and PM guard.
- Add no permanent forcewake reference, new blanket VF PM prohibition,
  DMA-unmap bypass or permanent BO/module retention scheme. Avoiding extra
  submission work is a design property; performance and power savings
  have not been measured.

## Validation on the development host

On 2026-11-14, all eight driver commit trees built Xe and compatibility
modules against Linux 7.3.4 with `KCFLAGS=-g` and GCC 16.2.0. Commit messages
were subsequently polished without changing any tree; the build manifest
records both commit identities and their identical tree IDs. No compiler
warnings or errors were found in those build logs.

`CC=<host-compiler> python3 tests/run_xe_mtl_ggtt.py` compiles extracted driver
functions with AddressSanitizer and UndefinedBehaviorSanitizer. Four suites
cover:

1. PTE expansion, VF range/overflow rejection, PAT and VFID ownership.
2. Ordinary versus strict TLB issue/completion error policy.
3. GSM admission, firmware denial, zero base and mapping failure.
4. PF message length/reserved-field checks, ABI negotiation, PTE decoding,
   both-GT completion errors and state changes before/after writes.

The fourth suite explicitly demonstrates that an error after a PTE write
is not rollback: the service returns failure and must not encode success.
It scripts state changes and mocks locking/firmware; it does not prove
concurrent reset ordering, actual cancellation or physical memory access.

The existing v5.1 bootstrap and relay test scripts also passed all 32 local
cases at the frozen diagnostic revision. Those tests exercise extracted
helpers with simulated replies, not kernel execution.

The driver patches pass whitespace checks and the pinned upstream
`checkpatch.pl` with full macro context and `--no-tree --no-signoff`.
Checkpatch is a style check, not upstream approval. The local build has
`CONFIG_PCI_IOV=y`; !PCI_IOV, KUnit, lockdep and other configuration/runtime
matrices were not exercised. No module was loaded by this review work.
The hardware submission used Linux 7.3.3, a distinct build environment.

## Gates before upstream acceptance

1. **Remote-update lifetime.** Receive-time generations and CT epochs reject
   observed stale state; they cannot cancel messages still in firmware or
   prove that a late PF write cannot arrive after VF timeout/reset. This
   remains a review gate for the PF service as well as native VF enablement.
2. **Register scope.** The nonprivileged whitelist grants access to all of
   `COMMON_SLICE_CHICKEN3`, not just bit 13. Its other bits and context
   semantics need authoritative review. A working Windows guest is not a
   complete register-access contract.
3. **Assignment invalidation.** The retained MTL PF assignment path issues
   MMIO invalidation under temporary forcewake but does not poll completion.
   Do not describe it as equivalent to the strict relay completion path.
4. **Transport policy.** Sixteen ordinary MMIO RETRY replies is a bounded
   policy, not a measured firmware requirement. Review it independently
   from MTL enablement; uncertain PTE updates must not use blind replay.
5. **Platform and lifecycle scope.** MTL/ARL share the descriptor here, but
   evidence covers one MTL-H system. Multiple VFs, CT GGTT writes, repeated
   enable/disable, reset races, suspend/resume, GSC/PXP failures and workloads
   remain unvalidated. Firmware denial has no alternate backend here.

These are explicit RFC boundaries, not requests for another experiment
while the owner is away. The [hardware results](xe-mtl-vf-bootstrap-results.md)
and [native VF design](xe-mtl-native-vf-design.md) identify which conclusions
are already supported and which code contracts remain to be implemented.
