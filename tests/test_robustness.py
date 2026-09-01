# -*- coding: utf-8 -*-
"""Failure behaviour on scenes that are not an EpicFigRig.

The bar this fork set for itself: when something is wrong, the user gets one
clear sentence, and nothing is touched. Before the defensive layer, pressing
the nine operators across four bad starting states raised raw Python
tracebacks in 21 of 32 cases.

Every one of these presses must come back CANCELLED with a readable message.
A traceback in the console counts as a failure even if nothing crashed.
"""

import bpy

from harness import check

OPERATORS = (
    ("snap_left.add", lambda: bpy.ops.snap_left.add()),
    ("snap_right.add", lambda: bpy.ops.snap_right.add()),
    ("snap_head.add", lambda: bpy.ops.snap_head.add()),
    ("pivot.left", lambda: bpy.ops.pivot.left()),
    ("pivot.right", lambda: bpy.ops.pivot.right()),
    ("reset.pivot", lambda: bpy.ops.reset.pivot()),
    ("rig.reset", lambda: bpy.ops.rig.reset()),
    ("snap.masterbone", lambda: bpy.ops.snap.masterbone()),
    ("auto.rig", lambda: bpy.ops.auto.rig()),
)


def _fresh():
    if bpy.context.mode != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except RuntimeError:
            pass
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _override():
    """Re-found after every scene reset -- read_factory_settings invalidates it."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next(r for r in area.regions if r.type == 'WINDOW')
                return dict(window=window, area=area, region=region)
    return None


def _press_all(label, results):
    override = _override()
    for name, call in OPERATORS:
        try:
            if override:
                with bpy.context.temp_override(**override):
                    outcome = call()
            else:
                outcome = call()
            detail = "returned %s" % (outcome,)
            ok = True
        except Exception as exc:                  # noqa: BLE001
            text = str(exc)
            ok = "Traceback" not in text
            detail = ("raw traceback" if not ok
                      else text.replace("\n", " ")[:60])
        results.append(check("%s / %s" % (label, name), ok, detail))


def run(override):
    results = []

    _fresh()
    _press_all("empty scene", results)

    _fresh()
    ov = _override()
    if ov:
        with bpy.context.temp_override(**ov):
            bpy.ops.mesh.primitive_cube_add()
    _press_all("cube only", results)

    _fresh()
    ov = _override()
    if ov:
        with bpy.context.temp_override(**ov):
            bpy.ops.object.armature_add()
            bpy.context.view_layer.objects.active.name = "NotEpicFig"
            bpy.ops.object.mode_set(mode='POSE')
    _press_all("plain armature in pose mode", results)

    _fresh()
    ov = _override()
    if ov:
        with bpy.context.temp_override(**ov):
            bpy.ops.object.armature_add()
            bpy.ops.mesh.primitive_cube_add()
            cube = bpy.context.view_layer.objects.active
            for obj in bpy.data.objects:
                obj.select_set(True)
            bpy.context.view_layer.objects.active = cube
    _press_all("armature + mesh selected", results)

    return results
