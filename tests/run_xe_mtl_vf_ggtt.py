#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Test the actual VF range backend and MMIO transport without hardware.

The harness supplies scripted replies and a delayed-write model. It does
not exercise kernel concurrency, TTM ownership, firmware or real DMA.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
XE = ROOT / "drivers/gpu/drm/xe"
guc = (XE / "xe_guc.c").read_text()
transport = guc[guc.index("#define MAX_RETRIES_ON_FLR"):
                guc.index("int xe_guc_mmio_send(struct")]
backend = (XE / "xe_gt_sriov_vf_ggtt.c").read_text()
backend = re.sub(r"^#include[^\n]*\n", "", backend, flags=re.MULTILINE)
types = (XE / "xe_gt_sriov_vf_types.h").read_text()
start = types.index("struct xe_gt_sriov_vf_ggtt {")
state = types[start:types.index("};", start) + 2]

with tempfile.TemporaryDirectory(prefix="xe-vf-ggtt-") as tmp:
    work = Path(tmp)
    (work / "linux").mkdir()
    (work / "linux/types.h").write_text("/* Supplied by the harness. */\n")
    (work / "linux/build_bug.h").write_text("#define static_assert _Static_assert\n")
    (work / "actual-state.inc").write_text(state)
    (work / "actual-functions.inc").write_text(transport + backend)
    binary = work / "vf-ggtt"
    subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
        "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-Wno-sign-compare",  # Existing Xe transport uses signed loop counters.
        "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
        "-I" + str(work), "-I" + str(XE),
        str(ROOT / "tests/xe_mtl_vf_ggtt.c"), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
