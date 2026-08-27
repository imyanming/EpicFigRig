# EpicFigRig — Blender compatibility notes

The upstream addon (<https://github.com/BlenderBricks/EpicFigRig>, last updated 2022)
targets Blender 2.83. This fork keeps it working on modern Blender.

**Scope of the promise.** Nobody can guarantee this keeps working on every future
Blender — the API gets removed without warning, and it has twice already. What this
file and the defensive layer in `__init__.py` are for is the achievable goal: when a
future Blender breaks something, the addon should either work or *say clearly what
broke*, never silently compute a wrong result. The 2022 code failed that test badly —
`armature.data.layers[18]` quietly stopped existing and the character ended up
airborne.

Tested on: **2.83** (original upstream), **4.2**, **5.0.1** (this fork).
Current version: **1.0.20**.

For what the *author* intended these buttons to do (and where this fork deliberately
diverges), see [DESIGN_INTENT.md](DESIGN_INTENT.md).

---

## 1. Blender API changes and how this file responds

| Blender | What changed | How this file copes | Detection if it breaks again |
|---|---|---|---|
| 4.0 | Bone Layers (32-slot bitmask) replaced by **Bone Collections**. `armature.data.layers[18]` gone. | `set_pivot_helper_visible()` prefers `armature.collections[PIVOT_BONECOLL_NAME]`, falls back to `layers[PIVOT_LAYER_INDEX]`. Never raises — the pivot helper is cosmetic, so it warns on the console and lets the operator finish. | `check_blender_api()` reports if *neither* `collections` nor `layers` exists. |
| 4.0 | **Drivers stored inside `Append.blend` that target `layers[N]`** died with the layers. `ArmIK`→`layers[2]`, `LegIK`→`layers[1]`. | `repair_rig_drivers()` re-points them at `collections["Layer 3"/"Layer 2"].is_visible`. Run automatically at the end of `auto.rig`, and on demand via the **Fix Rig Settings Drivers** button. | Toggling ArmIK/LegIK switches the IK behaviour but does **not** show/hide the matching control bones. |
| 3.0 | **`PoseBone.custom_shape_scale` (float) became `custom_shape_scale_xyz` (vector).** The `Head Bone Size` / `Head Accessory Bone Size` drivers in the .blend still name the old one. | `repair_rig_drivers()` rebuilds them across all three axes. | Those two sliders in Rig Settings do **nothing at all**. |
| 5.0 | **`Bone.select` removed.** Official note: use `pose.bones[x].select` instead of `armature.data.bones[x].select`. | All ~44 sites use `pose.bones[x].select`. | `check_blender_api()` probes `PoseBone.bl_rna.properties`. |
| 5.0 | `bpy.ops.transform.translate` rejects the old legacy kwargs (`texture_space`, `gpencil_strokes`, `cursor_transform`, …) → `TypeError`. | Trimmed to `value=` and `orient_type='LOCAL'`. | `check_blender_api()` inspects `transform.translate.get_rna_type().properties`. |
| 4.x | Setting `armature.data.bones.active = X` **no longer implicitly selects** X. Old code relied on that side effect. | Bones are selected explicitly with `.select = True` before any pose-mode toggle (`AutoRig` hand snap, both pivot operators). | No automatic probe — behavioural, not an API removal. Covered by the functional tests below. |
| ~~4.x/5.x~~ | ~~Custom-property slider min/max no longer come from the `.blend`.~~ **NOT TRUE — retracted.** The stock rig's smear properties arrive with `{'min': 0, 'max': 9, 'soft_min': 0, 'soft_max': 9}` intact. | `_ensure_smear_ui_range()` now only supplies a range when the rig has **none**, and matches int/float bound types. The earlier code stamped `min=0, max=1` over it every redraw — which silently failed with `TypeError: 'float' object cannot be interpreted as an integer` on these INT properties. Lucky: had it worked it would have clamped a 0..9 control to 0..1. | Sliders that refuse to go past 1. |
| 4.x/5.x | Depsgraph evaluation is lazier; a matrix read right after a property write can lag one step behind. | Explicit `bpy.context.view_layer.update()` before reading `master_bone_snap.matrix`. | Visible as drift that worsens per press. |
| 4.4+/5.0 | Actions became **slotted**; `action.fcurves` no longer exists. | Only affects test scripts, not the addon. Walk `action.layers[].strips[].channelbags[].fcurves`. | `AttributeError: 'Action' object has no attribute 'fcurves'`. |
| 4.2+ | Extensions platform expects a `manifest.toml`. This addon has none. | **Must be installed via "Install Legacy Add-on"**, not the Extensions installer. | Install silently does nothing / addon never appears. |

### A detection trap worth remembering

`hasattr()` on a **type** is the wrong way to test whether an RNA property exists — RNA
properties are not Python class attributes. Verified on 5.0.1:

```python
hasattr(bpy.types.PoseBone, "select")          # False  <- WRONG, it works fine
"select" in bpy.types.PoseBone.bl_rna.properties  # True   <- correct
"select" in bpy.types.Bone.bl_rna.properties      # False  <- correctly detects the 5.0 removal
```

The first version of `check_blender_api()` used `hasattr` and produced a false alarm on
every button press. Use the `_rna_has()` helper. On an **instance**, plain `hasattr`
is fine (`hasattr(arm, "collections")`).

---

## 2. Assumptions this file still makes

These are the things that would break next. None of them are guarded by an automatic
probe, because you cannot probe a rig convention — but every one of them now produces a
clear message instead of a traceback, via the preflight in `_guarded_execute()`.

- **Bone names are fixed strings.** `MasterBone`, `Master Bone Snap`, `Pivot`,
  `Pivot lock L/R`, `BodyControlBoneIK`, `LeftFootIK`, `RightFootIK`,
  `Center of Mass`, `Left/Right Hand Snap Bone`, `Head Accessory`. Each operator
  declares what it needs in `epic_bones` and is checked before it touches anything.
- **`PIVOT_BONECOLL_NAME = "Layer 19"`** — **confirmed**. The stock rig carries
  `Layer 1, Layer 2, Layer 3, Layer 8, Layer 17, Layer 18, Layer 19, Layer 24` plus
  `Blue, Yellow, Green, Red`, so legacy layer index 18 → `"Layer 19"` holds. (It was a
  guess until the driver audit listed the collections.) If a future rig variant renames
  them the console prints the available names.
- **The armature data-block is renamed to match the object name** (`obj.data.name =
  obj.name`) so `bpy.data.armatures[selected_armature]` resolves — `selected_armature`
  holds the *object* name while that lookup is keyed by the *data-block* name.
  **This line is required, not copy-paste noise: do not "tidy" it away.** The author's
  tutorial states that if the two names differ the UI scripts break. Fragile with
  duplicates. See [DESIGN_INTENT.md](DESIGN_INTENT.md) §4.
- **`Master Bone Snap` exists twice** — as a bone *and* as a scene Empty object. Both
  are required; the Empty is used as scratch space.
- **`Pivot Slide`** is a custom property on the armature data-block.
- **Bone axis mapping** on `MasterBone`: local Y = armature −Z (vertical, inverted),
  local Z = armature +Y. See the audit block in `__init__.py`.
- **`BodyControlBoneIK.lock_location = (True, False, False)`** — the sideways hip axis is
  locked, which is why the Master Bone operators only compensate forward/back.

`auto.rig` (Rig Selected Minifigure) additionally assumes:

- **The three rig source `.blend` files sit next to `__init__.py`** (`Append.blend`,
  `Append_Child.blend`, `Cape_Rig.blend`). This is the single most likely install
  failure — the Extensions installer does not keep them together. Checked by
  `_preflight_rigging()` against `REQUIRED_BLEND_FILES`.
- **Parts are identified by LEGO part number substrings in the *mesh data* name**, not
  the object name — `"3814"` torso, `"3815"` hips, `"3816"/"3817"` legs,
  `"3818"/"3819"` arms, `"3820"` hands, plus long tables for heads and head
  accessories. Rename a mesh datablock and that part silently stops being recognised.
- **Every selected part needs a material.** The rigger copies each part's material onto
  its smear proxy mesh (`LlegS`, `RlegS`, …) via `material_slots[0]`, so an unpainted
  part used to raise `IndexError` *after* the rig had already been appended, leaving a
  half-built scene. Now refused up front, naming the offending objects.
- The collection appended from those files is named **`"The EpicFigRig"`**
  (`"CapeRig"` for the cape).

---

## 3. Behaviour fixes (not API — pre-existing bugs)

| # | Problem | Fix |
|---|---|---|
| 1 | World-space drift: `obj_empty` transforms are world-space but were read straight into MasterBone's **local** pose channels, assuming the armature sits at the world origin. It does not — it sits at world Z +16. | Convert through `armature.matrix_world.inverted() @ obj_empty.matrix_world` first. |
| 2 | 3D cursor used as scratch space and never restored, permanently moving the user's cursor. | Save/restore `cursor.location` and `.rotation_euler`. |
| 3 | Keyframes inserted on **every** press, even when only posing. | Gated behind `use_keyframe_insert_auto` (Blender's normal Auto-Key toggle). **Deliberate deviation from upstream, not a defect** — the author intended per-press keyframing. Reversible via the "Always keyframe" preference. See [DESIGN_INTENT.md](DESIGN_INTENT.md) §3. |
| 4 | New keys used the user's global default interpolation (often Bezier), turning the single-frame pop into a slide. | Force `CONSTANT` for the operator's duration, restore after. |
| 5 | `SnapMasterBone` had an unpaired `frame_set(+1)`, nudging the current frame forward on every press. | Only done (and undone) when Auto-Key is on. |
| 6 | `MasterBone.location[1] = snap_empty_zloc` was uncommented in v1.0.9 on the theory that an axis was "missing". It is the **vertical** channel and was commented out deliberately. It threw the character +15.75 up on a ~23-unit-tall rig, flip-flopping between two states. | Reverted. This tool snaps ground position + facing only. |
| 7 | `SnapMasterBone` moved MasterBone correctly but **also displaced the character** by the same amount, accumulating every press (4.99 → 9.98 → 14.97 → 19.96). It lacked the hip/IK-leg compensation `ResetMasterBone` has. Present in the 2022 original. | Added the same compensation block. Both operators now hold the character still. |
| 8 | The `Pivot Slide` frame-1 keyframe recorded the *new* value instead of the old one, flattening the before/after pop. | Remember the old value, key it on frame-1, then set 0. |
| 10 | **Smear never hid the real limb.** `driverCreate()` fetched the curve to stamp with `obj.animation_data.drivers[0]` for *both* the `hide_viewport` and the `hide_render` driver, so the second call piled two more points onto the first curve. Limbs ended up with 6 keyframe points instead of 2 and the on/off mapping stopped switching — the smear mesh appeared but the arm/leg stayed visible, drawn on top of it. The smear meshes' own curves were always correct, which is why only the limbs looked wrong. | `_set_switch_curve()` stamps the F-curve `driver_add()` returned, normalising it to exactly two CONSTANT points. `repair_rig_drivers()` also re-normalises existing rigs, so the **Fix Rig Settings Drivers** button repairs characters already rigged. |
| 9 | The three pivot operators assigned `_prev_interp` inside `if context.mode == 'POSE':` but restored it unconditionally → `UnboundLocalError` on the error path. | Seeded before the branch. |

---

## 3b. Drivers that stay invalid on purpose

After `repair_rig_drivers()` the stock rig still reports **5** invalid drivers. Every one
of them targets something the rig simply does not contain, so they drive nothing and are
left alone rather than silently deleted:

| Driver | Why it is dead |
|---|---|
| `pose.bones["Left Arm"].constraints["Damped Track"].influence` | `Left Arm` has **no constraints at all** |
| `pose.bones["Right Arm"].constraints["Damped Track"].influence` | same |
| `pose.bones["Left Hand"].constraints["Copy Transforms"].influence` | `Left Hand` only has `Copy Location` (whose equivalent driver is fine) |
| `pose.bones["Right Hand"].constraints["Copy Transforms"].influence` | same |
| `pose.bones["Pivot slide"].location` | there is no bone `Pivot slide` (the rig has `Pivot`, `Pivot control 1/2`, `Pivot lock L/R`) — and it reads `["Pivot slide"]`, lowercase, while the property is `"Pivot Slide"` |

These are pre-existing authoring leftovers in `Append.blend`, not version breakage, and
they are the source of the `WARNING Invalid driver` lines Blender prints on file load.

Also worth knowing: **`LepinHands` has no consumer.** The slider is drawn in Rig Settings
but no driver, constraint, or script reads it. It currently does nothing.

---

## 4. How to check quickly

Blender can drive the whole addon headlessly — **measure, do not guess.** Bone axis
mappings in particular are not readable from the Python source.

```bash
# read-only inspection
blender -b Append.blend --python inspect.py

# operators need a real 3D View; run windowed and use temp_override
blender Append.blend --python test.py
```

```python
import bpy, sys, importlib
sys.path.insert(0, r"<dir containing EpicFigRig/>")
mod = importlib.import_module("EpicFigRig"); mod.register()
arm = bpy.data.objects['Rig']; arm.name = 'FinishedRig'; arm.data.name = 'FinishedRig'

ov = None
for w in bpy.context.window_manager.windows:
    for a in w.screen.areas:
        if a.type == 'VIEW_3D':
            ov = dict(window=w, area=a,
                      region=[r for r in a.regions if r.type == 'WINDOW'][0])

with bpy.context.temp_override(**ov):
    bpy.ops.rig.reset()
```

Caveats: `bpy.ops.anim.keyframe_insert_menu` and `bpy.ops.view3d.snap_cursor_to_selected`
fail `poll()` in background (`-b`) mode — run windowed for those.

### What a regression run should show

Hip pushed +5 forward, Auto-Key off — the character must **not** move:

```
rig.reset        MasterBone +4.991 | character -0.009 | LeftFoot -0.008
snap.masterbone  MasterBone +4.991 | character -0.009 | LeftFoot -0.008
```

(±0.009 per press is the rig's own ~0.001 matrix skew, not drift.)

Empty scene / non-EpicFigRig armature: every button must return `CANCELLED` with a
one-line explanation and **no Python traceback**.

`auto.rig` can be exercised without a real minifigure — build synthetic parts whose
*mesh data* names carry the part numbers, and give each one a material:

```python
for name, num in {"head":"3626", "torso":"3814", "hips":"3815",
                  "leg_l":"3817", "leg_r":"3816"}.items():
    me = bpy.data.meshes.new("%s_%s" % (num, name))
    me.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
    me.materials.append(bpy.data.materials.new("mat_" + name))
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    obj.select_set(True)
bpy.ops.auto.rig()      # -> {'FINISHED'}, scene gains "FinishedRig"
```

A pass means `{'FINISHED'}` and a `FinishedRig` armature carrying `MasterBone`,
`Master Bone Snap`, `Pivot`, `BodyControlBoneIK` and the `Pivot Slide` property.
Note that Blender sometimes does not exit cleanly after a full rig build in a scripted
session — that is a shutdown quirk, not a rigging failure. Have the test write its log
line by line rather than only at the end, or you will lose results that were fine.
