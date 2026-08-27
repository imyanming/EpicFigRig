# EpicFigRig — Blender 4.2 / 5.0 compatibility fork

A Blender LEGO minifigure rig add-on.

This is a **modified version** of [BlenderBricks/EpicFigRig](https://github.com/BlenderBricks/EpicFigRig)
(v1.0.2, 2022, written for Blender 2.83). The original is unmaintained and no longer runs
on current Blender. This fork gets it working again on **Blender 5.0.1** and fixes a number
of bugs that predate the fork.

Original authors: Jambo, Owenator Productions, Golden Ninja Ben, IX Productions and
Citrine's Animations. Original demo video: <https://www.youtube.com/watch?v=mZM0jk-jfP0>

Licensed under the **GNU GPL v3 or later**, same as the original. See `LICENSE`.

---

## Install

Download the release zip and use **Install Legacy Add-on** — *not* the Extensions
installer. The add-on has no `manifest.toml`, and the Extensions path does not keep the
three `.blend` rig sources next to `__init__.py`, which the rigger needs. If they go
missing the add-on now says so instead of failing halfway through.

Remove any older copy first.

## Use

Select the minifigure's base parts (head, torso, hips, arms, hands, legs — not
accessories) in Object Mode and press **Rig Selected Minifigure**.

If you are opening a character that was rigged with an older build, press
**Fix Rig Settings Drivers** once — several drivers stored inside the rig point at Blender
API that no longer exists, and this repoints them. The Smears panel will tell you when a
rig still needs it.

## What changed

Two documents record every change, including the measurements behind each one:

- **[COMPAT_NOTES.md](COMPAT_NOTES.md)** — Blender API breakage (4.0 bone collections,
  5.0 `Bone.select`, `custom_shape_scale`, `transform.translate`, …), how this build
  copes, and how to tell if it breaks again.
- **[DESIGN_INTENT.md](DESIGN_INTENT.md)** — what the original author intended each
  button to do, checked against their own tutorial, and the places where this fork
  deliberately departs from that.

Headline fixes:

| Symptom | Cause |
|---|---|
| Character drifts further on every press | World-space transform read into a local pose channel |
| Snap Master Bone displaced the character, cumulatively | Missing the hip/IK-leg compensation Reset already had |
| Character span back to front when turned 180° | Euler decomposition drops the yaw at half a turn |
| Smear appeared but the real arm/leg never hid | Both hide drivers stamped the same F-curve |
| Head size sliders did nothing | Driver targeted a property renamed in Blender 3.0 |
| IK toggles did not show/hide their control bones | Drivers targeted bone layers, removed in 4.0 |
| 3D cursor silently moved | Used as scratch space, never restored |
| Buttons keyframed on every press | Now follows Blender's Auto-Key (see below) |

Robustness: on an empty scene or a non-EpicFigRig armature, all nine operators used to
raise raw Python tracebacks in 21 of 32 cases. That is now **0** — every failure reports
one clear sentence and cancels before touching anything.

## Deliberate difference from upstream

The original inserted keyframes on **every** press of the Master Bone and Pivot buttons,
by design. This fork instead follows Blender's normal **Auto-Key** toggle, because
unconditional keyframing surprises people who are only posing.

To get the original behaviour back, tick **Always keyframe** in
`Preferences → Add-ons → EpicFigRig` (also shown at the bottom of the Rig Settings panel).

## Known limitations

- The Auto-Key **on** recording path has not been verified end to end — scripted tests
  cannot drive it (`keyframe_insert_menu` fails `poll()` outside a real 3D View).
- Roughly 0.01 units of residual drift per press, from skew in the rig's own bone
  matrices. Negligible for single presses; it does slowly accumulate.
- Five drivers in the rig remain invalid. Each targets a constraint or bone the rig does
  not contain, so they drive nothing. They are the source of the `Invalid driver` lines
  Blender prints on load, and are left alone deliberately.
- Only the one-click `Rig Selected Minifigure` path is supported. Manual append +
  Ctrl+P parenting gets none of the preflight checks or the driver repair.
- `LepinHands` in Rig Settings has no effect — nothing in the rig or the code reads it.

## Reporting problems

Problems with **this build** are not upstream's responsibility — they have not touched the
project since 2022 and know nothing about these changes. Check `COMPAT_NOTES.md` first;
it lists what each failure mode looks like and what causes it.
