# -*- coding: utf-8 -*-
"""Pivot Foot Switch: Left / Right / Reset Pivot.

These move the Pivot bone under the chosen foot so the character can rotate
around it. Two things used to go wrong and neither was obvious from the
viewport:

  * the operators borrow the 3D cursor as scratch space -- snap it to a helper
    bone, then snap the Pivot bone to it -- and never put it back, so the
    user's cursor silently moved every press;
  * Snap Master Bone carried an unpaired frame_set(+1), so the current frame
    crept forward one step on every press.
"""

import bpy

from harness import (check, clear_pose, enter_pose_mode, get_rig, run_op,
                     world_of)

CURSOR_LOC = (1.0, 2.0, 3.0)
CURSOR_ROT = (0.1, 0.2, 0.3)

# Left -> 1, Right -> 0, Reset -> 0. The property drives the Copy Location
# constraints on "Body rock control.001".
EXPECTED_SLIDE = {"pivot.left": 1, "pivot.right": 0, "reset.pivot": 0}


def run(override):
    arm = get_rig()
    scene = bpy.context.scene
    scene.tool_settings.use_keyframe_insert_auto = False
    results = []

    for name, op in (("pivot.left", bpy.ops.pivot.left),
                     ("pivot.right", bpy.ops.pivot.right),
                     ("reset.pivot", bpy.ops.reset.pivot)):
        enter_pose_mode(arm)
        clear_pose(arm)
        scene.cursor.location = CURSOR_LOC
        scene.cursor.rotation_euler = CURSOR_ROT
        frame_before = scene.frame_current
        body_before = world_of(arm, "Center of Mass").copy()

        _, err = run_op(op, override)
        if err:
            results.append(check("%s runs" % name, False, err))
            continue

        moved_cursor = max(abs(a - b) for a, b in
                           zip(CURSOR_LOC, scene.cursor.location))
        turned_cursor = max(abs(a - b) for a, b in
                            zip(CURSOR_ROT, scene.cursor.rotation_euler))
        results.append(check("%s restores the 3D cursor" % name,
                             moved_cursor < 1e-4 and turned_cursor < 1e-4,
                             "loc off by %.6f, rot off by %.6f"
                             % (moved_cursor, turned_cursor)))
        results.append(check("%s leaves the frame alone" % name,
                             scene.frame_current == frame_before,
                             "frame %d -> %d" % (frame_before, scene.frame_current)))

        slide = arm.data.get("Pivot Slide")
        results.append(check("%s sets Pivot Slide" % name,
                             slide == EXPECTED_SLIDE[name],
                             "Pivot Slide = %s (want %s)"
                             % (slide, EXPECTED_SLIDE[name])))

        # Switching the pivot foot should not lift or drop the character.
        moved_body = abs(world_of(arm, "Center of Mass").z - body_before.z)
        results.append(check("%s does not change height" % name,
                             moved_body < 0.05,
                             "body moved %.4f vertically" % moved_body))

    # pivot.left should slide the Pivot bone sideways by roughly the distance
    # between the feet, and purely horizontally.
    enter_pose_mode(arm)
    clear_pose(arm)
    before = world_of(arm, "Pivot").copy()
    _, err = run_op(bpy.ops.pivot.left, override)
    if not err:
        delta = world_of(arm, "Pivot") - before
        results.append(check("pivot.left moves the Pivot bone horizontally",
                             delta.length > 1.0 and abs(delta.z) < 0.1,
                             "moved (%.2f, %.2f, %.2f)" % (delta.x, delta.y, delta.z)))

    return results
