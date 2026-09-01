# -*- coding: utf-8 -*-
"""Shared scaffolding for the EpicFigRig test suite.

Everything here exists because of something that actually went wrong while
porting this addon, so the comments explain the trap rather than the code.
"""

import math
import os
import sys

import bpy


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

class Result:
    """One assertion, with the number that produced it.

    Tests record measurements, not just booleans. A failure that says
    "character moved 4.991, wanted < 0.05" is worth ten that say False."""

    def __init__(self, name, passed, detail, skipped=False):
        self.name = name
        self.passed = passed
        self.detail = detail
        self.skipped = skipped

    def __str__(self):
        mark = "SKIP" if self.skipped else ("PASS" if self.passed else "FAIL")
        return "  [%s] %-46s %s" % (mark, self.name, self.detail)


def check(name, passed, detail):
    return Result(name, bool(passed), detail)


def close(name, got, want, tol, unit=""):
    ok = abs(got - want) <= tol
    return Result(name, ok, "%.4f%s (want %.4f +/- %.4f)" % (got, unit, want, tol))


def skip(name, why):
    return Result(name, True, why, skipped=True)


# --------------------------------------------------------------------------
# Blender context
# --------------------------------------------------------------------------

def view3d_override():
    """A context override containing a real 3D View, or None in background mode.

    Several operators call bpy.ops.view3d.snap_cursor_to_selected and
    bpy.ops.anim.keyframe_insert_menu, both of which fail poll() without a
    VIEW_3D area. Tests that need those must run windowed:

        blender Append.blend --python tests/run_tests.py

    Running with -b is fine for everything else and is much faster."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next(r for r in area.regions if r.type == 'WINDOW')
                return dict(window=window, area=area, region=region)
    return None


def run_op(operator, override):
    """Call an operator, returning (result, error_string)."""
    try:
        if override:
            with bpy.context.temp_override(**override):
                return operator(), None
        return operator(), None
    except Exception as exc:                      # noqa: BLE001 - reporting
        return None, "%s: %s" % (type(exc).__name__, str(exc).split("\n")[0])


# --------------------------------------------------------------------------
# The rig
# --------------------------------------------------------------------------

def get_rig():
    """The armature under test, renamed the way AutoRig leaves it.

    Several code paths reach the armature through
    bpy.data.armatures[selected_armature], which is keyed by the *data-block*
    name while selected_armature holds the *object* name. They must match --
    see DESIGN_INTENT.md section 4."""
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    arm.name = 'FinishedRig'
    arm.data.name = 'FinishedRig'
    return arm


def enter_pose_mode(arm):
    bpy.context.view_layer.objects.active = arm
    for obj in bpy.data.objects:
        obj.select_set(False)
    arm.select_set(True)
    if bpy.context.mode != 'POSE':
        bpy.ops.object.mode_set(mode='POSE')


def clear_pose(arm):
    for bone in arm.pose.bones:
        bone.location = (0.0, 0.0, 0.0)
        if bone.rotation_mode == 'QUATERNION':
            bone.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        else:
            bone.rotation_euler = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()


def world_of(arm, bone_name):
    """World-space location of a pose bone.

    Read through matrix_world deliberately. The bug that started this port was
    code assuming the armature object sits at the origin; the stock rig sits at
    (0, 0, 16) and a working scene can be anywhere."""
    bpy.context.view_layer.update()
    return (arm.matrix_world @ arm.pose.bones[bone_name].matrix).to_translation()


def facing_degrees(arm, bone_name="Center of Mass"):
    """Which way the character points, in degrees about the vertical axis."""
    bpy.context.view_layer.update()
    matrix = arm.matrix_world @ arm.pose.bones[bone_name].matrix
    basis = matrix.to_3x3()
    basis.normalize()
    return math.degrees(math.atan2(basis[1][0], basis[0][0]))


def evaluated(arm, obj=None):
    """Depsgraph-evaluated copy.

    Drivers write to the evaluated copy, not the original datablock. Reading
    obj.hide_viewport straight off bpy.data gives the stored value and makes a
    working driver look broken -- that cost a whole debugging round."""
    target = obj if obj is not None else arm
    arm.data.update_tag()
    target.update_tag()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return target.evaluated_get(depsgraph)


def action_fcurves(owner):
    """F-curves of an ID's action, across Blender's action layouts.

    Blender 4.4 introduced slotted actions and action.fcurves disappeared."""
    anim = getattr(owner, "animation_data", None)
    action = getattr(anim, "action", None)
    if action is None:
        return
    try:
        for fcurve in action.fcurves:
            yield fcurve
        return
    except AttributeError:
        pass
    for layer in action.layers:
        for strip in layer.strips:
            try:
                bags = list(strip.channelbags)
            except AttributeError:
                continue
            for bag in bags:
                for fcurve in bag.fcurves:
                    yield fcurve


def load_addon(module_name="epicfigrig_under_test"):
    """Import the addon source sitting one directory up, and register it."""
    import importlib
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    pkg = os.path.join(root, module_name)
    if not os.path.isdir(pkg):
        os.makedirs(pkg)
    # AutoRig appends from these and refuses to run if they are not beside
    # __init__.py, so the throwaway package needs them too.
    import shutil
    for fname in ("__init__.py", "Append.blend", "Append_Child.blend",
                  "Cape_Rig.blend"):
        source = os.path.join(root, fname)
        target = os.path.join(pkg, fname)
        if os.path.isfile(source) and not os.path.isfile(target):
            shutil.copyfile(source, target)
        elif fname == "__init__.py":
            shutil.copyfile(source, target)
    if root not in sys.path:
        sys.path.insert(0, root)
    # Import once and do NOT reload. Reloading a module whose Blender classes
    # are already registered leaves stale RNA pointers behind, and a later
    # operator call dereferences freed memory -- Blender dies with
    # EXCEPTION_ACCESS_VIOLATION part-way through the run. Each invocation gets
    # a fresh Blender process anyway, so there is nothing to reload for.
    module = importlib.import_module(module_name)
    try:
        module.register()
    except Exception as exc:                      # noqa: BLE001
        print("[tests] register() warning: %s" % exc)
    return module
