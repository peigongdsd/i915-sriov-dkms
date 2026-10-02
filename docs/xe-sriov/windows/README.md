# Targeted Windows driver analysis

This is supporting evidence for distinguishing guest-driver startup failures from Linux PF/VF failures. The current implementation effort remains Linux ADL-P first.

- [ADL-generation 7092 findings](analysis/7092/findings.md)
- [MTL/ARL 9033 findings and qualified resource-parser result](analysis/9033-findings.md)

The original classifiers were executed in isolated CPU emulation. Windows and GPU hardware were not simulated. The 9033 resource-parser experiment additionally uses synthetic descriptors; its conditional failure does not establish the resource layout of a real guest. No Intel binary is included or modified.

Official packages used:

| Package | Official download | Inspected `Graphics/igdkmdn64.sys` SHA-256 |
|---|---|---|
| 32.0.101.7092 | [Intel 11th–14th-generation package](https://downloadmirror.intel.com/929468/gfx_win_101.7092.exe) | `454624942bf9a79a75fd1bfe6c6a2f8d499aabef45cb4268a1353d527902d098` |
| 32.0.101.9033 | [Intel Arc/Core Ultra package](https://downloadmirror.intel.com/929557/gfx_win_101.9033.exe) | `2969ef18daf397b43353dd4ff465f52a8107fc1a612eab4a8cc2703dee919a4d` |

To reproduce, extract the matching package with a RAR-capable extractor, placing the module at `windows/extracted/<7092-or-9033>/Graphics/igdkmdn64.sys` relative to the parent study directory. The scripts assert the expected module hash. Use Python with `pefile` and `unicorn`; `capstone` is used by the separate disassembly tooling. Then run:

```sh
python analysis/emulate_7092_classifier.py
python analysis/emulate_9033_classifier.py
python analysis/emulate_9033_resources.py
```

Run those commands from this `windows` directory. Outputs are the adjacent recorded JSON files. Utility-call stubs and supplied inputs are visible in the scripts; these substitutions bound the conclusions. Exact private enum names and a general end-to-end Code 43 cure were not recovered.
