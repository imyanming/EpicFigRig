# -*- coding: utf-8 -*-
"""Accessory Snapping: Left Hand / Right Hand / Head.

These use a COPY_TRANSFORMS constraint and let Blender do the maths, so they
never had the world-vs-local coordinate bug that hit the Master Bone
operators. They are covered here mainly to keep it that way.

Note the deliberate behaviour, confirmed by the author's tutorial: snapping
does NOT parent the accessory. The visual transform is baked on the current
frame and the constraint influence is keyed back to 0, so the object stays put
afterwards instead of following the hand. Use the Dynamic Parent add-on for a
held prop. A test asserting it *does* follow would be asserting a bug.
"""

import bpy

from harness import check, clear_pose, enter_pose_mode, get_rig, run_op, world_of

CASES = (
    ("snap_right.add", "Right Hand Snap Bone"),
    ("snap_left.add", "Left Hand Snap Bone"),
    ("snap_head.add", "Head Accessory"),
)

FRAME = 10
FAR_AWAY = (20.0, 20.0, 20.0)


def _operator(idname):
    module, _, func = idname.partition(".")
    return getattr(getattr(bpy.ops, module), func)


def _make_accessory(name):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = FAR_AWAY
    return obj


def run(override):
    arm = get_rig()
    scene = bpy.context.scene
    results = []

    for idname, bone in CASES:
        enter_pose_mode(arm)
        clear_pose(arm)
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        accessory = _make_accessory("ACC_" + idname.replace(".", "_"))
        for obj in bpy.data.objects:
            obj.select_set(False)
        accessory.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = accessory
        scene.frame_set(FRAME)
        start = accessory.matrix_world.to_translation().copy()

        _, err = run_op(_operator(idname), override)
        if err:
            results.append(check("%s runs" % idname, False, err))
            continue

        bpy.context.view_layer.update()
        landed = accessory.matrix_world.to_translation()
        target = world_of(arm, bone)
        results.append(check("%s snaps onto %s" % (idname, bone),
                             (landed - target).length < 0.01,
                             "%.4f from the bone" % (landed - target).length))

        scene.frame_set(FRAME - 1)
        bpy.context.view_layer.update()
        back = accessory.matrix_world.to_translation()
        results.append(check("%s leaves the previous frame alone" % idname,
                             (back - start).length < 0.6,
                             "%.3f from where it started" % (back - start).length))
        scene.frame_set(FRAME)

    return results
