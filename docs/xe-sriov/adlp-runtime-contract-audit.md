# ADL-P after CCS enable: bounded runtime-service audit

**Later capture update:** the replacement archives and second VM attempt are analyzed in [the current capture note](adlp-reuploaded-capture-analysis.md). All have CCS enabled; the second attempt faults before any new KVMFR export. The user confirms unchanged settings and persistent Code 43. A separate [ADL-P render-context experiment](adlp-indirect-offset-experiment.md) is now built for testing. The source distinctions below remain evidence, not established causes.

Inspected on 2026-10-02. Baseline: `strongtz/i915-sriov-dkms` commit `f4cb98f4c28e1f3ac78ca88501a87c86d0c21a88`. Windows binary: official 32.0.101.7092 `igdkmdn64.sys`, SHA-256 `454624942bf9a79a75fd1bfe6c6a2f8d499aabef45cb4268a1353d527902d098`. The actual failing guest's module hash/version has not been established by this inspection. This is source and original-binary analysis, not a GPU test. No driver source or configuration was changed.

The user reports Code 43 persists after enabling CCS. The previously supplied log established a separate PF render-engine timeout in host `.org.gnome.Naut`; it did not establish the first failed guest operation. Preserve that PF coredump and correlate a fresh occurrence with guest startup before assuming an isolated guest-only failure.

## There is no demonstrated ABI 0.1 versus 1.0 version mismatch

The actual working-i915 comparison source defines both base and latest ABI as **1.0**, in `drivers/gpu/drm/i915/gt/iov/abi/iov_version_abi.h:9`. Xe defines the same values in `drivers/gpu/drm/xe/abi/guc_relay_actions_abi.h:24`.

For the valid two-word CT handshake, i915 `intel_iov_service.c:265` and Xe `xe_sriov_pf_service.c:41` both choose 1.0 for a 0.0 ANY request or a newer major, accept a 1.x request with negotiated minor zero, and reject an explicit 0.1 request. Their Linux rejection errno differs; their accepted version sets do not. The Windows handshake bytes have not been recovered or observed. Downgrading Xe's ABI declaration to 0.1 is therefore unsupported by this comparison.

## A real sequencing difference deserves a trace

Xe records successful handshake state per VF, then requires negotiated ABI 1.0 before serving `VF2PF_QUERY_RUNTIME` (action `0x0101`): `xe_gt_sriov_pf_service.c:329` returns `-EACCES` if that state is missing. `xe_sriov_pf_service.c:176` clears the state when the VF connection is reset. Its successful-handshake path logs the negotiated version.

i915's CT handshake sends a reply without recording corresponding negotiated state (`intel_iov_service.c:308`). Its request dispatcher (`:450`) directly invokes the runtime handler; `pf_reply_runtime_query` (`:314`) checks message length and range but has **no equivalent negotiation-state check**. Thus a guest that queries before handshaking, or reuses pre-reset assumptions, can encounter different behavior. That is a concrete difference in PF behavior, **not evidence that Windows actually does this**.

The most discriminating service trace is the VF-specific order and replies: handshake action `0x0001`, runtime action `0x0101`, each reset/FLR, negotiated version, and first failing reply. A successful 1.0 handshake followed by successful runtime pages rules out this particular ordering explanation for that startup. A runtime request rejected with EACCES before negotiation would establish the missing edge and justify a narrowly scoped compatibility decision rather than an ABI-number change.

Verbose service-action logging in `xe_gt_sriov_pf_service.c:382` is conditional on `CONFIG_DRM_XE_DEBUG_SRIOV` through `xe_gt_sriov_printk.h:30`; enabling dynamic debug cannot restore code compiled out by that option. Ordinary successful-handshake logging is not that verbose-only macro. A diagnostic patch, if needed, should log action, VF, result and reset sequence without changing acceptance policy first.

## Two missing clock registers are real, but VF consumption is unproved

At this pinned source, Xe's TGL-family runtime list exports eight register/value entries, whereas i915 exports ten. The additional i915 entries are `CTC_MODE` (`0xA26C`) and `GEN9_TIMESTAMP_OVERRIDE` (`0x44074`): `xe_gt_sriov_pf_service.c:24` versus `intel_iov_service.c:31`. `0x9144` is already present in this DKMS Xe and must not be proposed as a newly missing entry merely because bare mainline differs. The public service returns raw register values, so the EU_ENABLE/EU_DISABLE source-name difference does not itself imply transformed values.

Runtime query `0x0101` is **enumeration by start index and limit**, returning offset/value pairs and remaining count; it does not request a named register address. A trace will therefore show which pages Windows obtains, not a literal request for CTC_MODE. Compare the complete PF runtime maps plus response pages from working i915 and failing Xe with an unchanged guest.

Original 7092 code supports the following narrower statements; all addresses below are RVAs for the hashed file:

- `0x3D236D–0x3D2425` reads `0xA26C`, `0xD00`, and conditionally `0x44074`, computes a clock frequency, and stores it in a nested object's `+0x7F4`. The non-override path derives a nonzero standard frequency from RPM_CONFIG0. A missing CTC_MODE that reads as zero therefore does **not by itself imply an immediate fatal error** in this arithmetic.
- Leaf `0x3D1120` follows nested-object `+0x728` to the adapter, then invokes the function at adapter-vtable `+0xF8` through Control Flow Guard dispatch. The VF-specific target of that callback has **not** been proved.
- `0x269590` searches cached `(offset, value)` pairs: primary GT uses adapter `+0x56BB0` count and `+0x56BB8` pointer; media GT uses `+0x56BC0/+0x56BC8`. If absent, it writes zero through its output argument and logs. This is an actual cache helper, but a call edge from the clock reader to it was not established.
- `0x269A10–0x269D1E` creates a cache from a platform register list (`+0x5AC80/+0x5AC88`) and reads each value through the same vtable `+0xF8` callback. This function contains no proved PF-runtime relay transaction. It can describe native capture; it cannot by itself prove VF negotiation or consumption of PF data.
- Several platform initialization functions install ten-entry lists; for example `0x26C540` installs internal platform `0x25`, a list at RVA `0x8A61E0`, and count ten. This pass did not complete the PCI-ID-to-initializer selection for ADL-P `46A6`. Tables selected for other generations are not ADL-P evidence.

Raw instruction evidence: `windows/analysis/7092/runtime-register-consumers.txt`, `runtime-register-xrefs.txt`, `runtime-query-flow.txt`, `runtime-table-select.txt`, `runtime-count-xrefs.txt`, `runtime-cache-xrefs.txt`, and `runtime-list-xrefs.txt`. The PE exception table omits some leaf functions and splits other functions; a preceding exception-table entry alone must not be treated as a valid function boundary. `runtime-register-consumers.txt` explicitly appends the verified complete `0x3D1120` leaf after the initial exploratory disassembly.

## Evidence-ranked next action

First capture the PF render failure/coredump and the first VF service/submission failure during the same unchanged-guest startup. In that capture, discriminate the concrete handshake-state difference before altering ABI policy. Compare the full runtime maps; if negotiation succeeds and the guest consumes the returned map, an isolated two-register exposure A/B is a small plausible compatibility experiment, but still requires measured startup behavior and timing values. There is no present justification to migrate i915's complete service implementation or introduce an additional relay protocol for ADL-P.

The prior Hyper-V binary findings remain conditional on actual guest CPUID and Hyper-V state; they do not explain a controlled i915-success/Xe-failure pair by themselves. Neither this audit nor the previous classifier emulation proves a path from these two absent registers to Code 43.
