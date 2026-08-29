# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

#=============================================================================
# MODIFIED VERSION -- this is not the original file.
#
# Modified in 2026 to run on Blender 4.2 / 5.0, and to fix a number of bugs
# that predate this fork. The original is EpicFigRig v1.0.2 (2022, targeting
# Blender 2.83) by the authors named below:
#
#     https://github.com/BlenderBricks/EpicFigRig
#
# Upstream is unmaintained as of 2022 and is not responsible for anything in
# this build -- please do not send them problems that originate here.
#
# Every change is written up, with the measurements behind it, in:
#     COMPAT_NOTES.md   -- Blender API breakage and how this file copes
#     DESIGN_INTENT.md  -- what the original author intended, and where this
#                          fork deliberately departs from it
#
# Distributed under the same GNU GPL v3-or-later as the original.
#=============================================================================

#add-on info

bl_info = {
    "name": "The EpicFigRig",
    # Original authors first; the fork line is required by GPL-3.0 5(a).
    "author": ("Jambo, Owenator Productions, Golden Ninja Ben, IX Productions "
               "and Citrine's Animations; Blender 4.2/5.0 compatibility fork "
               "2026 by LIN YANMING"),
    "version": (1, 0, 21),
    "blender": (4, 2, 0),
    "location": "View3D > Add > Mesh > New Object",
    "description": "An Epic Minifigure Rig",
    "wiki_url": "",
    "category": "Animation",
}

#=============================================================================
# DEFENSIVE COMPATIBILITY LAYER (added v1.0.12)
#
# Blender removes API without warning (4.0 took the bone layers, 5.0 took
# Bone.select). We cannot predict what goes next and we do not try to. The
# goal here is narrower and achievable: when something this addon depends on
# disappears, the user gets a sentence telling them what broke -- instead of a
# raw traceback, or worse, a silently wrong result like the character drifting
# into the sky. See COMPAT_NOTES.md for the running history.
#=============================================================================

import math
import traceback as _traceback

# Blender versions this addon has actually been exercised against.
COMPAT_TESTED_VERSIONS = ("2.83 (original upstream)", "4.2", "5.0.1")
# Warn above this. Bump it only after actually testing on a newer Blender.
COMPAT_TESTED_MAX = (5, 1)
# The 2022 addon this build is patched from. Kept for attribution and for
# anyone tracing where the code came from -- it is NOT a bug tracker for this
# build. Upstream has been unmaintained since 2022 and knows nothing about any
# of the changes here, so sending people there would waste their time and the
# original author's.
UPSTREAM_URL = "https://github.com/BlenderBricks/EpicFigRig"

# Where someone hitting a problem in THIS build should actually look. These two
# files ship next to __init__.py, so they are available offline and always
# describe the exact code they were packaged with.
LOCAL_NOTES = "COMPAT_NOTES.md and DESIGN_INTENT.md (next to this addon)"

# The rig source files AutoRig appends from. They have to sit next to this
# script, which is exactly what the Extensions installer does not guarantee.
REQUIRED_BLEND_FILES = ("Append.blend", "Append_Child.blend", "Cape_Rig.blend")

_API_PROBLEMS = None


class EpicFigRigError(Exception):
    """A failure we understand well enough to explain in one sentence."""


def _rna_has(rna_type, prop_name):
    """Does this Blender still expose `prop_name` on `rna_type`?

    NOTE: hasattr() on the *type* is the wrong test and silently reports
    False for properties that work perfectly well -- RNA properties are not
    Python class attributes. Verified on 5.0.1:
        hasattr(bpy.types.PoseBone, "select")            -> False  (wrong)
        "select" in PoseBone.bl_rna.properties           -> True   (right)
    The same probe correctly reports that Bone.select really is gone in 5.0
    ("select" in Bone.bl_rna.properties -> False), which is the removal that
    broke this addon in the first place."""
    try:
        return prop_name in rna_type.bl_rna.properties
    except Exception:
        return False


def check_blender_api(force=False):
    """Verify the Blender APIs this addon leans on still exist.

    Returns a list of human-readable problem strings; empty means fine. Each
    entry names the API that vanished, so a future breakage is identifiable
    from the error bar alone. Cached after the first call."""
    global _API_PROBLEMS
    if _API_PROBLEMS is not None and not force:
        return _API_PROBLEMS

    problems = []

    # Bone selection. Blender 5.0 removed Bone.select; we use PoseBone.select.
    if not _rna_has(bpy.types.PoseBone, "select"):
        problems.append(
            "This Blender has no 'pose.bones[x].select'. Blender 5.0 already "
            "removed the older 'data.bones[x].select'; if the pose-bone one is "
            "gone too, a newer Blender has moved bone selection again and this "
            "addon needs updating. Please report this to the maintainer.")

    # Bone collections (4.0+), with the pre-4.0 layers bitmask as fallback.
    if not (_rna_has(bpy.types.Armature, "collections")
            or _rna_has(bpy.types.Armature, "layers")):
        problems.append(
            "This Blender has neither 'armature.collections' (4.0+) nor the "
            "legacy 'armature.layers'. The pivot helper bones cannot be shown "
            "or hidden. Please report this to the maintainer.")

    # transform.translate signature (5.0 rejected the old legacy kwargs).
    try:
        translate_props = bpy.ops.transform.translate.get_rna_type().properties.keys()
        for needed in ("value", "orient_type"):
            if needed not in translate_props:
                problems.append(
                    "bpy.ops.transform.translate no longer accepts '%s'. "
                    "Resetting the IK legs would compute the wrong result. "
                    "Please report this to the maintainer." % needed)
    except Exception:
        problems.append(
            "Could not inspect the parameters of bpy.ops.transform.translate -- "
            "Blender's operator API may have changed. Please report this to "
            "the maintainer.")

    _API_PROBLEMS = problems
    return problems


def get_pose_bone(armature_obj, name, operator_self=None):
    """Look up one pose bone by name, explaining clearly if it is missing."""
    pb = None
    if armature_obj is not None and getattr(armature_obj, "pose", None) is not None:
        pb = armature_obj.pose.bones.get(name)
    if pb is None and operator_self is not None:
        operator_self.report(
            {'ERROR'},
            "Bone '%s' not found. This rig is probably not a standard "
            "EpicFigRig armature, or the bone has been renamed." % name)
    return pb


def _resolve_armature(context, op):
    """Find the armature this operator should act on, or report why not."""
    kind = getattr(op, "epic_kind", "POSE")

    if kind == 'ACCESSORY':
        arms = [o for o in context.selected_objects if o.type == 'ARMATURE']
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if len(arms) != 1 or len(meshes) != 1:
            op.report({'ERROR'},
                      "Select exactly one armature and one accessory object.")
            return None
        return arms[0]

    if kind == 'ARMATURE':
        # Works in any mode: just needs an EpicFigRig armature to act on.
        obj = context.object
        if obj is None or obj.type != 'ARMATURE':
            obj = next((o for o in context.selected_objects
                        if o.type == 'ARMATURE'), None)
        if obj is None:
            op.report({'ERROR'},
                      "Select the EpicFigRig armature first.")
            return None
        return obj

    if context.mode != 'POSE':
        op.report({'ERROR'}, "Make sure you are in Pose Mode")
        return None
    obj = context.object
    if obj is None or obj.type != 'ARMATURE':
        obj = next((o for o in context.selected_objects if o.type == 'ARMATURE'), None)
    if obj is None:
        op.report({'ERROR'},
                  "No active armature found. Select the EpicFigRig armature first.")
        return None
    return obj


def _preflight_rigging(context, op):
    """Preflight for AutoRig, which builds the rig instead of posing one.

    There are no EpicFigRig bones to check yet -- they arrive with the append.
    What can go wrong up front is the selection, the mode, and the rig source
    .blend files not being installed next to this script (which is what
    happens when the addon is installed through the Extensions installer
    instead of "Install Legacy Add-on")."""
    if context.mode != 'OBJECT':
        op.report({'ERROR'},
                  "Switch to Object Mode before rigging a minifigure.")
        return None

    meshes = [o for o in context.selected_objects if o.type == 'MESH']
    if not meshes:
        op.report({'ERROR'},
                  "Select the minifigure part(s) you want to rig (mesh "
                  "objects) first.")
        return None

    missing = [f for f in REQUIRED_BLEND_FILES
               if not os.path.isfile(os.path.join(addon_dirc, f))]
    if missing:
        op.report({'ERROR'},
                  "EpicFigRig cannot find its rig source files: %s. They must "
                  "sit next to __init__.py -- reinstall with 'Install Legacy "
                  "Add-on' (not the Extensions installer), which keeps the "
                  ".blend files alongside the script."
                  % ", ".join(missing))
        return None

    # The author's tutorial says a Mecabricks import arrives under a root
    # Empty which "must be deleted before rigging, as it interferes with the
    # master bone reset scripts". AutoRig does try to remove it -- but its
    # check reads `if obj.parent == True:`, and an Object never compares equal
    # to True, so that branch has never once run (verified). Rather than start
    # silently deleting objects out of the user's scene now, name it and stop.
    parent_empties = sorted({o.parent.name for o in meshes
                             if o.parent is not None and o.parent.type == 'EMPTY'})
    if parent_empties:
        op.report({'ERROR'},
                  "These parts are still parented to an Empty: %s. A Mecabricks "
                  "import brings in a root Empty which has to be deleted before "
                  "rigging -- it interferes with the master bone reset scripts. "
                  "Delete it (keeping the parts), then rig again."
                  % ", ".join("'%s'" % n for n in parent_empties))
        return None

    # Rigging copies each part's material onto the matching smear proxy mesh
    # (e.g. "LlegS"), so a part with no material assigned raises IndexError on
    # material_slots[0]. That happens *after* the rig has been appended, which
    # leaves a half-built mess in the scene -- so refuse up front instead.
    unpainted = [o.name for o in meshes
                 if not o.material_slots or o.material_slots[0].material is None]
    if unpainted:
        op.report({'ERROR'},
                  "These selected parts have no material assigned: %s. "
                  "EpicFigRig copies each part's material onto its smear mesh, "
                  "so every part needs one. Assign a material (or re-import the "
                  "minifigure) and try again."
                  % ", ".join("'%s'" % n for n in unpainted))
        return None

    return True


def _preflight(context, op):
    """Check every bone / object / property the operator is about to touch.

    Doing this up front is the whole point: without it the operator dies
    half-way through, having already moved some bones, and the traceback
    points at whichever line happened to touch the missing name first."""
    if getattr(op, "epic_kind", "POSE") == 'RIGGING':
        return _preflight_rigging(context, op)

    arm_obj = _resolve_armature(context, op)
    if arm_obj is None:
        return None

    global selected_armature
    selected_armature = arm_obj.name

    missing = [n for n in getattr(op, "epic_bones", ())
               if arm_obj.pose.bones.get(n) is None]
    if missing:
        op.report({'ERROR'},
                  "Armature '%s' is missing bones EpicFigRig needs: %s. This "
                  "is probably not a standard EpicFigRig armature, or the "
                  "bones have been renamed."
                  % (arm_obj.name, ", ".join("'%s'" % n for n in missing)))
        return None

    missing_obj = [n for n in getattr(op, "epic_objects", ())
                   if n not in bpy.data.objects]
    if missing_obj:
        op.report({'ERROR'},
                  "The scene is missing objects EpicFigRig needs: %s."
                  % ", ".join("'%s'" % n for n in missing_obj))
        return None

    missing_prop = [n for n in getattr(op, "epic_props", ())
                    if arm_obj.data.get(n) is None]
    if missing_prop:
        op.report({'ERROR'},
                  "Armature '%s' is missing the custom property: %s. This rig "
                  "may not be a complete EpicFigRig."
                  % (arm_obj.name, ", ".join("'%s'" % n for n in missing_prop)))
        return None

    return arm_obj


def _guarded_execute(op, context):
    """Run an operator body behind the API check, the preflight, and a net."""
    problems = check_blender_api()
    if problems:
        for msg in problems:
            op.report({'ERROR'}, msg)
        return {'CANCELLED'}

    arm_obj = None
    if getattr(op, "epic_kind", "POSE") != 'NONE':
        arm_obj = _preflight(context, op)
        if arm_obj is None:
            return {'CANCELLED'}

    # The operators set keyframe_new_interpolation_type to CONSTANT and put it
    # back at the end of _execute_inner -- but that restore is a plain
    # statement, not a finally, so any error part-way through used to leave the
    # preference stuck on CONSTANT. The user then had no idea why every
    # keyframe they placed by hand came out stepped. Guarantee it here.
    _prefs = bpy.context.preferences.edit
    _user_interp = _prefs.keyframe_new_interpolation_type
    _arm_for_keys = arm_obj if isinstance(arm_obj, bpy.types.Object) else None
    _frame = context.scene.frame_current
    _keys_before = _snapshot_keys(_arm_for_keys) if _arm_for_keys else set()

    try:
        result = op._execute_inner(context)
        if _arm_for_keys is not None:
            _relax_new_keys(_arm_for_keys, _frame, _user_interp, _keys_before)
        return result
    except EpicFigRigError as exc:
        op.report({'ERROR'}, str(exc))
        return {'CANCELLED'}
    except Exception as exc:
        # Never let a raw traceback be the user's error message. The full
        # trace still goes to the system console for whoever debugs it.
        _traceback.print_exc()
        op.report(
            {'ERROR'},
            "EpicFigRig hit an unexpected error (%s: %s). You are on Blender "
            "%s; this addon was tested up to %s. Full details are in the "
            "system console -- please report this to the maintainer."
            % (type(exc).__name__, exc,
               ".".join(str(v) for v in bpy.app.version),
               ".".join(str(v) for v in COMPAT_TESTED_MAX)))
        return {'CANCELLED'}
    finally:
        _prefs.keyframe_new_interpolation_type = _user_interp


def _warn_if_untested_blender():
    """Tell the user once, at register time, when they are ahead of us."""
    if tuple(bpy.app.version[:2]) > COMPAT_TESTED_MAX:
        print("[EpicFigRig] WARNING: running on Blender %s. This build has "
              "only been tested on: %s. If the buttons misbehave, that version "
              "gap is the first thing to suspect -- see %s. (Patched from the "
              "original addon at %s, which is unmaintained since 2022 and is "
              "not the place to report problems with this build.)"
              % (".".join(str(v) for v in bpy.app.version),
                 ", ".join(COMPAT_TESTED_VERSIONS), LOCAL_NOTES, UPSTREAM_URL))
        for msg in check_blender_api(force=True):
            print("[EpicFigRig] API CHECK: %s" % msg)


# --- Rig Settings / Smears: drivers that Blender's own changes invalidated ---
#
# These drivers live inside Append.blend, so they cannot be fixed by editing
# this script alone -- they have to be re-pointed on the rig after it is
# appended. Measured on the stock rig in 5.0.1, before repair:
#     layers[2]                            <- ArmIK    BROKEN (4.0 deleted layers)
#     layers[1]                            <- LegIK    BROKEN
#     pose.bones["Head"].custom_shape_scale <- Head Bone Size            BROKEN
#     pose.bones["Head Accessory"].custom_shape_scale <- ...Bone Size    BROKEN
# The IK *behaviour* drivers (constraint influence) were fine all along; what
# broke was the half that shows and hides the matching control bones, and the
# two head-size sliders, which did nothing at all.

# (legacy layer index, bone collection that replaced it, driving property)
LAYER_VISIBILITY_DRIVERS = (
    (2, "Layer 3", "ArmIK"),
    (1, "Layer 2", "LegIK"),
)
# (pose bone, driving property) -- custom_shape_scale became a vector in 3.0
SHAPE_SCALE_DRIVERS = (
    ("Head", "Head Bone Size"),
    ("Head Accessory", "Head Accessory Bone Size"),
)
SMEAR_PROPS = ("LLegSmear", "RLegSmear", "LArmSmear", "RArmSmear")
RIG_SETTING_PROPS = ("ArmIK", "LegIK", "Head Accessory Bone Size",
                     "Head Bone Size", "LepinHands")


def _get_prefs(context):
    """This addon's preferences, or None when it is not installed as an addon
    (e.g. run straight from the text editor or imported by a test script)."""
    try:
        return context.preferences.addons[__name__].preferences
    except (KeyError, AttributeError):
        return None


def _should_keyframe(context):
    """Whether the Master Bone / Pivot operators should record keyframes.

    DELIBERATE DEVIATION FROM UPSTREAM -- not a bug and not a compatibility
    problem, so please do not "fix" it back.

    The original addon inserted keyframes on every press. The author's own
    tutorial is explicit that this is by design: Snap Master Bone snaps the
    master bone to the character's current location "and keyframes it",
    so the animation is preserved while the UI catches up.

    v1.0.10 changed it to follow Blender's normal Auto-Key toggle instead,
    because unconditional keyframing surprised people who were only posing and
    left keys behind on frames they never meant to touch. Auto-Key off means
    the buttons just reposition bones.

    Anyone who wants the upstream behaviour back can tick "Always keyframe"
    in the addon preferences (also shown in the Rig Settings panel) -- no code
    edit required. See DESIGN_INTENT.md."""
    prefs = _get_prefs(context)
    if prefs is not None and getattr(prefs, "always_keyframe", False):
        return True
    return context.scene.tool_settings.use_keyframe_insert_auto


def _ensure_smear_ui_range(arm):
    """Only fill in a slider range when the rig genuinely has none.

    Measured on the stock rig, these properties already arrive from
    Append.blend with proper UI metadata:

        LLegSmear -> {'min': 0, 'max': 9, 'soft_min': 0, 'soft_max': 9}

    so 1..9 is the author's intended smear length, and `slider=True` has always
    had a range to draw against. An earlier version of this fork assumed the
    range was missing and stamped min=0/max=1 over it on every redraw. That
    never actually applied -- the properties are stored as INTEGERS and passing
    float bounds raises

        TypeError: 'float' object cannot be interpreted as an integer

    which a bare `except TypeError: pass` swallowed. Lucky: had it worked it
    would have clamped a 0..9 control down to 0..1 and broken the feature.

    So: never override bounds the rig already declares. Only supply a default
    for a rig that has none, and match the bound types to the stored value."""
    for prop_name in SMEAR_PROPS:
        if prop_name not in arm.keys():
            continue
        try:
            ui = arm.id_properties_ui(prop_name)
            existing = ui.as_dict()
        except (TypeError, KeyError):
            continue
        if existing.get("min") is not None and existing.get("max") is not None:
            continue  # the rig knows its own range -- leave it alone
        as_int = (isinstance(arm[prop_name], int)
                  and not isinstance(arm[prop_name], bool))
        try:
            if as_int:
                ui.update(min=0, max=9, soft_min=0, soft_max=9)
            else:
                ui.update(min=0.0, max=9.0, soft_min=0.0, soft_max=9.0)
        except (TypeError, KeyError):
            pass


def smear_needs_repair(armature_obj):
    """True when this rig's limbs still carry the broken 6-point hide curves.

    Lets the Smears panel say so instead of the user wondering why the real
    arm/leg refuses to disappear. See _set_switch_curve."""
    arm = armature_obj.data
    for obj in bpy.data.objects:
        anim = getattr(obj, "animation_data", None)
        if anim is None:
            continue
        for fcurve in anim.drivers:
            if fcurve.data_path not in ("hide_viewport", "hide_render"):
                continue
            if not any(tgt.id is arm
                       for var in fcurve.driver.variables
                       for tgt in var.targets):
                continue
            if len(fcurve.keyframe_points) != 2:
                return True
    return False


def _yaw_from_matrix(matrix):
    """Rotation about the vertical axis, read straight off the matrix.

    The Master Bone operators only ever transfer yaw -- they write
    MasterBone.rotation_euler[1] and nothing else. The old code got that angle
    from `matrix.to_euler().z`, which breaks at half a turn: Euler
    decomposition is ambiguous there, and Blender expresses a 180 degree yaw
    through the X and Y terms instead, leaving `.z` at roughly zero. Measured
    on the stock rig with Center of Mass rotated:

        30 deg  -> facing preserved, MasterBone.rotY = -0.524   (correct)
        90 deg  -> facing preserved, MasterBone.rotY = -1.571   (correct)
        180 deg -> facing flipped to 0, MasterBone.rotY = -0.000 (WRONG)

    i.e. a character turned to face directly away had the whole rotation
    silently dropped and spun back to front. atan2 on the first column has no
    such singularity, and agrees with to_euler().z everywhere else."""
    basis = matrix.to_3x3()
    try:
        basis.normalize()
    except ValueError:
        return 0.0
    return math.atan2(basis[1][0], basis[0][0])


def _iter_action_fcurves(owner):
    """All driver-free F-curves on an ID, across Blender's action layouts."""
    anim = getattr(owner, "animation_data", None)
    action = getattr(anim, "action", None)
    if action is None:
        return
    try:
        for fcurve in action.fcurves:      # pre-4.4 layout
            yield fcurve
        return
    except AttributeError:
        pass
    for layer in action.layers:            # 4.4+ slotted actions
        for strip in layer.strips:
            try:
                bags = list(strip.channelbags)
            except AttributeError:
                continue
            for bag in bags:
                for fcurve in bag.fcurves:
                    yield fcurve


def _snapshot_keys(armature_obj):
    """Which keyframes already exist, so we can tell apart the ones we add."""
    seen = set()
    for owner in (armature_obj, armature_obj.data):
        for fcurve in _iter_action_fcurves(owner):
            for point in fcurve.keyframe_points:
                seen.add((id(fcurve), round(point.co[0], 4)))
    return seen


def _relax_new_keys(armature_obj, frame, interpolation, before):
    """Give the keys we just wrote on `frame` the user's own interpolation.

    These operators force CONSTANT while they run, because the trick they play
    -- key the old pose one frame back, key the new pose on the current frame
    -- only reads as an instant change if that *boundary* key holds flat.

    The mistake was letting that apply to the current-frame key as well. That
    key is the one that carries motion forward, and a CONSTANT key holds its
    value until the next one, so everything after it stepped instead of
    interpolating. With Auto-Key (or "Always keyframe") on, one press of Reset
    Master Bone wrote 72 CONSTANT keys across 37 curves and the whole
    animation went stop-motion.

    So: frame-1 keeps CONSTANT, the current frame gets whatever the user had.
    Only keys this operator actually created are touched -- anything that was
    already on that frame is left alone."""
    if interpolation == 'CONSTANT':
        return 0                      # the user wants stepped keys anyway
    changed = 0
    for owner in (armature_obj, armature_obj.data):
        for fcurve in _iter_action_fcurves(owner):
            dirty = False
            for point in fcurve.keyframe_points:
                if round(point.co[0], 4) != round(float(frame), 4):
                    continue
                if (id(fcurve), round(point.co[0], 4)) in before:
                    continue          # already existed; not ours to change
                if point.interpolation == 'CONSTANT':
                    point.interpolation = interpolation
                    changed += 1
                    dirty = True
            if dirty:
                fcurve.update()
    return changed


def find_epic_armature(context):
    """The armature a panel should show settings for.

    Prefers the active object, then any selected armature -- so selecting an
    armature together with an accessory (the normal snapping workflow) still
    shows the settings."""
    obj = getattr(context, "active_object", None)
    if obj is not None and obj.type == 'ARMATURE':
        return obj
    for other in getattr(context, "selected_objects", ()):
        if other.type == 'ARMATURE':
            return other
    return None


def _set_switch_curve(fcurve, x=0.0, y=0.0, xx=1.0, yy=1.0):
    """Give a driver F-curve exactly two constant points: (x,y) and (xx,yy).

    The smear system hides a limb by driving its `hide_viewport` /
    `hide_render` from `SmearsTest + <limb>Smear`, and these two points are the
    whole 0->visible / 1->hidden mapping.

    They were being built wrong. `driverCreate()` fetched the curve to stamp
    with `obj.animation_data.drivers[0]` for the viewport driver *and again*
    for the render driver -- index 0 both times -- so the second call appended
    another two points to the first curve instead of setting up its own.
    Measured on a freshly rigged figure: the original body parts came out with
    6 points on `hide_viewport`, and with the points no longer in a sane order
    the curve stopped switching at all:

        LLegSmear=0.0 -> original leg hide_viewport=False | smear mesh hidden
        LLegSmear=1.0 -> original leg hide_viewport=False | smear mesh shown

    i.e. the smear mesh appeared correctly but the real limb never went away,
    leaving both drawn on top of each other. The smear meshes' own curves were
    fine all along (2 points), which is why only the limbs misbehaved."""
    points = fcurve.keyframe_points
    while len(points) > 2:
        points.remove(points[len(points) - 1])
    while len(points) < 2:
        points.add(1)
    points[0].co = (x, y)
    points[0].interpolation = 'CONSTANT'
    points[1].co = (xx, yy)
    points[1].interpolation = 'CONSTANT'
    fcurve.update()


def _add_prop_driver(owner, data_path, index, arm_data, prop_name):
    """Drive `data_path` straight from an armature custom property."""
    try:
        if index is None:
            owner.driver_remove(data_path)
        else:
            owner.driver_remove(data_path, index)
    except Exception:
        pass
    fcurve = (owner.driver_add(data_path) if index is None
              else owner.driver_add(data_path, index))
    drv = fcurve.driver
    drv.type = 'SCRIPTED'
    var = drv.variables.new()
    var.name = "v"
    var.type = 'SINGLE_PROP'
    tgt = var.targets[0]
    tgt.id_type = 'ARMATURE'
    tgt.id = arm_data
    tgt.data_path = '["%s"]' % prop_name
    drv.expression = "v"
    return fcurve


def repair_rig_drivers(armature_obj):
    """Re-point the Rig Settings drivers onto the API that replaced them.

    Safe to run more than once -- each driver is removed before being rebuilt.
    Returns a list of short strings describing what was repaired."""
    arm = armature_obj.data
    repaired = []

    # 4.0: Armature.layers -> Bone Collections. Only rebuild when the old
    # property really is gone, so pre-4.0 Blender keeps its working drivers.
    if not _rna_has(bpy.types.Armature, "layers"):
        for legacy_index, coll_name, prop_name in LAYER_VISIBILITY_DRIVERS:
            if prop_name not in arm.keys():
                continue
            if arm.collections.get(coll_name) is None:
                print("[EpicFigRig] repair: no bone collection %r on %r -- "
                      "cannot restore the %s control visibility. Available: %s"
                      % (coll_name, armature_obj.name, prop_name,
                         [c.name for c in arm.collections]))
                continue
            try:
                arm.driver_remove("layers", legacy_index)
            except Exception:
                pass
            _add_prop_driver(arm, 'collections["%s"].is_visible' % coll_name,
                             None, arm, prop_name)
            repaired.append("%s -> show/hide '%s'" % (prop_name, coll_name))

    # 3.0: custom_shape_scale (float) -> custom_shape_scale_xyz (vector).
    if (not _rna_has(bpy.types.PoseBone, "custom_shape_scale")
            and _rna_has(bpy.types.PoseBone, "custom_shape_scale_xyz")):
        for bone_name, prop_name in SHAPE_SCALE_DRIVERS:
            if prop_name not in arm.keys():
                continue
            if armature_obj.pose.bones.get(bone_name) is None:
                continue
            try:
                armature_obj.driver_remove(
                    'pose.bones["%s"].custom_shape_scale' % bone_name, 0)
            except Exception:
                pass
            for axis in range(3):
                _add_prop_driver(
                    armature_obj,
                    'pose.bones["%s"].custom_shape_scale_xyz' % bone_name,
                    axis, arm, prop_name)
            repaired.append("%s -> '%s' bone size" % (prop_name, bone_name))

    # Smear on/off curves -- see _set_switch_curve for what went wrong. A rig
    # built before that fix has extra points on the limbs' hide_viewport curve
    # and never hides the real arm/leg when its smear is switched on.
    for obj in bpy.data.objects:
        anim = getattr(obj, "animation_data", None)
        if anim is None:
            continue
        for fcurve in anim.drivers:
            if fcurve.data_path not in ("hide_viewport", "hide_render"):
                continue
            # only touch objects this armature actually drives
            driven_by_us = any(tgt.id is arm
                               for var in fcurve.driver.variables
                               for tgt in var.targets)
            if not driven_by_us:
                continue
            if len(fcurve.keyframe_points) != 2:
                _set_switch_curve(fcurve)
                repaired.append("smear switch on '%s' (%s)"
                                % (obj.name, fcurve.data_path))

    # Slider ranges used to come from metadata stored in the .blend; modern
    # Blender needs them declared through id_properties_ui.
    _ensure_smear_ui_range(arm)

    arm.update_tag()
    armature_obj.update_tag()
    return repaired


#=============================================================================
# SYSTEMATIC AUDIT -- v1.0.11
# Every operator below was exercised against the stock rig in Blender 5.0.1,
# driven from a script with a real VIEW_3D context override, and the world
# transforms of the key bones were measured before and after each press
# (Auto-Key off unless stated). Results:
#
#   rig.reset        (Reset Master Bone) -- CORRECT. Moves MasterBone to the
#       character's current position while the character itself holds still
#       (measured +4.991 / +0.009 on a +5 hip offset).
#   snap.masterbone  (Snap Master Bone)  -- WAS BROKEN, fixed in v1.0.11.
#       Moved MasterBone correctly but displaced the character by the same
#       amount, accumulating on every press (4.986 -> 9.978 -> 14.969 ->
#       19.960). It was missing the hip/IK-leg compensation rig.reset does.
#       Confirmed pre-existing: absent from the 2022 original too.
#   pivot.left / pivot.right / reset.pivot -- CORRECT. 3D cursor location and
#       rotation both restored, no current-frame drift, "Pivot Slide" ends at
#       1 / 0 / 0 respectively.
#   snap_right.add / snap_left.add / snap_head.add -- CORRECT. Each snaps its
#       object onto the target bone to within 0.000, and the object returns to
#       its original place on the previous frame. These use a COPY_TRANSFORMS
#       constraint rather than manual matrix maths, so they never had the
#       world-vs-local coordinate bug that hit the Master Bone operators.
#       By design the accessory does NOT keep following the hand afterwards:
#       the visual transform is baked on the current frame and the constraint
#       influence is keyed back to 0. Snap once per frame, not a parent.
#       CONFIRMED by the author's tutorial: accessory snapping deliberately
#       does not parent. Use the Dynamic Parent add-on for a held prop, or
#       parent a hat manually to the "Head Accessory" bone. Do not "fix" this.
#
# Deliberately NOT changed:
#   The sideways (local X) hip axis is locked on this rig -- BodyControlBoneIK
#   is lock_location=(True,False,False), both foot IK bones (True,False,True).
#   A sideways hip offset is therefore unreachable through the UI, so the
#   Master Bone operators only compensate the forward/back axis, as the
#   original author intended.
#=============================================================================

selected_armature = "FinishedRig"

import os
import bpy, mathutils
from bpy.props import BoolProperty
from bpy.types import PropertyGroup, Panel, Scene

addon_dirc = os. path .dirname (os .path .realpath (__file__))

#COMPAT: Blender 4.0 replaced the old 32-slot Armature.layers bitmask with
#named Bone Collections. This addon only ever toggled layer index 18 (the
#hidden pivot-helper layer). On file load, Blender auto-converts non-empty
#layers into collections named "Layer N" (1-indexed), so layer 18 usually
#becomes "Layer 19" -- but that shifts if any earlier layer had zero bones
#in it. If pivot switching silently does nothing on your rig, open the
#Armature Data Properties > Bone Collections panel (or run
#`print([c.name for c in bpy.context.object.data.collections])` in the
#Python console) to find the real name and update PIVOT_BONECOLL_NAME below.
PIVOT_LAYER_INDEX = 18
PIVOT_BONECOLL_NAME = "Layer 19"

def set_pivot_helper_visible(armature_obj, state):
    """Show/hide the hidden pivot-helper bones.

    Purely cosmetic: the pivot operators use it to reveal a helper bone long
    enough to snap the 3D cursor to it. If it fails there is nothing to
    correct in the pose, so we warn on the console and let the operator carry
    on rather than aborting a transform that is already half applied."""
    arm = getattr(armature_obj, "data", None)
    if arm is None:
        print("[EpicFigRig] set_pivot_helper_visible: no armature data on %r"
              % getattr(armature_obj, "name", armature_obj))
        return False

    try:
        if hasattr(arm, "collections"):
            # Blender 4.0+: Bone Collections API
            coll = arm.collections.get(PIVOT_BONECOLL_NAME)
            if coll is None:
                print("[EpicFigRig] Bone Collection '%s' not found on '%s'. "
                      "Update PIVOT_BONECOLL_NAME in __init__.py -- available: %s"
                      % (PIVOT_BONECOLL_NAME, armature_obj.name,
                         [c.name for c in arm.collections]))
                return False
            coll.is_visible = state
            return True

        if hasattr(arm, "layers"):
            # Blender <4.0: legacy layer bitmask
            arm.layers[PIVOT_LAYER_INDEX] = state
            return True

        print("[EpicFigRig] This Blender has neither armature.collections nor "
              "armature.layers -- the pivot helper bones cannot be toggled. "
              "Please report this to the maintainer.")
        return False
    except Exception as exc:
        print("[EpicFigRig] Could not toggle the pivot helper bones (%s: %s). "
              "Please report this to the maintainer." % (type(exc).__name__, exc))
        return False

#PANELS

class EpicFigRigPanel(bpy.types.Panel):
    
    bl_label = "The EpicFigRig"
    bl_idname = "EPIC_FIGRIG_PT_PANEL"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EpicFigRig'
    
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        row = box.row()
        row.operator("wm.url_open", text="User Manual", icon= 'URL', emboss= False).url = "https://docs.google.com/document/d/1wWlGkeNHBnmPA1siEARibdjcdEdBDNlHe-tcdELbq8M/edit?usp=sharing"
        row = layout.row()
        row.label(text= "Active: Object:")
        #row = layout.row()
        #row.label(text= bpy.context.object.data.name, icon= 'OUTLINER_OB_ARMATURE') #emboss= False)
        
        row = layout.row()
        row.operator('auto.rig')

class EpicButtons(bpy.types.Panel):
    
    bl_label = "Epic Buttons"
    bl_idname = "EPIC_PT_BUTTONS"
    bl_parent_id = "EPIC_FIGRIG_PT_PANEL"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EpicFigRig'
    
    def draw(self, context):
        layout = self.layout

        row = layout.row()
        
        row = layout.row()
        row.label(text= "Accessory Snapping:", icon= 'SNAP_ON')
        row = layout.row(align=True)
        row.operator('snap_left.add')
        row.operator('snap_right.add')
        row = layout.row(align=True)
        row.operator('snap_head.add')
        #pivot buttons
        layout.label(text="Pivot Foot Switch:", icon= 'ARROW_LEFTRIGHT')
        row = layout.row(align=True)
        row.operator('pivot.left')
        row.operator('pivot.right')
        row = layout.row()
        row.operator('reset.pivot')
        row = layout.row(align=True)
        row.label(text= "Master Bone Control:")
        row = layout.row()
        row.operator('rig.reset')
        row = layout.row()
        row.operator('snap.masterbone')

        
class RigSettings(bpy.types.Panel):

    bl_label = "Rig Settings"
    bl_idname = "RIG_PT_SETTINGS"
    bl_parent_id = "EPIC_FIGRIG_PT_PANEL"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EpicFigRig'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        # The old version worked out the armature by looping over the whole
        # selection and keeping whatever came last, which meant: an
        # UnboundLocalError with nothing selected, "(Select an Armature)" when
        # an armature *and* an accessory were selected (the normal accessory
        # workflow), and a KeyError on any armature without these properties.
        arm_obj = find_epic_armature(context)
        if arm_obj is None:
            layout.row().label(text="(Select an Armature for Settings)")
            return

        global selected_armature
        selected_armature = arm_obj.name
        arm = arm_obj.data

        missing = [p for p in RIG_SETTING_PROPS if p not in arm.keys()]
        if missing:
            col = layout.column()
            col.label(text="Not an EpicFigRig armature", icon='ERROR')
            col.label(text="missing: %s" % ", ".join(missing[:3]))
            return

        layout.row().prop(arm, '["ArmIK"]', slider=True)

        # The arm-socket options only mean anything while the arms are on IK.
        if arm["ArmIK"] != 0:
            for prop_name in ("IK Arm Socket Lock", "IK Stick"):
                if prop_name in arm.keys():
                    layout.row().prop(arm, '["%s"]' % prop_name, slider=True)

        for prop_name in ("LegIK", "Head Accessory Bone Size",
                          "Head Bone Size", "LepinHands"):
            layout.row().prop(arm, '["%s"]' % prop_name, slider=True)

        prefs = _get_prefs(context)
        if prefs is not None:
            layout.separator()
            layout.prop(prefs, "always_keyframe")

        layout.separator()
        layout.operator('rig.repair_drivers', icon='DRIVER')


#BUTTONS 

#AutoRig
class AutoRig(bpy.types.Operator):
    
    bl_label = "Rig Selected Minifigure"
    bl_idname = 'auto.rig'
    
    # --- declared up front so a bad starting state fails cleanly ---
    # RIGGING rather than POSE: this operator builds the rig, so there are
    # no EpicFigRig bones to check yet. What _preflight_rigging checks is
    # the mode, the selection, and that the rig source .blend files are
    # actually installed next to this script.
    epic_kind = 'RIGGING'

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        
        
        child = True

        def driverCreate(context, object, armatures, path, Bo_nus, path2, expression, x, y, xx, yy):
            obj = bpy.data.objects[object]
            dwive = obj.driver_add("hide_viewport")
            driver = dwive.driver
            
            var = driver.variables.new()
            
            var.type = 'SINGLE_PROP'
            var.name = "hide"

            target = var.targets[0]

            target.id_type = 'ARMATURE'

            b = bpy.data.armatures[armatures]

            target.id = b

            target.data_path = path

            #numba 2
            if Bo_nus == True:
                var = driver.variables.new()
            
                var.type = 'SINGLE_PROP'
                var.name = "hide2"

                target = var.targets[0]

                target.id_type = 'ARMATURE'

                b = bpy.data.armatures[armatures]

                target.id = b

                target.data_path = path2

            driver.expression = expression

            # Use the F-curve driver_add() just handed us. The original code
            # said obj.animation_data.drivers[0] here AND for hide_render
            # below, so both stamps landed on the same curve.
            _set_switch_curve(dwive, x, y, xx, yy)

            #next

            obj2 = bpy.data.objects[object]
            dwive2 = obj2.driver_add("hide_render")
            driver2 = dwive2.driver
            
            var2 = driver2.variables.new()
            
            var2.type = 'SINGLE_PROP'
            var2.name = "hide"

            target2 = var2.targets[0]

            target2.id_type = 'ARMATURE'

            b = bpy.data.armatures[armatures]

            target2.id = b

            target2.data_path = path

            #numba 2
            if Bo_nus == True:
                var2 = driver2.variables.new()
            
                var2.type = 'SINGLE_PROP'
                var2.name = "hide2"

                target2 = var2.targets[0]

                target2.id_type = 'ARMATURE'

                b = bpy.data.armatures[armatures]

                target2.id = b

                target2.data_path = path2

            driver2.expression = expression

            _set_switch_curve(dwive2, x, y, xx, yy)
        
        #remove empty
        # DEAD CODE: `obj.parent` is an Object, never equal to True, so this
        # has never executed. Left as the author wrote it -- the leftover
        # Empty is now caught by _preflight_rigging() and reported instead of
        # being deleted behind the user's back.
        if bpy.context.selected_objects[0].parent == True:

            empty_name = bpy.context.selected_objects[0].parent.name
            empty = bpy.data.objects[empty_name]
            
            bpy.data.objects.remove(empty)

        def append_normal():
            path = addon_dirc + "/Append.blend/Collection/"
            object_name = "The EpicFigRig"
            bpy.ops.wm.append(filename = object_name, directory = path)

        def append_child():
            path = addon_dirc + "/Append_Child.blend/Collection/"
            object_name = "The EpicFigRig"
            bpy.ops.wm.append(filename = object_name, directory = path)

        def append_cape():
            path = addon_dirc + "/Cape_Rig.blend/Collection/"
            object_name = "CapeRig"
            bpy.ops.wm.append(filename = object_name, directory = path)

        leg_l = ["3817", "20926", "24083", "37364p2"]
        leg_r = ["3816", "20932", "24082", "37364p1", "2532"]
        head_epic = ["24581", "3626", "28621", "94590", "28650", "28649", "26683", "93248",
        "30480", "30378", "98103", "64804", "92743", "1735", "24601", "24629", "98365", 
        "98384", "93068", "19729", "20613", "41201", "18828", "65431"]
        arm_r = ["16000", "3818", "62691"]
        arm_l = ["16001", "3819", "62691"]
        torso = ["3814"]
        hand_epic = ["3820", "2531", "9532"]
        child_leg = ["37364","16709", "37679", "41879"]
        child_leg_single = ["16709", "37679", "41879"]
        head_accessory = ["64798", "64807", "85974", "887990", "87991", "87995", "88283", "88286", "92081", "92083", "93217", "93562", "93563", "18228", "99240", "11908", "99930", "99248",
        "98726", "10301", "10166", "10048", "10055", "10066", "11256", "12893", "13768", "13251", "13664", "13785", "13750", "13765", "13766", "15443", "15427", "15491", "15500",
        "15485", "17346", "17630", "18858", "21787", "20688", "20877", "20595", "20597", "20596", "21777", "21268", "21269", "21778", "23186", "23187", "24072", "25775", "28798", "25378",
        "25379", "26139", "25972", "27186", "27385", "27160", "28551", "28144", "28149", "27323", "28664", "28432", "25411", "25412", "25409", "28430", "34316", "25405", "34693", 
        "36060", "36489", "37823", "40938", "3901", "62810", "40239", "3625", "96859", "62711", "6093", "62696", "59363", "95225", "6025", "99245", "92746", "61183", "40240", "98371", "20603", 
        "21788", "21789", "92756", "40233", "24071", "28139", "65425", "35182", "35620", "49362", "92259", "18637", "15675", "18640", "92255", "19196", "65471", "65463", "66912", "3842", "50665", "16599", "30124", "49663", "36293", "93560", "35458",
        "15851", "3834", "90541", "4505", "26079", "4506", "2338", "3844", "3896", "48493",
        "30273", "89520", "4503", "71015", "2544", "2528", "2543", "23973", "30048", "93554",
        "2545", "40235", "18822", "3629", "30167", "61506", "15424", "13565",  "13788", "13746",
        "6131", "4485", "86035", "11303", "93219", "35660", "11258", "3878", "3624", "41334",
        "3898", "30287", "95678", "36933", "62537", "46303", "3833", "16178", "16175", "98289",
        "99254", "43057", "22380", "85975", "90386", "98381", "30370", "61189", "11217", "15308",
        "30369", "23947", "20904", "20905", "20950", "98119", "21829", "30561", "16497", "57900",
        "52345", "20908", "20954", "21557", "19916", "19917", "87610", "87571", "60768", "92761",
        "6030", "10051", "10056d1", "13767", "10173", "30171", "15530", "17351", "99244", "25971",
        "18831", "66972", "18819", "24076", "25977", "29575", "35697", "20695", "95674", "95319",
        "13789", "30381", "10113", "27161", "18987", "98729", "27326", "10907", "10908", "28631",
        "20917", "17016", "11620", "10909", "15554", "33862", "18936", "19303", "25264", "19026",
        "65589", "19730", "18962", "98130", "96034", "98133", "19857", "24496", "24504", "40925",
        "65072", "93059", "26007", "98128", "25407", "25742", "25743", "25748", "25113", "25114",
        "28679", "30668", "96204", "18984", "90388", "24073", "19861", "90392", "98366", "25978",
        "15404", "98378", "22425", "13792", "13787", "11265", "30172", "27955", "37038", "10164",
        "34704", "54001", "52684", "93557", "65532", "30926", "67145", "66917", "11420"]

        head_clothing_accessories = ["91190", "64647", "30126", "98379", "12886", "33322",
        "25974", "14045", "25634", "13665", "24131", "44553", "41944", "54568", "87696",
        "87695", "11437", "22411", "88964", "39262", "35183"]

        head_clothing_visors = ["2447", "41805", "23318", "89159", "30170", "6119", "30090", 
        "15446", "2594", "22393", "22395", "22400", "22401", "22394", "23851", "28976",]


        selected_objects = bpy.context.selected_objects
        loc = bpy.context.selected_objects[0]
        
  

        for y in selected_objects:
                if "3814" in y.data.name:
                    loc = y

        child = False 
        for fig in bpy.context.selected_objects:
            
            for num in child_leg:
                if num in fig.data.name:
                #if "37364" in fig.data.name:
                    child = True


        if child == True:
            append_child()
            
        else:
            append_normal()

        

        """ 
        if 1 == 1 in selected_objects:
            append_child()
        else:
            append_normal()
        """
        


        all_objects = bpy.data.objects
        rig = all_objects['Rig']
        arma = bpy.data.objects['Rig']
        arma_edit = arma.data.edit_bones

        
        
        rig.location = loc.location

        collections = bpy.data.collections
        h = collections['BoneShapes']
        h.hide_viewport = True

        

        def parent( Bone_name, Dou_ble, Smear_prop):

            fig.select_set(True)
            fig.data = fig.data.copy()
            if Dou_ble == True:
                driverCreate(bpy.context, fig.name, rig.name, '["SmearsTest"]', True, Smear_prop, "hide + hide2", 0, 0, 1, 1)
            else:
                driverCreate(bpy.context, fig.name, rig.name, '["SmearsTest"]', False, Smear_prop, "hide", 0, 0, 1, 1)


            rig.select_set(True)
            bpy.context.view_layer.objects.active = rig
            rig.data.bones.active = rig.data.bones[Bone_name]
            bpy.ops.object.parent_set(type='BONE', keep_transform=True)
            bpy.ops.object.select_all(action='DESELECT')
            
        
        for fig in selected_objects:

            #CHILD_LEG
            for num in child_leg_single:
                if num in fig.data.name:
                    parent("Torso", False, '["LLegSmear"]')
                    bpy.context.object.data.bones["RightFootIK"].hide = True
                    bpy.context.object.data.bones["LeftFootIK"].hide = True
                    bpy.context.object.data.bones["RightLeg"].hide = True
                    bpy.context.object.data.bones["LeftLeg"].hide = True
                    break

            #LEFT_LEG
            for num in leg_l:
                if num in fig.data.name:
                    parent("LeftLeg", True, '["LLegSmear"]')
                    bpy.data.objects["LlegS"].material_slots[0].material = fig.material_slots[0].material
                    break



            #RIGHT_LEG
            for num in leg_r:
                if num in fig.data.name:
                    parent("RightLeg", True, '["RLegSmear"]')
                    bpy.data.objects["RlegS"].material_slots[0].material = fig.material_slots[0].material
                    break

            #IK_HIP
            if "3815" in fig.data.name:
                parent("Torso", False, '["LLegSmear"]')

            #TORSO
            for num in torso:
                if num in fig.data.name:
                    parent("Torso Rock", False, '["LLegSmear"]')
                    break


            #LEFT_ARM
            for num in arm_l:
                if num in fig.data.name:
                    parent("Left Arm", True, '["LArmSmear"]')
                    bpy.data.objects["LarmS"].material_slots[0].material = fig.material_slots[0].material
                    break

            #RIGHT_ARM
            for num in arm_r:
                if num in fig.data.name:
                    parent("Right Arm", True, '["RArmSmear"]')
                    bpy.data.objects["RarmS"].material_slots[0].material = fig.material_slots[0].material
                    break
            
            #HEAD
            for num in head_epic:
                if num in fig.data.name:
                    parent("Head", False, '["LLegSmear"]')
                    break

            #HEAD_ACCESSORY
            for num in head_accessory:
                if num in fig.data.name:
                    parent("Head Accessory", False, '["LLegSmear"]')
                    break
            
            #HEAD_CLOTHING.ACCESSORIES
            for num in head_clothing_accessories:
                if num in fig.data.name:
                    parent("Head Accessory", False, '["LLegSmear"]')
                    break

            #HEAD_CLOTHING.VISORS
            for num in head_clothing_visors:
                if num in fig.data.name:
                    parent("Head Accessory", False, '["LLegSmear"]')
                    break
            
            if "50231" in fig.data.name:
                append_cape()
                rigcape = bpy.data.objects['CapeRig']
                rigcape.location = fig.location

                LFarm = rigcape.pose.bones['LL'].constraints['Transformation']

                LFarm.target = rig
                LFarm.subtarget = "Left Arm"

                LFarm2 = rigcape.pose.bones['LL'].constraints['Transformation.001']

                LFarm2.target = rig
                LFarm2.subtarget = "Left Arm Socket Control"

                
                RFarm = rigcape.pose.bones['RR'].constraints['Transformation']

                RFarm.target = rig
                RFarm.subtarget = "Right Arm"

                RFarm2 = rigcape.pose.bones['RR'].constraints['Transformation.001']

                RFarm2.target = rig
                RFarm2.subtarget = "Right Arm Socket Control"

                bpy.data.objects['Cape'].material_slots[0].material = fig.material_slots[0].material

                bpy.ops.object.select_all(action='DESELECT')
                fig.select_set(True)
                bpy.context.view_layer.objects.active = fig
                bpy.ops.object.delete() 
                fig = rigcape
                parent("Torso Rock", False, '["LLegSmear"]')

                bpy.data.objects['Cape'].name = 'FinishedCape'
                bpy.data.objects['CapeRig'].name = 'FinishedCapeRig'
                bpy.data.collections['CapeRig'].name = 'FinishedCapeRig'
                bpy.data.collections['ShapesBones'].hide_viewport = True
                bpy.data.collections['ShapesBones'].hide_render = True
                bpy.data.collections['ShapesBones'].name = 'FinishedShapesBones'



            #HAND
            for num in hand_epic:
                if num in fig.data.name:
                    
                    shortestDist = 100000
                    bpy.context.view_layer.objects.active = rig
                    # COMPAT: setting .bones.active used to also select the
                    # bone as a side effect on older Blender; 5.x no longer
                    # does that, so selected_pose_bones came back empty and
                    # `handname` was never assigned below. Select explicitly.
                    for b in rig.pose.bones:
                        b.select = False
                    rig.pose.bones['Left Hand'].select = True
                    rig.pose.bones['Right Hand'].select = True
                    rig.data.bones.active = rig.data.bones['Right Hand']
                    bpy.ops.object.posemode_toggle()
                    here = bpy.context.selected_pose_bones
                    bpy.ops.object.posemode_toggle()

                    if not here:
                        print(f"[EpicFigRig] Could not find 'Left Hand'/'Right Hand' "
                              f"selected on '{rig.name}' for part '{fig.name}'; skipping hand snap.")
                        continue

                    for x in here:
                        hand = x.id_data
                        matrix_final = hand.matrix_world @ x.matrix
                        location = matrix_final.translation.xyz
                        
                        handloc = (location - fig.location).length
                        if handloc < shortestDist:
                            shortestDist = handloc
                            handname = x.name

                    if handname == 'Left Hand':
                        fig.select_set(True)
                        bpy.context.view_layer.objects.active = fig
                        bpy.ops.object.modifier_add(type='BOOLEAN')
                        bpy.context.object.modifiers["Boolean"].object = bpy.data.objects["RLBool"]
                        fig.select_set(False)

                        obj = bpy.data.objects[fig.name]
                        dwive = obj.modifiers["Boolean"].driver_add("show_viewport")
                        driver = dwive.driver
                        
                        var = driver.variables.new()
                        
                        var.type = 'SINGLE_PROP'
                        var.name = "hide"

                        target = var.targets[0]

                        target.id_type = 'ARMATURE'

                        b = bpy.data.armatures[rig.name]

                        target.id = b

                        target.data_path = '["LepinHands"]'

                        driver.expression = "hide"

                        #2

                        obj = bpy.data.objects[fig.name]
                        dwive = obj.modifiers["Boolean"].driver_add("show_render")
                        driver = dwive.driver
                        
                        var = driver.variables.new()
                        
                        var.type = 'SINGLE_PROP'
                        var.name = "hide"

                        target = var.targets[0]

                        target.id_type = 'ARMATURE'

                        b = bpy.data.armatures[rig.name]

                        target.id = b

                        target.data_path = '["LepinHands"]'

                        driver.expression = "hide"
                    else:
                        fig.select_set(True)
                        bpy.context.view_layer.objects.active = fig
                        bpy.ops.object.modifier_add(type='BOOLEAN')
                        bpy.context.object.modifiers["Boolean"].object = bpy.data.objects["RHBool"]
                        
                        obj = bpy.data.objects[fig.name]
                        dwive = obj.modifiers["Boolean"].driver_add("show_viewport")
                        driver = dwive.driver
                        
                        var = driver.variables.new()
                        
                        var.type = 'SINGLE_PROP'
                        var.name = "hide"

                        target = var.targets[0]

                        target.id_type = 'ARMATURE'

                        b = bpy.data.armatures[rig.name]

                        target.id = b

                        target.data_path = '["LepinHands"]'

                        driver.expression = "hide"

                        #2

                        obj = bpy.data.objects[fig.name]
                        dwive = obj.modifiers["Boolean"].driver_add("show_render")
                        driver = dwive.driver
                        
                        var = driver.variables.new()
                        
                        var.type = 'SINGLE_PROP'
                        var.name = "hide"

                        target = var.targets[0]

                        target.id_type = 'ARMATURE'

                        b = bpy.data.armatures[rig.name]

                        target.id = b

                        target.data_path = '["LepinHands"]'

                        driver.expression = "hide"
                        
                        fig.select_set(False)

                    parent(handname, False, '["LLegSmear"]')
                    break

        bpy.data.armatures["Rig"].name = "FinishedRig"
        rig.name = "FinishedRig"
        collections["BoneShapes"].name = "FinishedBoneShapes"

        objectsfsmear = bpy.data.objects

        objectsfsmear["LlegS"].name = "FinishedLlegS"
        objectsfsmear["RlegS"].name = "FinishedRlegS"
        objectsfsmear["LarmS"].name = "FinishedLarmS"
        objectsfsmear["RarmS"].name = "FinishedRarmS"
        objectsfsmear["RHBool"].name = "FinishedRHBool"
        objectsfsmear["RLBool"].name = "FinishedRLBool"

        # The Rig Settings drivers come out of Append.blend already broken on
        # modern Blender (see repair_rig_drivers). Fix them on the way out so a
        # freshly rigged character has working ArmIK/LegIK visibility and head
        # size sliders without the user having to know about the repair button.
        for _msg in repair_rig_drivers(rig):
            print("[EpicFigRig] repaired driver: %s" % _msg)
        

        return {'FINISHED'}

#Master Bone   
class ResetMasterBone(bpy.types.Operator):
    
    bl_label = "Reset Master Bone"
    bl_idname = 'rig.reset'
    
    # --- declared up front so a non-EpicFigRig rig fails cleanly ---
    epic_kind = 'POSE'
    epic_bones = ("MasterBone",
                   "Master Bone Snap",
                   "Pivot",
                   "BodyControlBoneIK",
                   "LeftFootIK",
                   "RightFootIK",
                   "Center of Mass")
    epic_objects = ("Master Bone Snap",)
    epic_props = ("Pivot Slide",)

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        bpy.context.object.data.name = bpy.context.object.name
        # COMPAT/FIX: this operator's whole trick (key the old pose one
        # frame back, then key the new pose on the current frame) only
        # reads as an instant "pop" if that boundary keyframe holds its
        # value flat instead of easing into the next one. Without forcing
        # Constant interpolation here, whatever the user's global default
        # happens to be (often Bezier) turns that single-frame gap into a
        # quick slide/bounce.
        _prev_interp = bpy.context.preferences.edit.keyframe_new_interpolation_type
        bpy.context.preferences.edit.keyframe_new_interpolation_type = 'CONSTANT'
        # COMPAT/FIX: this operator used to insert keyframes unconditionally
        # on every press, whether or not you were actually animating. Match
        # normal Blender behaviour instead: only record keys when Auto-Key
        # (the record button on the timeline) is on. With it off this just
        # repositions the bones -- no frame jumping, no keys left behind,
        # nothing to look like a "jump" when scrubbing past this frame.
        _auto_key = _should_keyframe(context)
        if context.mode == 'POSE':
            
        
            if len(context.selected_objects) == 1:
                
                #names selected_armature and selected_object 
                for obj in bpy.context.selected_objects:
                    
                    if obj.type == 'ARMATURE':
                        global selected_armature
                        selected_armature = obj.name
                        

            master_bone_snap = bpy.data.objects[selected_armature].pose.bones["Master Bone Snap"]
            master_bone = bpy.data.objects[selected_armature].data.bones["MasterBone"]
            cur_frame = bpy.context.scene.frame_current
            context = bpy.context
            cur_frame = bpy.context.scene.frame_current
            context = bpy.context
            
        #insert locrot on pivot bone and master bone frame -1 (only if animating)
            if _auto_key:
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1) 
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
                bpy.data.objects[selected_armature].pose.bones["MasterBone"].select = True
                bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].select = True
                bpy.data.objects[selected_armature].pose.bones["LeftFootIK"].select = True
                bpy.data.objects[selected_armature].pose.bones["RightFootIK"].select = True
                bpy.data.objects[selected_armature].pose.bones["Center of Mass"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)
            
        #reset hip loc and height
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["MasterBone"].select = True
            hip_height = bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].location[2]
            hip_rot = bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].rotation_quaternion[1] 
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].location[2] = 0
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].rotation_quaternion[1] = 0
            if _auto_key:
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')
            
        #gets world matrix of the snap bone
            # COMPAT: force the depsgraph to catch up before reading it back.
            # Newer Blender can defer evaluation after the property writes
            # above, so without this the matrix read here (and thus where
            # MasterBone ends up) can lag one step behind -> visible drift
            # that gets worse each time the button is pressed.
            bpy.context.view_layer.update()
            obj = master_bone_snap.id_data
            matrix_final = obj.matrix_world @ master_bone_snap.matrix
            obj2 = master_bone.id_data

        #moves snap empty to snap bone
            obj_empty = bpy.data.objects["Master Bone Snap"]
            obj_empty.matrix_world = matrix_final

        #resets pivot bone locrot
            #bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)
            pivot_rotation = bpy.context.object.pose.bones["Pivot"].rotation_euler[0]
            bpy.data.objects[selected_armature].pose.bones["Pivot"].rotation_euler[0] = 0
            bpy.data.objects[selected_armature].pose.bones["Pivot"].location[0] = 0
            bpy.data.objects[selected_armature].pose.bones["Pivot"].location[1] = 0
            bpy.data.objects[selected_armature].pose.bones["Pivot"].location[2] = 0
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
            # COMPAT/FIX: this insert was missed when the rest of this operator
            # was gated behind Auto-Key -- it still dropped a LocRot key on
            # Pivot on every press with Auto-Key off.
            if _auto_key:
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')
            
        #reset center of mass rotation
            flip_bone_rotation = bpy.context.object.pose.bones["Center of Mass"].rotation_euler[2]
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["Center of Mass"].select = True
            bpy.context.object.pose.bones["Center of Mass"].rotation_euler[2] = 0
            
        #reset IK Hip Bone 
            ik_distance = bpy.context.object.pose.bones["BodyControlBoneIK"].location[1]
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].select = True
            bpy.context.object.pose.bones["BodyControlBoneIK"].location[1] = 0

        #reset IK Legs   
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["LeftFootIK"].select = True
            bpy.data.objects[selected_armature].pose.bones["RightFootIK"].select = True
            # COMPAT: trimmed to the handful of params still valid in 4.x/5.x;
            # the long legacy kwarg list (texture_space, gpencil_strokes,
            # cursor_transform, ...) raised TypeError on newer Blender.
            bpy.ops.transform.translate(value=(0.0, ik_distance, 0.0), orient_type='LOCAL')

        #moves master bone to snap empty
            # COMPAT/FIX: the debug session confirmed it -- obj_empty.location
            # / .rotation_euler are in WORLD space. This addon silently
            # assumed the armature object sits exactly at the world origin
            # (matrix_world == identity), so it read those world values
            # straight into MasterBone's LOCAL pose channels. On a rig placed
            # anywhere else in the scene, every press added one more copy of
            # the armature's own world offset -- exactly the accumulating
            # drift you saw. Fix: convert the empty's transform into the
            # armature object's local space first, then read loc/rot from that.
            _arm_obj = bpy.data.objects[selected_armature]
            _local_matrix = _arm_obj.matrix_world.inverted() @ obj_empty.matrix_world
            _local_loc = _local_matrix.to_translation()
            _local_rot = _local_matrix.to_euler()

            snap_empty_xloc = _local_loc.x
            snap_empty_yloc = _local_loc.y
            snap_empty_zloc = _local_loc.z
            snap_empty_xrot = _local_rot.x
            snap_empty_yrot = _local_rot.y
            # NOTE: not _local_rot.z -- that silently drops a 180 degree
            # turn. See _yaw_from_matrix().
            snap_empty_zrot = _yaw_from_matrix(_local_matrix)

            bpy.data.objects[selected_armature].pose.bones["MasterBone"].location[0] = snap_empty_xloc
            # REVERTED (was v9 "fix #8"): do NOT write this axis. Uncommenting
            # it was wrong -- verified against the actual rig in Blender 5.0.1.
            # MasterBone's rest matrix has local Y = armature -Z, so location[1]
            # is the VERTICAL channel (and inverted: +1 moves the character
            # DOWN 1 unit). The original author commented it out on purpose:
            # this tool is meant to snap ground position + facing only, and the
            # character's height is owned by BodyControlBoneIK (which is why
            # hip_height is saved and restored around this block).
            # Two further reasons the write can never be correct as written:
            #  1. snap_empty_zloc is an ABSOLUTE armature-space Z, but
            #     .location is a pose OFFSET from the rest head. That works for
            #     X/Y only because MasterBone's rest head is at X=0, Y=0 -- its
            #     rest Z is -14.6495, so there is no valid absolute-to-offset
            #     shortcut on this axis.
            #  2. "Master Bone Snap" is parented under MasterBone, so it moves
            #     with whatever this writes. Measured on the stock rig: press 1
            #     read -15.7467 and threw the character +15.75 up (rig is only
            #     ~23 units tall); press 2 then read 0.0 and dropped it back.
            #     That is the up/down flip-flop between Reset and Snap Master
            #     Bone -- it alternates between two states forever instead of
            #     accumulating, which is why it never looked like drift.
            #bpy.data.objects[selected_armature].pose.bones["MasterBone"].location[1] = snap_empty_zloc
            bpy.data.objects[selected_armature].pose.bones["MasterBone"].location[2] = snap_empty_yloc
            bpy.data.objects[selected_armature].pose.bones["MasterBone"].rotation_euler[1] = -snap_empty_zrot #+ 3.14159


        #reset hip height and rot
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].location[2] = hip_height
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].rotation_quaternion[1] = hip_rot

        #insert locrot
            # FIX (v1.0.11): v1.0.9 hoisted this assignment above the Auto-Key
            # block so the property would still be set with Auto-Key off. That
            # was right, but it also meant the frame-1 keyframe below recorded
            # the NEW value (0) instead of the old one, flattening the
            # before/after pop this operator exists to create. Keep the
            # unconditional assignment, but remember the old value and put it
            # back just long enough to key it on frame-1.
            _old_pivot_slide = bpy.data.armatures[selected_armature]["Pivot Slide"]
            bpy.data.armatures[selected_armature]["Pivot Slide"] = 0
            if _auto_key:
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].select = True
                bpy.data.objects[selected_armature].pose.bones["LeftFootIK"].select = True
                bpy.data.objects[selected_armature].pose.bones["RightFootIK"].select = True
                bpy.data.objects[selected_armature].pose.bones["MasterBone"].select = True
                bpy.data.objects[selected_armature].pose.bones["Center of Mass"].select = True
                bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')

                #switch custom property
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
                bpy.data.armatures[selected_armature]["Pivot Slide"] = _old_pivot_slide
                bpy.data.armatures[selected_armature].keyframe_insert(data_path = '["Pivot Slide"]') #, frame = cur_frame -1)
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)
                bpy.data.armatures[selected_armature]["Pivot Slide"] = 0
                bpy.data.armatures[selected_armature].keyframe_insert(data_path = '["Pivot Slide"]') #, frame = cur_frame)

                #update the scene
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)
        else:
            self.report({'ERROR'}, "Make sure you are in Pose Mode")
        

        # COMPAT/FIX: restore whatever interpolation default the user had.
        bpy.context.preferences.edit.keyframe_new_interpolation_type = _prev_interp
        return {'FINISHED'}

class SnapMasterBone(bpy.types.Operator):
    
    bl_label = "Snap Master Bone"
    bl_idname = 'snap.masterbone'
    
    # --- declared up front so a non-EpicFigRig rig fails cleanly ---
    epic_kind = 'POSE'
    epic_bones = ("MasterBone",
                   "Master Bone Snap",
                   "BodyControlBoneIK",
                   "LeftFootIK",
                   "RightFootIK",
                   "Center of Mass")
    epic_objects = ("Master Bone Snap",)

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        bpy.context.object.data.name = bpy.context.object.name 
        # COMPAT/FIX: same interpolation fix as Reset Master Bone -- see
        # the comment there for why this matters.
        _prev_interp = bpy.context.preferences.edit.keyframe_new_interpolation_type
        bpy.context.preferences.edit.keyframe_new_interpolation_type = 'CONSTANT'
        # COMPAT/FIX: only record keys when Auto-Key is on -- see the
        # comment in Reset Master Bone for why. This also happens to
        # sidestep an existing bug further down where the frame counter
        # could end up one frame ahead of where you started.
        _auto_key = _should_keyframe(context)
        if context.mode == 'POSE':

            name_mark = bpy.context.selected_objects[0]

            if len(context.selected_objects) == 1:
                
                #names selected_armature and selected_object 
                for obj in bpy.context.selected_objects:
                    
                    if obj.type == 'ARMATURE':
                        name_mark = obj
                        global selected_armature
                        selected_armature = obj.name
            master_bone_snap = bpy.data.objects[selected_armature].pose .bones["Master Bone Snap"] #context.active_pose_bone
            master_bone = bpy.data.objects[selected_armature].data.bones["MasterBone"]
            cur_frame = bpy.context.scene.frame_current
            context = bpy.context
            cur_frame = bpy.context.scene.frame_current
            context = bpy.context

        #insert locrot on flip bone and master bone frame -1 (only if animating)
            if _auto_key:
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1) 
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["MasterBone"].select = True
                bpy.data.objects[selected_armature].pose.bones["Center of Mass"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)
            
        #reset hip loc and height
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["MasterBone"].select = True
            hip_height = bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].location[2]
            hip_rot = bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].rotation_quaternion[1] 
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].location[2] = 0
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].rotation_quaternion[1] = 0
            if _auto_key:
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')

        #gets world matrix of the snap bone
            # COMPAT: force the depsgraph to catch up before reading it back.
            # Newer Blender can defer evaluation after the property writes
            # above, so without this the matrix read here (and thus where
            # MasterBone ends up) can lag one step behind -> visible drift
            # that gets worse each time the button is pressed.
            bpy.context.view_layer.update()
            obj = master_bone_snap.id_data
            matrix_final = obj.matrix_world @ master_bone_snap.matrix
            obj2 = master_bone.id_data

        #moves snap empty to snap bone
            obj_empty = bpy.data.objects["Master Bone Snap"]
            obj_empty.matrix_world = matrix_final
            
        #reset center of mass rotation
            # COMPAT/FIX: this frame_set(+1) had no matching -1 anywhere in
            # the original code, so every press of this button silently
            # nudged the current frame forward by one -- another
            # contributor to "things keep drifting the more I press it".
            # Only do it (and undo it) when actually keying.
            if _auto_key:
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)
            flip_bone_rotation = bpy.context.object.pose.bones["Center of Mass"].rotation_euler[2]
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["Center of Mass"].select = True
            bpy.context.object.pose.bones["Center of Mass"].rotation_euler[2] = 0
            if _auto_key:
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)

        #reset IK Hip Bone / IK Legs
            # FIX (v1.0.11, systematic audit): this compensation block existed
            # only in ResetMasterBone -- SnapMasterBone never had it, going all
            # the way back to the 2022 original. Both buttons move MasterBone to
            # catch up with where the character actually is (that part IS the
            # intended design: "Master Bone Snap" is parented under
            # BodyControlBoneIK, so the root does not follow the IK controls on
            # its own and these buttons re-sync it). But everything else is
            # parented under MasterBone too, so moving it also carries the body
            # and the feet along. Unless the hip's own forward/back offset is
            # zeroed and the feet are translated back by the same amount, the
            # character is displaced by that offset a second time.
            # Measured on the stock rig, hip pushed +5 forward, Auto-Key off:
            #   rig.reset       -> MasterBone +4.991, character +0.009 (correct)
            #   snap.masterbone -> MasterBone +4.991, character +4.991 (wrong)
            # and it accumulated: 4.986 -> 9.978 -> 14.969 -> 19.960 over three
            # presses. With this block the character now holds still (+0.009),
            # matching rig.reset exactly.
            # NOTE: only location[1] is handled, deliberately. location[0] (the
            # sideways axis) is locked on this rig -- BodyControlBoneIK has
            # lock_location=(True,False,False) and both foot IK bones have
            # (True,False,True) -- so an animator can never produce a sideways
            # hip offset through the UI, and writing to that channel would be
            # silently dropped by the lock while leaving the feet displaced.
            ik_distance = bpy.context.object.pose.bones["BodyControlBoneIK"].location[1]
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].select = True
            bpy.context.object.pose.bones["BodyControlBoneIK"].location[1] = 0
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["LeftFootIK"].select = True
            bpy.data.objects[selected_armature].pose.bones["RightFootIK"].select = True
            bpy.ops.transform.translate(value=(0.0, ik_distance, 0.0), orient_type='LOCAL')

        #moves master bone to snap empty
            # COMPAT/FIX: the debug session confirmed it -- obj_empty.location
            # / .rotation_euler are in WORLD space. This addon silently
            # assumed the armature object sits exactly at the world origin
            # (matrix_world == identity), so it read those world values
            # straight into MasterBone's LOCAL pose channels. On a rig placed
            # anywhere else in the scene, every press added one more copy of
            # the armature's own world offset -- exactly the accumulating
            # drift you saw. Fix: convert the empty's transform into the
            # armature object's local space first, then read loc/rot from that.
            _arm_obj = bpy.data.objects[selected_armature]
            _local_matrix = _arm_obj.matrix_world.inverted() @ obj_empty.matrix_world
            _local_loc = _local_matrix.to_translation()
            _local_rot = _local_matrix.to_euler()

            snap_empty_xloc = _local_loc.x
            snap_empty_yloc = _local_loc.y
            snap_empty_zloc = _local_loc.z
            snap_empty_xrot = _local_rot.x
            snap_empty_yrot = _local_rot.y
            # NOTE: not _local_rot.z -- that silently drops a 180 degree
            # turn. See _yaw_from_matrix().
            snap_empty_zrot = _yaw_from_matrix(_local_matrix)

            bpy.data.objects[selected_armature].pose.bones["MasterBone"].location[0] = snap_empty_xloc
            # REVERTED (was v9 "fix #8"): do NOT write this axis. Uncommenting
            # it was wrong -- verified against the actual rig in Blender 5.0.1.
            # MasterBone's rest matrix has local Y = armature -Z, so location[1]
            # is the VERTICAL channel (and inverted: +1 moves the character
            # DOWN 1 unit). The original author commented it out on purpose:
            # this tool is meant to snap ground position + facing only, and the
            # character's height is owned by BodyControlBoneIK (which is why
            # hip_height is saved and restored around this block).
            # Two further reasons the write can never be correct as written:
            #  1. snap_empty_zloc is an ABSOLUTE armature-space Z, but
            #     .location is a pose OFFSET from the rest head. That works for
            #     X/Y only because MasterBone's rest head is at X=0, Y=0 -- its
            #     rest Z is -14.6495, so there is no valid absolute-to-offset
            #     shortcut on this axis.
            #  2. "Master Bone Snap" is parented under MasterBone, so it moves
            #     with whatever this writes. Measured on the stock rig: press 1
            #     read -15.7467 and threw the character +15.75 up (rig is only
            #     ~23 units tall); press 2 then read 0.0 and dropped it back.
            #     That is the up/down flip-flop between Reset and Snap Master
            #     Bone -- it alternates between two states forever instead of
            #     accumulating, which is why it never looked like drift.
            #bpy.data.objects[selected_armature].pose.bones["MasterBone"].location[1] = snap_empty_zloc
            bpy.data.objects[selected_armature].pose.bones["MasterBone"].location[2] = snap_empty_yloc
            #py.context.object.pose.bones["MasterBone"].rotation_euler[0] = #snap_empty_xrot
            bpy.data.objects[selected_armature].pose.bones["MasterBone"].rotation_euler[1] = -snap_empty_zrot
            #bpy.context.object.pose.bones["MasterBone"].rotation_euler[2] = snap_empty_zrot

            
        #reset hip height and rot
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].location[2] = hip_height
            bpy.data.objects[selected_armature].pose.bones["BodyControlBoneIK"].rotation_quaternion[1] = hip_rot
            
        #insert locrot on flip bone and master bone frame current 
            if _auto_key:
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["MasterBone"].select = True
                bpy.data.objects[selected_armature].pose.bones["Center of Mass"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')

                #update scene
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)

        else:
            self.report({'ERROR'}, "Make sure you are in Pose Mode")
        # COMPAT/FIX: restore whatever interpolation default the user had.
        bpy.context.preferences.edit.keyframe_new_interpolation_type = _prev_interp
        return {'FINISHED'}  

#Pivot
class SwitchPivottoLeft(bpy.types.Operator):
    
    bl_label = "Left"
    bl_idname = 'pivot.left'
    
    # --- declared up front so a non-EpicFigRig rig fails cleanly ---
    epic_kind = 'POSE'
    epic_bones = ("Pivot",
                   "LeftFootIK",
                   "Pivot lock L")
    epic_props = ("Pivot Slide",)

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        # Seeded here because the restore at the end of this method is
        # unconditional; without it the error path raises UnboundLocalError.
        _prev_interp = bpy.context.preferences.edit.keyframe_new_interpolation_type
        if context.mode == 'POSE':
            # COMPAT/FIX: same Constant-interpolation fix as Reset/Snap
            # Master Bone -- this uses the same frame-1/frame pop trick.
            _prev_interp = bpy.context.preferences.edit.keyframe_new_interpolation_type
            bpy.context.preferences.edit.keyframe_new_interpolation_type = 'CONSTANT'
            # COMPAT/FIX: only record keys when Auto-Key is on -- see the
            # comment in Reset Master Bone for why.
            _auto_key = _should_keyframe(context)
            # COMPAT/FIX: this operator borrows the 3D cursor as scratch
            # space (snap cursor to a bone, then snap the bone to the
            # cursor) but never put the cursor back, so every press
            # permanently relocated the user's actual 3D cursor. Save it
            # here and restore it at the end.
            saved_cursor_loc = context.scene.cursor.location.copy()
            saved_cursor_rot = context.scene.cursor.rotation_euler.copy()
            if len(context.selected_objects) == 1:
                
                #names selected_armature and selected_object 
                for obj in bpy.context.selected_objects:
                    
                    if obj.type == 'ARMATURE':
                        global selected_armature
                        selected_armature = obj.name
                        bpy.context.object.data.name = bpy.context.object.name
            

            #insert keyframes on frame -1 (only if animating)
            if _auto_key:
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
                bpy.data.objects[selected_armature].pose.bones["LeftFootIK"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')
                bpy.data.armatures[selected_armature].keyframe_insert(data_path = '["Pivot Slide"]')
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)
            
            #turn on armature layer 18
            set_pivot_helper_visible(bpy.context.object, True)
            
            #reset IK Foot Loc
            bpy.data.objects[selected_armature].pose.bones["LeftFootIK"].location[0] = 0
            bpy.data.objects[selected_armature].pose.bones["LeftFootIK"].location[1] = 0
            bpy.data.objects[selected_armature].pose.bones["LeftFootIK"].location[2] = 0

            #Move Pivot to Left Foot
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["Pivot lock L"].select = True
            # COMPAT/FIX: selecting a bone no longer implies making it
            # active on newer Blender, and snap_cursor_to_selected /
            # snap_selected_to_cursor lean on the active bone. Without this
            # they can silently act on a stale bone left active from
            # earlier in the operator, which is what made Pivot land in
            # the wrong spot instead of on the foot.
            bpy.data.objects[selected_armature].data.bones.active = bpy.data.objects[selected_armature].data.bones["Pivot lock L"]
            #bpy.context.area.ui_type = 'VIEW_3D'
            # COMPAT: same depsgraph-lag issue as Reset/Snap Master Bone --
            # "Pivot lock L" needs to reflect the IK foot reset above before
            # the cursor snap reads its world position.
            bpy.context.view_layer.update()
            bpy.ops.view3d.snap_cursor_to_selected()
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
            bpy.data.objects[selected_armature].data.bones.active = bpy.data.objects[selected_armature].data.bones["Pivot"]
            bpy.ops.view3d.snap_selected_to_cursor(use_offset=True)
            #bpy.context.area.ui_type = 'TEXT_EDITOR' 
            
            #switch custom property
            bpy.data.armatures[selected_armature]["Pivot Slide"] = 1
            if _auto_key:
                bpy.data.armatures[selected_armature].keyframe_insert(data_path = '["Pivot Slide"]')
    
            #turn off layer 18
            set_pivot_helper_visible(bpy.context.object, False)
            
            #insert keyframes
            if _auto_key:
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
                bpy.data.objects[selected_armature].pose.bones["LeftFootIK"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')

                #update scene
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)

            # COMPAT/FIX: put the 3D cursor back where the user had it.
            context.scene.cursor.location = saved_cursor_loc
            context.scene.cursor.rotation_euler = saved_cursor_rot
        else:
            self.report({'ERROR'}, "Make sure you are in Pose Mode")
        

        # COMPAT/FIX: restore whatever interpolation default the user had.
        bpy.context.preferences.edit.keyframe_new_interpolation_type = _prev_interp
        return {'FINISHED'}

class SwitchPivottoRight(bpy.types.Operator):
     
    bl_label = "Right"
    bl_idname = 'pivot.right'
    
    # --- declared up front so a non-EpicFigRig rig fails cleanly ---
    epic_kind = 'POSE'
    epic_bones = ("Pivot",
                   "RightFootIK",
                   "Pivot lock R")
    epic_props = ("Pivot Slide",)

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        # Seeded here because the restore at the end of this method is
        # unconditional; without it the error path raises UnboundLocalError.
        _prev_interp = bpy.context.preferences.edit.keyframe_new_interpolation_type
        if context.mode == 'POSE':
            # COMPAT/FIX: same Constant-interpolation fix as Reset/Snap Master Bone.
            _prev_interp = bpy.context.preferences.edit.keyframe_new_interpolation_type
            bpy.context.preferences.edit.keyframe_new_interpolation_type = 'CONSTANT'
            # COMPAT/FIX: only record keys when Auto-Key is on.
            _auto_key = _should_keyframe(context)
            # COMPAT/FIX: same cursor-scratch-space issue as the Left pivot switch.
            saved_cursor_loc = context.scene.cursor.location.copy()
            saved_cursor_rot = context.scene.cursor.rotation_euler.copy()

            if len(context.selected_objects) == 1:
                
                #names selected_armature and selected_object 
                for obj in bpy.context.selected_objects:
                    
                    if obj.type == 'ARMATURE':
                        global selected_armature
                        selected_armature = obj.name
                        bpy.context.object.data.name = bpy.context.object.name
                        
        #insert keyframes on frame -1 (only if animating)
            if _auto_key:
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
                bpy.data.objects[selected_armature].pose.bones["RightFootIK"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')
                bpy.data.armatures[selected_armature].keyframe_insert(data_path = '["Pivot Slide"]')
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1) 
            
            #turn on layer 18
            set_pivot_helper_visible(bpy.context.object, True)
            bpy.data.objects[selected_armature].pose.bones["RightFootIK"].location[0] = 0
            bpy.data.objects[selected_armature].pose.bones["RightFootIK"].location[1] = 0
            bpy.data.objects[selected_armature].pose.bones["RightFootIK"].location[2] = 0

            #Move to Left Foot
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["Pivot lock R"].select = True
            # COMPAT/FIX: same active-bone issue as the Left pivot switch.
            bpy.data.objects[selected_armature].data.bones.active = bpy.data.objects[selected_armature].data.bones["Pivot lock R"]
            #bpy.context.area.ui_type = 'VIEW_3D'
            # COMPAT: same depsgraph-lag issue as Reset/Snap Master Bone.
            bpy.context.view_layer.update()
            bpy.ops.view3d.snap_cursor_to_selected()
            bpy.ops.pose.select_all(action='SELECT')
            bpy.ops.pose.select_all(action='DESELECT')
            bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
            bpy.data.objects[selected_armature].data.bones.active = bpy.data.objects[selected_armature].data.bones["Pivot"]
            bpy.ops.view3d.snap_selected_to_cursor(use_offset=True)
            #bpy.context.area.ui_type = 'TEXT_EDITOR' 
            
            #switch custom property
            bpy.data.armatures[selected_armature]["Pivot Slide"] = 0
            if _auto_key:
                bpy.data.armatures[selected_armature].keyframe_insert(data_path = '["Pivot Slide"]')
    
            #turn off layer 18
            set_pivot_helper_visible(bpy.context.object, False)
            
            #insert keyframes
            if _auto_key:
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
                bpy.data.objects[selected_armature].pose.bones["RightFootIK"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')

                #update scene
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)

            # COMPAT/FIX: put the 3D cursor back where the user had it.
            context.scene.cursor.location = saved_cursor_loc
            context.scene.cursor.rotation_euler = saved_cursor_rot
        else:
            self.report({'ERROR'}, "Make sure you are in Pose Mode")

        # COMPAT/FIX: restore whatever interpolation default the user had.
        bpy.context.preferences.edit.keyframe_new_interpolation_type = _prev_interp
        return {'FINISHED'}

class ResetPivot(bpy.types.Operator):
    
    bl_label = "Reset Pivot"
    bl_idname = 'reset.pivot'
    
    # --- declared up front so a non-EpicFigRig rig fails cleanly ---
    epic_kind = 'POSE'
    epic_bones = ("Pivot",
                   "RightFootIK")
    epic_props = ("Pivot Slide",)

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        # Seeded here because the restore at the end of this method is
        # unconditional; without it the error path raises UnboundLocalError.
        _prev_interp = bpy.context.preferences.edit.keyframe_new_interpolation_type
        if context.mode == 'POSE':
            # COMPAT/FIX: same Constant-interpolation + Auto-Key gating as
            # the other pivot/master-bone operators -- see Reset Master Bone.
            _prev_interp = bpy.context.preferences.edit.keyframe_new_interpolation_type
            bpy.context.preferences.edit.keyframe_new_interpolation_type = 'CONSTANT'
            _auto_key = _should_keyframe(context)

            if len(context.selected_objects) == 1:
                
                #names selected_armature and selected_object 
                for obj in bpy.context.selected_objects:
                    
                    if obj.type == 'ARMATURE':
                        global selected_armature
                        selected_armature = obj.name
                        bpy.context.object.data.name = bpy.context.object.name
                        
            #insert keyframes on frame -1 (only if animating)
            if _auto_key:
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
                #bpy.data.objects[selected_armature].pose.bones["RightFootIK"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')
                bpy.data.armatures[selected_armature].keyframe_insert(data_path = '["Pivot Slide"]')
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)

            bpy.data.objects[selected_armature].pose.bones["Pivot"].location[0] = 0
            bpy.data.objects[selected_armature].pose.bones["Pivot"].location[1] = 0
            bpy.data.objects[selected_armature].pose.bones["Pivot"].location[2] = 0
            bpy.data.objects[selected_armature].pose.bones["Pivot"].rotation_euler[0] = 0
            bpy.data.objects[selected_armature].pose.bones["RightFootIK"].location[0] = 0
            bpy.data.objects[selected_armature].pose.bones["RightFootIK"].location[1] = 0
            bpy.data.objects[selected_armature].pose.bones["RightFootIK"].location[2] = 0
            bpy.data.armatures[selected_armature]["Pivot Slide"] = 0
            if _auto_key:
                bpy.ops.pose.select_all(action='SELECT')
                bpy.ops.pose.select_all(action='DESELECT')
                bpy.data.objects[selected_armature].pose.bones["Pivot"].select = True
                bpy.data.objects[selected_armature].pose.bones["RightFootIK"].select = True
                bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_LocRot')

                #switch custom property
                bpy.data.armatures[selected_armature].keyframe_insert(data_path = '["Pivot Slide"]')
                bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
                bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)
        else:
            self.report({'ERROR'}, "Make sure you are in Pose Mode")
        # COMPAT/FIX: restore whatever interpolation default the user had.
        bpy.context.preferences.edit.keyframe_new_interpolation_type = _prev_interp
        return {'FINISHED'}

#Snap Bones  
class SnapRight(bpy.types.Operator):
    
    bl_label = "Right Hand"
    bl_idname = 'snap_right.add'
    
    # --- declared up front so a non-EpicFigRig rig fails cleanly ---
    epic_kind = 'ACCESSORY'
    epic_bones = ("Right Hand Snap Bone",)

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        
        cur_frame = bpy.context.scene.frame_current
        context = bpy.context
        
        
        
        if len(context.selected_objects) == 2:
            
            #names selected_armature and selected_object 
            for obj in bpy.context.selected_objects:
                
                if obj.type == 'ARMATURE':
                    global selected_armature
                    selected_armature = obj.name
                    
                    
                if obj.type == 'MESH':
                    global selected_object
                    selected_object = obj.name
                    
                
            #deselects everything
            bpy.data.objects[selected_armature].pose.bones["Right Hand Snap Bone"].select = False
            for obj in bpy.context.selected_objects:
                obj.select_set(False)
            
            #selects adds keyframes to the selected object
            selected_object_keyframe = bpy.data.objects[selected_object].keyframe_insert
            bpy.data.objects[selected_object].select_set(True)
            # FIX: this read scene.objects[0] -- whatever object happens to
            # be first in the scene, which has nothing to do with the
            # accessory being snapped. The trailing comment says what was
            # meant. Two consequences: keyframe_insert_menu below ran with an
            # unrelated active object, and if that object sits in a collection
            # excluded from the view layer the assignment raises outright.
            obj = bpy.data.objects[selected_object]
            bpy.context.view_layer.objects.active = obj
            selected_object_keyframe(data_path='location', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='rotation_euler', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='scale', frame = (cur_frame - 1))
            
            #adds and sets up Copy Transforms Constraint
            # FIX: use the constraint constraints.new() just returned. Looking
            # it up by name fetched the WRONG one whenever the accessory
            # already carried a Copy Transforms constraint (snapping the same
            # prop a second time): new() names the duplicate
            # "Copy Transforms.001", so the lookup re-keyed the stale
            # constraint and left the fresh one behind, unconfigured.
            copy_transform = bpy.data.objects[selected_object].constraints.new(
                'COPY_TRANSFORMS')
            target_constraint = bpy.data.objects[selected_armature]
            subtarget_constraint = bpy.data.objects[selected_armature].data.bones['Right Hand Snap Bone']
            
            copy_transform.target = target_constraint
            copy_transform.subtarget = "Right Hand Snap Bone"
            
            #sets up keyframes for influence
            copy_transform.influence = 0
            copy_transform.keyframe_insert(data_path = "influence", frame = cur_frame - 1)
            copy_transform.influence = 1
            copy_transform.keyframe_insert(data_path = "influence", frame = cur_frame)
            
            #sets up keyframes for Loc Rot
            selected_object_keyframe(data_path='location', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='rotation_euler', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='scale', frame = (cur_frame - 1))
            bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_VisualLocRot')
            copy_transform.influence = 0
            copy_transform.keyframe_insert(data_path = "influence", frame = cur_frame)
            bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
            bpy.context.scene.frame_set(bpy.context.scene.frame_current +1) 



        else:
            self.report({'ERROR'}, "Select both Armature and Object")
            
            
        return {'FINISHED'}
    
class SnapLeft(bpy.types.Operator):
    
    bl_label = "Left Hand"
    bl_idname = 'snap_left.add'
    
    # --- declared up front so a non-EpicFigRig rig fails cleanly ---
    epic_kind = 'ACCESSORY'
    epic_bones = ("Left Hand Snap Bone",)

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        
        cur_frame = bpy.context.scene.frame_current
        context = bpy.context
        
        
        
        if len(context.selected_objects) == 2:
            
            #names selected_armature and selected_object 
            for obj in bpy.context.selected_objects:
                
                if obj.type == 'ARMATURE':
                    global selected_armature
                    selected_armature = obj.name
                    
                    
                if obj.type == 'MESH':
                    global selected_object
                    selected_object = obj.name
                    
                
            #deselects everything
            bpy.data.objects[selected_armature].pose.bones["Left Hand Snap Bone"].select = False
            for obj in bpy.context.selected_objects:
                obj.select_set(False)
            
            #selects adds keyframes to the selected object
            selected_object_keyframe = bpy.data.objects[selected_object].keyframe_insert
            bpy.data.objects[selected_object].select_set(True)
            # FIX: this read scene.objects[0] -- whatever object happens to
            # be first in the scene, which has nothing to do with the
            # accessory being snapped. The trailing comment says what was
            # meant. Two consequences: keyframe_insert_menu below ran with an
            # unrelated active object, and if that object sits in a collection
            # excluded from the view layer the assignment raises outright.
            obj = bpy.data.objects[selected_object]
            bpy.context.view_layer.objects.active = obj
            selected_object_keyframe(data_path='location', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='rotation_euler', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='scale', frame = (cur_frame - 1))
            
            #adds and sets up Copy Transforms Constraint
            # FIX: use the constraint constraints.new() just returned. Looking
            # it up by name fetched the WRONG one whenever the accessory
            # already carried a Copy Transforms constraint (snapping the same
            # prop a second time): new() names the duplicate
            # "Copy Transforms.001", so the lookup re-keyed the stale
            # constraint and left the fresh one behind, unconfigured.
            copy_transform = bpy.data.objects[selected_object].constraints.new(
                'COPY_TRANSFORMS')
            target_constraint = bpy.data.objects[selected_armature]
            subtarget_constraint = bpy.data.objects[selected_armature].data.bones['Left Hand Snap Bone']
            
            copy_transform.target = target_constraint
            copy_transform.subtarget = "Left Hand Snap Bone"
            
            #sets up keyframes for influence
            copy_transform.influence = 0
            copy_transform.keyframe_insert(data_path = "influence", frame = cur_frame - 1)
            copy_transform.influence = 1
            copy_transform.keyframe_insert(data_path = "influence", frame = cur_frame)
            
            #sets up keyframes for Loc Rot
            selected_object_keyframe(data_path='location', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='rotation_euler', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='scale', frame = (cur_frame - 1))
            bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_VisualLocRot')
            copy_transform.influence = 0
            copy_transform.keyframe_insert(data_path = "influence", frame = cur_frame)
            bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
            bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)

        else:
            self.report({'ERROR'}, "Select both Armature and Object")
            
            
        return {'FINISHED'}
    
class SnapHead(bpy.types.Operator):
    
    bl_label = "Head"
    bl_idname = 'snap_head.add'
    
    # --- declared up front so a non-EpicFigRig rig fails cleanly ---
    epic_kind = 'ACCESSORY'
    epic_bones = ("Head Accessory",)

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        
        cur_frame = bpy.context.scene.frame_current
        context = bpy.context
        
        
        
        if len(context.selected_objects) == 2:
            
            #names selected_armature and selected_object 
            for obj in bpy.context.selected_objects:
                
                if obj.type == 'ARMATURE':
                    global selected_armature
                    selected_armature = obj.name
                    
                    
                if obj.type == 'MESH':
                    global selected_object
                    selected_object = obj.name
                    
                
            #deselects everything
            bpy.data.objects[selected_armature].pose.bones["Head Accessory"].select = False
            for obj in bpy.context.selected_objects:
                obj.select_set(False)

            
            #selects adds keyframes to the selected object
            selected_object_keyframe = bpy.data.objects[selected_object].keyframe_insert
            bpy.data.objects[selected_object].select_set(True)
            # FIX: this read scene.objects[0] -- whatever object happens to
            # be first in the scene, which has nothing to do with the
            # accessory being snapped. The trailing comment says what was
            # meant. Two consequences: keyframe_insert_menu below ran with an
            # unrelated active object, and if that object sits in a collection
            # excluded from the view layer the assignment raises outright.
            obj = bpy.data.objects[selected_object]
            bpy.context.view_layer.objects.active = obj
            selected_object_keyframe(data_path='location', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='rotation_euler', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='scale', frame = (cur_frame - 1))
            
            #adds and sets up Copy Transforms Constraint
            # FIX: use the constraint constraints.new() just returned. Looking
            # it up by name fetched the WRONG one whenever the accessory
            # already carried a Copy Transforms constraint (snapping the same
            # prop a second time): new() names the duplicate
            # "Copy Transforms.001", so the lookup re-keyed the stale
            # constraint and left the fresh one behind, unconfigured.
            copy_transform = bpy.data.objects[selected_object].constraints.new(
                'COPY_TRANSFORMS')
            target_constraint = bpy.data.objects[selected_armature]
            subtarget_constraint = bpy.data.objects[selected_armature].data.bones['Head Accessory']
            
            copy_transform.target = target_constraint
            copy_transform.subtarget = "Head Accessory"
            
            #sets up keyframes for influence
            copy_transform.influence = 0
            copy_transform.keyframe_insert(data_path = "influence", frame = cur_frame - 1)
            copy_transform.influence = 1
            copy_transform.keyframe_insert(data_path = "influence", frame = cur_frame)
            
            #sets up keyframes for Loc Rot
            selected_object_keyframe(data_path='location', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='rotation_euler', frame = (cur_frame - 1))
            selected_object_keyframe(data_path='scale', frame = (cur_frame - 1))
            bpy.ops.anim.keyframe_insert_menu(type='BUILTIN_KSI_VisualLocRot')
            copy_transform.influence = 0
            copy_transform.keyframe_insert(data_path = "influence", frame = cur_frame)
            bpy.context.scene.frame_set(bpy.context.scene.frame_current -1)
            bpy.context.scene.frame_set(bpy.context.scene.frame_current +1)



        else:
            self.report({'ERROR'}, "Select both Armature and Object")
            
            
        return {'FINISHED'}

class SmearSlider(bpy.types.Panel):

    bl_label = "Smears"
    bl_idname = "SMEAR_SLIDER"
    bl_parent_id = "EPIC_FIGRIG_PT_PANEL"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'EpicFigRig'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        arm_obj = find_epic_armature(context)
        if arm_obj is None:
            layout.row().label(text="(Select an Armature for Smears)")
            return
        arm = arm_obj.data

        # A rig built before v1.0.15 still has the broken switch curves, so
        # raising a smear shows the smear mesh but never hides the real limb --
        # you get both drawn on top of each other. Say so here rather than
        # leaving the user to wonder, and put the fix one click away.
        if smear_needs_repair(arm_obj):
            box = layout.box()
            box.label(text="Smears need repairing", icon='ERROR')
            box.label(text="The real arm/leg will not hide.")
            box.operator('rig.repair_drivers', icon='DRIVER')

        # Ranges are stamped once for the whole set, not per property per
        # redraw -- these are int properties and the bounds must match.
        _ensure_smear_ui_range(arm)

        drawn = False
        for prop_name in SMEAR_PROPS:
            # NOTE: the previous version drew the property outside its own
            # existence check, so a non-EpicFigRig armature (or no active
            # object) hit row.prop(None, ...) and broke the panel.
            if prop_name not in arm.keys():
                continue
            layout.row().prop(arm, '["%s"]' % prop_name, slider=True)
            drawn = True

        if not drawn:
            layout.row().label(text="No smear properties on this armature")


class EpicFigRigPreferences(bpy.types.AddonPreferences):

    bl_idname = __name__

    always_keyframe: BoolProperty(
        name="Always keyframe (original upstream behaviour)",
        description=("Insert keyframes every time Reset/Snap Master Bone or "
                     "the Pivot buttons are pressed, the way the original "
                     "addon did, instead of only when Blender's Auto-Key is "
                     "on. Leave this off to just pose without leaving keys"),
        default=False)

    def draw(self, context):
        col = self.layout.column()
        col.prop(self, "always_keyframe")
        col.label(text="Off (default) = the buttons only key when Auto-Key is on.",
                  icon='INFO')


class RepairRigDrivers(bpy.types.Operator):

    bl_label = "Fix Rig Settings Drivers"
    bl_idname = 'rig.repair_drivers'
    bl_description = ("Re-point the Rig Settings drivers that newer Blender "
                      "versions invalidated (ArmIK/LegIK control visibility "
                      "and the head size sliders). Run this once on a rig "
                      "built with an older version of this addon")

    epic_kind = 'ARMATURE'

    def execute(self, context):
        return _guarded_execute(self, context)

    def _execute_inner(self, context):
        arm_obj = find_epic_armature(context)
        repaired = repair_rig_drivers(arm_obj)

        still_bad = []
        for owner in (arm_obj, arm_obj.data):
            anim = getattr(owner, "animation_data", None)
            if not anim:
                continue
            for fcurve in anim.drivers:
                if not (fcurve.is_valid and fcurve.driver.is_valid):
                    still_bad.append(fcurve.data_path)

        if repaired:
            self.report({'INFO'},
                        "Repaired %d driver group(s): %s"
                        % (len(repaired), "; ".join(repaired)))
        else:
            self.report({'INFO'},
                        "Nothing to repair -- the Rig Settings drivers on "
                        "'%s' already point at current Blender API."
                        % arm_obj.name)

        if still_bad:
            # These target constraints/bones this rig simply does not have (no
            # "Damped Track" on the arms, no "Pivot slide" bone, no "Copy
            # Transforms" on the hands). They drive nothing, so they are left
            # alone rather than silently deleted -- but they are exactly what
            # prints "Invalid driver" in the console on file load, so say so.
            print("[EpicFigRig] %d driver(s) still invalid on '%s'; each "
                  "targets something this rig does not have, so they have no "
                  "effect: %s" % (len(still_bad), arm_obj.name,
                                  ", ".join(sorted(set(still_bad)))))
            self.report({'WARNING'},
                        "%d unrelated driver(s) remain invalid (they target "
                        "missing constraints/bones and do nothing) -- see the "
                        "console." % len(still_bad))
        return {'FINISHED'}


def register():

    # Say something at load time if this Blender is newer than anything
    # the addon has been tested against. bl_info's "blender" key is only
    # a MINIMUM -- Blender will happily load us on a version that has
    # since deleted half the API we use, so the warning has to be ours.
    _warn_if_untested_blender()

    bpy.utils.register_class(EpicFigRigPanel)

    bpy.utils.register_class(EpicButtons)

    bpy.utils.register_class(RigSettings)

    bpy.utils.register_class(SmearSlider)

    bpy.utils.register_class(ResetMasterBone)

    bpy.utils.register_class(SwitchPivottoLeft)

    bpy.utils.register_class(SwitchPivottoRight)

    bpy.utils.register_class(SnapMasterBone)

    bpy.utils.register_class(SnapRight)

    bpy.utils.register_class(SnapLeft)

    bpy.utils.register_class(SnapHead)

    bpy.utils.register_class(ResetPivot)

    bpy.utils.register_class(AutoRig)

    bpy.utils.register_class(RepairRigDrivers)

    bpy.utils.register_class(EpicFigRigPreferences)

def unregister():

    bpy.utils.unregister_class(EpicFigRigPanel)

    bpy.utils.unregister_class(EpicButtons)
    
    bpy.utils.unregister_class(RigSettings)

    bpy.utils.unregister_class(SmearSlider)

    bpy.utils.unregister_class(ResetMasterBone)

    bpy.utils.unregister_class(SwitchPivottoLeft)

    bpy.utils.unregister_class(SwitchPivottoRight)

    bpy.utils.unregister_class(SnapMasterBone)

    bpy.utils.unregister_class(SnapRight)

    bpy.utils.unregister_class(SnapLeft)

    bpy.utils.unregister_class(SnapHead)

    bpy.utils.unregister_class(ResetPivot)

    bpy.utils.unregister_class(AutoRig)

    bpy.utils.unregister_class(RepairRigDrivers)

    bpy.utils.unregister_class(EpicFigRigPreferences)

    
    
if __name__ == "__main__":
    register()
