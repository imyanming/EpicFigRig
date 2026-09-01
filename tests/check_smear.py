# -*- coding: utf-8 -*-
"""Smear check -- run this one on its own:

    blender -b --python tests/check_smear.py

It is deliberately NOT part of run_tests.py. Driving a full `auto.rig` build
from inside the suite harness hard-crashes Blender
(EXCEPTION_ACCESS_VIOLATION / SIGSEGV), in both background and windowed mode,
before the first assertion is reached. The same operator is perfectly happy in
a plain self-contained script like this one, so the fault is in how the
harness sets the run up, not in the addon. Rather than ship a suite that dies
half-way and loses the other results, smear coverage lives here.

What it checks: raising a smear must swap the real limb for the stretched
proxy mesh -- hide the arm or leg and show the proxy.

That was broken. driverCreate() fetched the curve to stamp with
obj.animation_data.drivers[0] for the hide_viewport driver *and again* for the
hide_render driver -- index 0 both times -- so the second call piled two more
points onto the first curve. Limbs came out with six keyframe points instead
of two, the on/off mapping stopped switching, and the smear appeared while the
real limb stayed visible underneath it. The proxies' own curves were always
fine, which is why the symptom read as "the smear works but the leg won't go
away".
"""

import os
import shutil
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Values above 1 are legitimate: the stock rig ships these properties with
# {'min': 0, 'max': 9} and the number is the smear length. The switch flips at
# >= 1. Fractional values are unreachable through the UI -- they are ints.
SWITCH_VALUES = (0, 1, 2, 5, 8)

# AutoRig identifies parts by LEGO part-number substrings in the *mesh data*
# name, not the object name.
PARTS = {
    "head": "3626", "torso": "3814", "hips": "3815",
    "leg_l": "3817", "leg_r": "3816",
    "arm_l": "3819", "arm_r": "3818",
}

PAIRS = (
    ("LLegSmear", "leg_l", "FinishedLlegS"),
    ("LArmSmear", "arm_l", "FinishedLarmS"),
)

failures = []


def report(name, ok, detail):
    print("  [%s] %-44s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        failures.append("%s -- %s" % (name, detail))


def load_addon(module_name="epicfigrig_under_test"):
    """Copy the addon into a throwaway package and register it.

    AutoRig appends from the three .blend files and refuses to run unless they
    sit beside __init__.py, so they have to be copied too."""
    pkg = os.path.join(ROOT, module_name)
    if not os.path.isdir(pkg):
        os.makedirs(pkg)
    for fname in ("__init__.py", "Append.blend", "Append_Child.blend",
                  "Cape_Rig.blend"):
        source = os.path.join(ROOT, fname)
        target = os.path.join(pkg, fname)
        if fname == "__init__.py" or not os.path.isfile(target):
            shutil.copyfile(source, target)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    import importlib
    module = importlib.import_module(module_name)
    module.register()
    return module


def build_minifig():
    """Stand-in parts good enough for AutoRig: right data names, a material."""
    made = []
    for name, number in PARTS.items():
        mesh = bpy.data.meshes.new("%s_%s" % (number, name))
        mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
        # Rigging copies each part's material onto its smear proxy, so an
        # unpainted part is refused up front by _preflight_rigging().
        mesh.materials.append(bpy.data.materials.new("mat_" + name))
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        made.append(obj)
    for obj in made:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = made[0]
    return made


def evaluated(arm, obj):
    """Depsgraph-evaluated copy -- drivers write there, not to bpy.data."""
    arm.data.update_tag()
    obj.update_tag()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return obj.evaluated_get(depsgraph)


def main():
    print("")
    print("=" * 74)
    print("EpicFigRig smear check")
    print("=" * 74)

    module = load_addon()
    print("addon under test: version %s" % (module.bl_info["version"],))
    print("")

    build_minifig()
    outcome = bpy.ops.auto.rig()
    report("auto.rig builds a test figure", outcome == {'FINISHED'},
           "returned %s" % (outcome,))

    arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
    if arm is None:
        report("rigged armature exists", False, "none in scene")
        return 1

    if hasattr(module, "smear_needs_repair"):
        needs = module.smear_needs_repair(arm)
        report("switch curves are normalised", not needs,
               "smear_needs_repair() = %s" % needs)

    for prop, limb_name, proxy_name in PAIRS:
        limb = bpy.data.objects.get(limb_name)
        proxy = bpy.data.objects.get(proxy_name)
        if limb is None or proxy is None:
            report("%s pair present" % prop, False,
                   "missing %s / %s" % (limb_name, proxy_name))
            continue
        for value in SWITCH_VALUES:
            arm.data[prop] = value
            limb_hidden = evaluated(arm, limb).hide_viewport
            proxy_shown = not evaluated(arm, proxy).hide_viewport
            want = value >= 1
            report("%s=%d swaps limb for proxy" % (prop, value),
                   limb_hidden == want and proxy_shown == want,
                   "limb hidden=%s, proxy shown=%s (want both %s)"
                   % (limb_hidden, proxy_shown, want))
        arm.data[prop] = 0

    print("")
    print("=" * 74)
    if failures:
        print("%d FAILED" % len(failures))
        for line in failures:
            print("  - %s" % line)
    else:
        print("all smear checks passed")
    print("=" * 74)
    print("")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
