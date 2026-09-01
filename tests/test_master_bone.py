# -*- coding: utf-8 -*-
"""Reset Master Bone / Snap Master Bone.

Both buttons move MasterBone to wherever the character actually is. The whole
point is that the character itself must not appear to move -- the author's
tutorial calls it snapping the master bone forward "seamlessly" so feet do not
slide when a walk cycle repeats.

Before v1.0.11, Snap Master Bone displaced the character by the same amount it
moved the root, and the error accumulated on every press
(4.99 -> 9.98 -> 14.97 -> 19.96). That is exactly the foot-sliding the feature
exists to prevent, and it was present in the 2022 original too.
"""

import math

import bpy

from harness import (check, clear_pose, close, enter_pose_mode, facing_degrees,
                     get_rig, run_op, world_of, action_fcurves)

# The rig's own bone matrices carry about 0.001 of skew, which shows up as
# roughly 0.01 of residual movement per press. Real, and it does slowly
# accumulate, but it is the rig's geometry and not the operator's arithmetic.
RESIDUAL = 0.05

# Probe the hip, not "Center of Mass". The hierarchy is
#     Center of Mass    -> MasterBone
#     BodyControlBoneIK -> ... -> Center of Mass -> MasterBone
# so Center of Mass is a direct child of the root and *must* travel with it;
# measuring there reports a 4.99 "failure" for correct behaviour. The body
# hangs off BodyControlBoneIK, whose compensating offset is the thing that
# keeps the character standing still.
BODY = "BodyControlBoneIK"


def _preload(arm, forward=-5.0):
    """A character standing off its root, the state these buttons are for."""
    clear_pose(arm)
    arm.pose.bones["BodyControlBoneIK"].location[1] = forward
    bpy.context.view_layer.update()


def run(override):
    arm = get_rig()
    results = []
    bpy.context.scene.tool_settings.use_keyframe_insert_auto = False

    for name, op in (("rig.reset", bpy.ops.rig.reset),
                     ("snap.masterbone", bpy.ops.snap.masterbone)):
        enter_pose_mode(arm)
        _preload(arm)
        before_body = world_of(arm, BODY).copy()
        before_root = world_of(arm, "MasterBone").copy()

        _, err = run_op(op, override)
        if err:
            results.append(check("%s runs" % name, False, err))
            continue

        moved_root = (world_of(arm, "MasterBone") - before_root).length
        moved_body = (world_of(arm, BODY) - before_body).length

        results.append(check("%s moves the root" % name, moved_root > 1.0,
                             "root moved %.3f" % moved_root))
        results.append(close("%s leaves the character put" % name,
                             moved_body, 0.0, RESIDUAL))

    # Pressing the same button repeatedly must not walk the character away.
    enter_pose_mode(arm)
    _preload(arm)
    start = world_of(arm, BODY).copy()
    for _ in range(4):
        _, err = run_op(bpy.ops.snap.masterbone, override)
        if err:
            break
    drift = (world_of(arm, BODY) - start).length
    results.append(check("four presses do not accumulate", drift < 4 * RESIDUAL,
                         "total drift %.3f over 4 presses" % drift))

    # Rotation. Euler decomposition is ambiguous at half a turn: reading
    # matrix.to_euler().z there returns roughly zero, so a character facing
    # directly away used to be spun back to front. _yaw_from_matrix() reads the
    # angle off the matrix instead, which has no singularity.
    for degrees in (30, 90, 180):
        for name, op in (("rig.reset", bpy.ops.rig.reset),
                         ("snap.masterbone", bpy.ops.snap.masterbone)):
            enter_pose_mode(arm)
            clear_pose(arm)
            arm.pose.bones["Center of Mass"].rotation_euler[2] = math.radians(degrees)
            arm.pose.bones["BodyControlBoneIK"].location[1] = -5.0
            bpy.context.view_layer.update()
            before = facing_degrees(arm)

            _, err = run_op(op, override)
            if err:
                results.append(check("%s at %d deg" % (name, degrees), False, err))
                continue

            delta = (facing_degrees(arm) - before + 180.0) % 360.0 - 180.0
            results.append(close("%s keeps facing at %d deg" % (name, degrees),
                                 delta, 0.0, 0.1, " deg"))

    # With Auto-Key off these buttons should only reposition bones.
    enter_pose_mode(arm)
    clear_pose(arm)
    if arm.animation_data:
        arm.animation_data_clear()
    if arm.data.animation_data:
        arm.data.animation_data_clear()
    bpy.context.scene.tool_settings.use_keyframe_insert_auto = False
    run_op(bpy.ops.rig.reset, override)
    keys = len(list(action_fcurves(arm))) + len(list(action_fcurves(arm.data)))
    results.append(check("Auto-Key off leaves no keyframes", keys == 0,
                         "%d f-curves created" % keys))

    return results
