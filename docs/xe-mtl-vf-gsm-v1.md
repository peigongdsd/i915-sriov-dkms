# MTL SR-IOV branch status

This revision is a **PF/VFIO foundation with native MTL/ARL Xe VF probing
deliberately rejected**. It is not a completed native VF fix or a hardware-
validated upstream submission. The branch name is retained for continuity.
The reproduction baseline remains `e9130affe933dfc45309dc7a82599a1d7a38517e`.

## Changes above the baseline

1. Serialize VF GuC MMIO request/reply exchanges using a per-GuC mutex and
   bound firmware RETRY replies to 16 retries. Existing FLR/BUSY handling
   remains in place; no claim is made that RETRY caused the observed hang.
2. Require the root tile and firmware-permitted direct GSM mapping for the
   MTL SR-IOV PF. Rely on common Xe discovery for graphics/media IP selection.
   Never silently substitute the BAR-backed GGTT path in that mode.
3. Reuse one TLB invalidation issue sequence. Ordinary callers retain their
   cancellation policy; PF relay replies preserve issue and fence failures.
   Recheck the VF generation and both GT epochs after invalidation.
4. Reject native MTL/ARL VF probing before GGTT initialization, using an
   early host PCI check and a second check after existing VF detection for
   assigned guests. PF creation and VFIO binding remain available subject
   to the PF checks above.

## Why the previous native-forwarding revision was withdrawn

The previous branch tip `d43b183df582773e1ad7fb3850ca0a486e5362fa` tried
to retain BOs after uncertain relay completion. Static audit found that:

- A GEM reference and module reference do not retain the DRM device and its
  managed GGTT/TTM resources through failed probe teardown.
- Normal CT shutdown precedes some GGTT cleanup. Treating CT being stopped
  as uncertain submission could permanently poison ordinary cleanup.
- Reset can stop CT before taking the added GGTT lock. Permanent error
  state could therefore survive an otherwise recoverable reset.
- Per-page mapping requests repeated transport and two-GT invalidation
  work; the mock tests did not validate real lifetime or reset ordering.

The rewrite removes the native forwarding backend, permanent retention,
DMA-unmap bypass and added BO/reset/PM special cases. It does not substitute
unproved timeout cancellation. Before native enablement can return, delayed
remote writes must be ordered against address reuse, reset and teardown.

This reduction also corrects two audit overstatements: the baseline already
disables PCI runtime PM for every VF, and its pinned-BO eviction path skips
non-VRAM BOs. Neither observation proves the withdrawn retention safe.

## Validation and limits

- Xe and compatibility modules build against Linux 7.3.4 on the development
  host. This is not a build or runtime test on the target's Linux 7.3.3.
- `python3 tests/run_xe_mtl_ggtt.py` compiles extracted driver functions with
  AddressSanitizer/UndefinedBehaviorSanitizer. Set `CC` if needed.
- PF tests cover expansion modes, range/overflow rejection, ownership bits,
  PAT retention and rejection before captured writes.
- GSM admission tests exercise the actual PF check with mocked MMIO and
  mapping: no additional IP allowlist, root-tile rejection before permission
  reads, firmware denial, zero GSM base and mapping failure.
- TLB tests cover ordinary versus strict cancellation, unrecoverable,
  allocation, I/O and fence errors, using the shared issue implementation.
- The harness mocks locking, MMIO and fence completion. It does not test
  concurrency, physical access, device lifetime, GuC firmware or VF binding.
- The cumulative driver diff passes `checkpatch.pl --no-tree --no-signoff`
  with full macro context and passes whitespace checks. This is style
  validation, not confirmation of upstream acceptance.

No module was installed or loaded, no VF was bound, and no Nix configuration
or pin was changed. The reported VFIO success belongs to the user's earlier
baseline tests, not to a test of this rewritten branch.

See [platform notes](xe-mtl-platform-notes.md) for source versions, hardware
versus VF restrictions and the focused evidence needed for further work.
