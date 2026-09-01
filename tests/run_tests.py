# -*- coding: utf-8 -*-
"""EpicFigRig test suite.

    blender Append.blend --python tests/run_tests.py -- report.txt

Run it windowed. Several operators call bpy.ops.view3d.snap_cursor_to_selected
and bpy.ops.anim.keyframe_insert_menu, and both fail poll() without a real 3D
View, so `-b` cannot exercise them. The suite says so rather than quietly
reporting green on tests that never ran.

The optional path after `--` gets a copy of the report, written line by line.
Blender can hard-crash while tearing a scene down, which loses buffered stdout
and with it every result; the file survives and names the module it died in.
"""

import os
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import harness                                              # noqa: E402

# Args after `--`:  <report path> [module ...]
_LOG = None
_ONLY = ()
if "--" in sys.argv:
    _extra = sys.argv[sys.argv.index("--") + 1:]
    if _extra:
        _LOG = _extra[0]
    if len(_extra) > 1:
        _ONLY = tuple(_extra[1:])


def say(line=""):
    print(line)
    sys.stdout.flush()
    if _LOG:
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write(line)
            handle.write(os.linesep)


# Order matters. test_smear rigs its own figure and test_robustness resets the
# scene outright, so both come after everything that needs the rig that was
# loaded from Append.blend.
MODULES = (
    "test_master_bone",
    "test_pivot",
    "test_accessory",
    "test_interpolation",
    "test_robustness",
)

# Smears are NOT covered here. Driving a full auto.rig build from inside this
# harness hard-crashes Blender (EXCEPTION_ACCESS_VIOLATION / SIGSEGV) before
# the first assertion, in both background and windowed mode, while the exact
# same operator is fine in a plain self-contained script. Rather than ship a
# suite that dies half-way and loses every other result, that coverage lives
# in its own file:
#
#   blender -b --python tests/check_smear.py


def main():
    if _LOG and os.path.exists(_LOG):
        os.remove(_LOG)

    say()
    say("=" * 78)
    say("EpicFigRig test suite")
    say("=" * 78)

    module = harness.load_addon()
    # Tests that reach into the addon (to call _guarded_execute or
    # smear_needs_repair directly) pick it up from here.
    bpy.app.driver_namespace["epicfigrig_module"] = module
    say("addon under test: version %s" % (module.bl_info["version"],))

    override = harness.view3d_override()
    if override is None:
        say()
        say("!! No 3D View found -- running in background mode.")
        say("!! Operators needing a VIEW_3D context will report failures that")
        say("!! are the harness's fault, not the addon's. Run windowed:")
        say("!!   blender Append.blend --python tests/run_tests.py")
    say()

    total = passed = failed = skipped = 0
    failures = []

    selected = _ONLY or MODULES
    for name in selected:
        say("-" * 78)
        say(name)
        say("-" * 78)
        try:
            mod = __import__(name)
            results = mod.run(override)
        except Exception:                          # noqa: BLE001
            say(traceback.format_exc())
            failed += 1
            total += 1
            failures.append("%s (crashed)" % name)
            continue

        for result in results:
            say(str(result))
            total += 1
            if result.skipped:
                skipped += 1
            elif result.passed:
                passed += 1
            else:
                failed += 1
                failures.append("%s :: %s -- %s"
                                % (name, result.name, result.detail))
        say()

    say("=" * 78)
    say("%d checks: %d passed, %d failed, %d skipped"
        % (total, passed, failed, skipped))
    if failures:
        say()
        say("failures:")
        for line in failures:
            say("  - %s" % line)
    say("=" * 78)
    say()
    return 1 if failed else 0


if __name__ == "__main__":
    code = main()
    # In background mode the script ending is enough to exit. Windowed, Blender
    # would otherwise sit with the window open forever, so ask it to close --
    # the report file is what the caller reads in that case.
    if bpy.app.background:
        sys.exit(code)
    say("exit code would be %d" % code)
    bpy.ops.wm.quit_blender()
