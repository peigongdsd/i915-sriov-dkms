#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Compile driver functions against captured I/O; never access hardware."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
XE = ROOT / "drivers/gpu/drm/xe"


def block(source, start):
    begin = source.index("{", start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end] + "\n"


def function(source, name):
    pattern = r"^(?:static )?(?:int|void|bool) " + re.escape(name) + r"\("
    return block(source, re.search(pattern, source, re.MULTILINE).start())


ggtt_source = (XE / "xe_ggtt.c").read_text()
pf = function(ggtt_source, "xe_ggtt_update_vf_ptes")
early = function(ggtt_source, "xe_ggtt_init_early")
gsm = block(early, early.index(
    "\tif (xe->info.platform == XE_METEORLAKE && IS_SRIOV_PF(xe)) {"))
tlb_source = (XE / "xe_tlb_inval.c").read_text()
service_source = (XE / "xe_gt_sriov_pf_service.c").read_text()
service = "".join(function(service_source, name) for name in (
    "pf_update_ggtt", "pf_process_update_ggtt_msg"))
start = tlb_source.index("#define __xe_tlb_inval_issue(")
end = tlb_source.index("/**", start)
tlb = tlb_source[start:end]
for name in ("xe_tlb_inval_all", "tlb_inval_ggtt", "xe_tlb_inval_ggtt",
             "xe_tlb_inval_ggtt_sync"):
    tlb += function(tlb_source, name)

with tempfile.TemporaryDirectory(prefix="xe-mtl-test-") as tmp:
    work = Path(tmp)
    (work / "linux").mkdir()
    (work / "linux/types.h").write_text("/* Types supplied by the harness. */\n")
    (work / "linux/build_bug.h").write_text("#define static_assert _Static_assert\n")
    for case, functions in (("xe_mtl_ggtt", pf), ("xe_tlb_inval", tlb),
                            ("xe_mtl_gsm", gsm), ("xe_mtl_service", service)):
        (work / "actual-functions.inc").write_text(functions)
        binary = work / case
        subprocess.run(shlex.split(os.environ.get("CC", "cc")) + [
            "-std=gnu11", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
            "-I" + str(work), "-I" + str(XE),
            str(ROOT / "tests" / (case + ".c")), "-o", str(binary),
        ], check=True)
        subprocess.run([str(binary)], check=True)
