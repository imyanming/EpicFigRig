# -*- coding: utf-8 -*-
"""Keyframe interpolation.

These operators play a trick: key the old pose one frame back, key the new
pose on the current frame. That only reads as an instant change if the
*boundary* key on frame-1 holds flat, so the operators force CONSTANT
interpolation while they run.

The mistake was letting that apply to the current-frame key too. That key is
the one carrying motion forward, and a CONSTANT key holds its value until the
next one, so everything after it stepped instead of interpolating. One press
of Reset Master Bone with Auto-Key on wrote 72 CONSTANT keys across 37 curves
and the whole animation went stop-motion.

There was a second, nastier half: the preference was restored by a plain
statement at the end of each operator rather than a finally, so any error
part-way through left the user's *global* default stuck on CONSTANT. Every
keyframe they placed by hand afterwards came out stepped, with no clue why.
"""

import bpy

from harness import (action_fcurves, check, clear_pose, enter_pose_mode,
                     get_rig, run_op)

USER_INTERP = 'BEZIER'


def run(override):
    arm = get_rig()
    prefs = bpy.context.preferences.edit
    scene = bpy.context.scene
    results = []

    module = bpy.app.driver_namespace.get("epicfigrig_module")

    # --- the preference must survive both exit paths ----------------------
    if module is not None and hasattr(module, "_guarded_execute"):
        class _Fake:
            epic_kind = 'NONE'

            def report(self, level, message):
                pass

        class _Ok(_Fake):
            def _execute_inner(self, context):
                prefs.keyframe_new_interpolation_type = 'CONSTANT'
                return {'FINISHED'}

        class _Boom(_Fake):
            def _execute_inner(self, context):
                prefs.keyframe_new_interpolation_type = 'CONSTANT'
                raise ValueError("simulated mid-operator failure")

        for label, cls in (("success", _Ok), ("exception", _Boom)):
            prefs.keyframe_new_interpolation_type = USER_INTERP
            module._guarded_execute(cls(), bpy.context)
            restored = prefs.keyframe_new_interpolation_type
            results.append(check(
                "interpolation restored on %s" % label,
                restored == USER_INTERP,
                "left at %s (want %s)" % (restored, USER_INTERP)))

    # --- boundary key stepped, current-frame key not ----------------------
    prefs.keyframe_new_interpolation_type = USER_INTERP
    enter_pose_mode(arm)
    clear_pose(arm)
    if arm.animation_data:
        arm.animation_data_clear()
    scene.tool_settings.use_keyframe_insert_auto = True
    scene.frame_set(20)

    _, err = run_op(bpy.ops.rig.reset, override)
    if err:
        results.append(check("Auto-Key press runs", False, err))
        scene.tool_settings.use_keyframe_insert_auto = False
        return results

    boundary, current, other = [], [], []
    for fcurve in action_fcurves(arm):
        for point in fcurve.keyframe_points:
            frame = round(point.co[0])
            if frame == 19:
                boundary.append(point.interpolation)
            elif frame == 20:
                current.append(point.interpolation)
            else:
                other.append(point.interpolation)

    # A couple of curves come out LINEAR because keyframe_insert() on the
    # custom property does not consult this preference. Those were never
    # CONSTANT, so the fix leaves them alone -- asserting "all CONSTANT" or
    # "all BEZIER" would be testing an accident rather than the guarantee.
    results.append(check(
        "frame-1 boundary keys are stepped",
        'CONSTANT' in boundary,
        "%d keys, %s" % (len(boundary), sorted(set(boundary)) or "none")))
    results.append(check(
        "no stepped keys on the current frame",
        bool(current) and 'CONSTANT' not in current,
        "%d keys, %s" % (len(current), sorted(set(current)) or "none")))

    scene.tool_settings.use_keyframe_insert_auto = False
    prefs.keyframe_new_interpolation_type = USER_INTERP
    return results
