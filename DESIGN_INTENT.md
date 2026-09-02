# EpicFigRig — original design intent

Everything here is checked against the **author's own v1.0.1 tutorial narration**, which
is the only first-hand statement of what these buttons are *supposed* to do. Up to this
point the fork's behaviour had been reconstructed by reading code and measuring the rig,
so this file records where the author's account confirms a change, where it contradicts
one, and what was measured either way.

Companion to [COMPAT_NOTES.md](COMPAT_NOTES.md), which covers Blender API breakage.
Addon version at time of writing: **1.0.22**.

---

## 1. Snap Master Bone must not move the character — CONFIRMED

The author describes the button as built for looping walk/run cycles, snapping the master
bone forward *seamlessly* so the feet do not slide when a cycle repeats.

"Seamlessly" settles it: the character must not visibly move at all. Only the master
bone's underlying position is supposed to catch up.

This corroborates the v1.0.11 fix. Measured on the stock rig, hip pushed +5 forward,
Auto-Key off:

| | before v1.0.11 | after |
|---|---|---|
| `rig.reset` | MasterBone +4.991, character +0.009 | unchanged (was already correct) |
| `snap.masterbone` | MasterBone +4.991, **character +4.991** | MasterBone +4.991, character **−0.009** |

Before the fix the displacement accumulated on every press — 4.99 → 9.98 → 14.97 →
19.96 — which is precisely the foot-sliding the feature exists to prevent. The cause was
that `SnapMasterBone` lacked the hip/IK-leg compensation `ResetMasterBone` already had.
Confirmed absent from the 2022 original too, so this was a genuine upstream bug rather
than something the port introduced.

---

## 2. The Mecabricks root Empty — INVESTIGATED, and it is not what we assumed

The author instructs that a Mecabricks model imports under a root `Empty` which must be
deleted before rigging, because it interferes with the master bone reset scripts.

Three things were checked.

**a. Is such an Empty shipped inside the addon's own `.blend` files?** No.

| File | Empties present | Armature | Armature parent |
|---|---|---|---|
| `Append.blend` | `Master Bone Snap` only (at the origin) | `Rig` | **none** |
| `Append_Child.blend` | `Master Bone Snap` only (at the origin) | `Rig` | **none** |
| `Cape_Rig.blend` | none | `CapeRig` | **none** |

`Master Bone Snap` is EpicFigRig's own scratch object. (`Root` matches a name search but
is a *mesh* — a bone widget shape.)

**b. Is the Empty the source of the rig's world offset?** **No — correction to the
earlier assumption.** The armature is parented to nothing; its offset is authored
directly into its own object transform:

```
Rig.matrix_world.translation = (0.0, 0.0, 16.0)      scale = (1, 1, 1)
Rig.location                 = (0.0, 0.0, 16.0)      parent chain = (none)
CapeRig                      = (0.0, 0.0, 28.8)
```

It is **(0, 0, 16)** — a pure Z lift, not `(-20, -4.4, 16)`. Nothing is parented to an
Empty, and no Mecabricks object is involved. This matters for the diagnosis: the
world-vs-local bug fixed in COMPAT_NOTES §3.1 was triggered by the rig's *own* built-in
+16 Z offset, so it affected **every** character, not only Mecabricks imports. The fix
was necessary regardless.

**c. Does the addon already handle the Empty?** It tries to, and has never once
succeeded:

```python
#remove empty
if bpy.context.selected_objects[0].parent == True:      # never true
```

`obj.parent` is an `Object`, which never compares equal to `True`. Verified directly:

```
cube.parent              -> bpy.data.objects['MecabricksRoot']
cube.parent == True      -> False     <- the addon's condition
cube.parent is not None  -> True      <- what it should be
```

So the author's automatic cleanup is dead code and always has been, which is presumably
why the tutorial has to tell users to delete the Empty by hand.

**d. What the author says actually goes wrong.** The stated mechanism is that the master
bone ends up *indirectly parented* to the Empty, and that this is what upsets the Master
Bone reset/snap buttons. That is exactly the world-space-vs-armature-local confusion fixed
in COMPAT_NOTES §3.1 — a parent chain makes `matrix_world` diverge from local space, which
is precisely what the old code assumed could never happen.

So both things are true and they are *separate* offsets:

- the **(0, 0, 16)** authored into `Append.blend` — always present, affects every rig;
- an **additional** offset from the Mecabricks parent chain — only when the Empty survives.

Worth noting: since v1.0.11 converts through `armature.matrix_world.inverted()`, the parent
chain case would now be handled correctly anyway. The preflight still blocks it, because the
author's instruction is explicit and the Empty causes other trouble besides — but the
buttons are no longer defenceless if one slips through.

**What was done.** `_preflight_rigging()` now detects parts still parented to an Empty
and refuses to rig, naming it:

> These parts are still parented to an Empty: 'Mecabricks_Root'. A Mecabricks import
> brings in a root Empty which has to be deleted before rigging — it interferes with the
> master bone reset scripts. Delete it (keeping the parts), then rig again.

Reporting was chosen over resurrecting the auto-delete, because silently removing an
object from someone's scene is not a decision the addon should make on its own. The dead
branch is left in place with a comment saying it never runs.

**DECIDED (maintainer, 2026-08-27): keep the error report. Do not change it to an
automatic delete.** The one-line revival of the auto-delete was offered and declined —
so this is settled, not an outstanding to-do.

---

## 3. Auto-Key gating is a DELIBERATE DEVIATION from upstream

The author states that Snap Master Bone snaps the master bone to the character's current
location *and keyframes it*, preserving the animation while stopping the UI being left
behind. Keyframing on every press is therefore **intended upstream behaviour, not a bug**.

The narration makes the same point about **Reset Master Bone**: it snaps the master bone
to the character and adds keyframes, so previously animated movement is preserved. So the
per-press keyframing is intended for *both* Master Bone buttons, not just Snap.

The **Pivot Foot Switch** buttons are the same: the narration says switching the pivot
foot adds keyframes so the switch can happen mid-animation. All five gated operators are
therefore covered by this deviation, not just the two Master Bone ones.

v1.0.10 nevertheless changed it: the operators now key only when Blender's own Auto-Key
toggle is on. This was a response to unconditional keyframing surprising users who were
only posing and leaving keys on frames they never meant to touch.

**This is a deliberate product decision, not an unfinished fix and not a compatibility
problem. Please do not "restore" it.** The rationale is repeated in the docstring of
`_should_keyframe()` in `__init__.py`.

It is now reversible without editing code. **Preferences → Add-ons → EpicFigRig →
"Always keyframe (original upstream behaviour)"**, also shown at the bottom of the Rig
Settings panel:

| Auto-Key | "Always keyframe" | Result |
|---|---|---|
| off | off *(default)* | buttons only reposition bones |
| on | off | keys inserted — normal Blender behaviour |
| off | **on** | keys inserted every press — **upstream behaviour** |

Verified:

```
AutoKey OFF, no prefs            -> should_keyframe=False
AutoKey ON,  no prefs            -> should_keyframe=True
AutoKey OFF, always_keyframe=ON  -> should_keyframe=True   (upstream)
AutoKey OFF, always_keyframe=OFF -> should_keyframe=False
```

---

## 4. `data.name = object.name` is required — do not remove it

The author warns that if the rig is renamed, the name in the Armature **Object**
properties and the Armature **Data** properties must match exactly, or the UI scripts
break.

That is exactly what the repeated line does:

```python
bpy.context.object.data.name = bpy.context.object.name
```

It appears at the top of five operators and looks like copy-paste noise. It is not.
Several code paths reach the armature through `bpy.data.armatures[selected_armature]`,
which is keyed by the **data-block** name while `selected_armature` holds the **object**
name — so the two must be kept in sync or those lookups raise `KeyError`.

Also recorded in COMPAT_NOTES.md §2.

---

## 5. Features the audit has not covered

The tutorial describes more than the fork has tested. Assessed by exposure rather than
tested one by one, because the deciding question is whether any addon *Python* touches
them — that is where the known-broken idioms (`select`, bone collections,
`transform.translate`) live.

Occurrences in `__init__.py`:

| Feature | Addon Python | Driver audit | Status |
|---|---|---|---|
| Arm socket system (in/out of socket) | `Socket` ×3 (panel labels, `AutoRig` subtargets) | covered | **tested, working** — see below |
| Arm Socket Lock / IK Stick | panel labels only | covered | **tested, working** |
| Selection Knobs | `Knob` ×0 | covered | pure rig data — no Python exposure |
| Body Roll / Torso Roll | `Body Roll` ×0 | covered | pure rig data — no Python exposure |
| Torso "In Front" display | `in_front` ×0 | covered | pure rig data — no Python exposure |
| Center of Mass rotation | `Center of Mass` ×12 | covered | exercised by the Master Bone operators |
| Manual rigging (append + Ctrl+P) | none | n/a | **genuinely unchecked** — see below |

**The arm socket settings were tested this round and all three work.** Driven values read
back off the evaluated depsgraph:

```
ArmIK=0 -> Left Arm Socket Control influences={'IK': 0.0, 'Transformation': 0.0}
ArmIK=1 -> Left Arm Socket Control influences={'IK': 1.0, 'Transformation': 1.0}
IK Stick=0 -> Left Arm IK {'Limit Distance': 1.0, 'Child Of': 1.0}
IK Stick=1 -> Left Arm IK {'Limit Distance': 1.0, 'Child Of': 0.0}
IK Arm Socket Lock=0 -> Left Arm IK lock_location=(False,...), Socket lock_ik_z=False
IK Arm Socket Lock=1 -> Left Arm IK lock_location=(True,...),  Socket lock_ik_z=True
```

**The dependency cycle on `Left/Right Arm Socket Control` is benign.** Blender prints it
on every load (`Transformation` → `Limit Distance` → back). Four consecutive evaluations
gave a bit-identical pose, so it resolves deterministically rather than oscillating:

```
eval 0 -> Left Arm Socket Control pose loc=(6.2538, -0.0257, 9.0113)
eval 1..3 -> STABLE
```

It is still worth fixing upstream one day — a cycle is a latent hazard — but it is not
currently producing wrong results.

**Manual rigging is OUT OF SCOPE — decided, not overlooked.**

**DECIDED (maintainer, 2026-08-27): the one-click `auto.rig` path is the supported
workflow. The manual append + Ctrl+P route is deliberately not covered.** Do not spend
effort hardening or testing it unless that decision changes.

For the record, what a manually rigged character misses: all of the
`_preflight_rigging()` checks (mode, selection, missing `.blend` files, unpainted parts,
leftover Empty), and — the one that actually bites — **the driver repair**, because
`repair_rig_drivers()` runs at the end of `auto.rig`. Such a rig keeps the broken
`ArmIK`/`LegIK` control visibility and the dead head-size sliders until
**Fix Rig Settings Drivers** is pressed. That button works on any EpicFigRig armature in
any mode, so it remains the escape hatch if a manual rig ever turns up.

---

## 6. Settled by the full tutorial

**Accessory snapping is not supposed to parent — QUESTION CLOSED.** This was flagged twice
as an open design question: after snapping, the accessory does not follow the hand,
because the Copy Transforms influence is keyed back to 0 once the visual transform has
been baked. The author states plainly that accessory snapping *does not* parent the
object, and that you should use the Dynamic Parent add-on for a held prop, or parent a
hat manually to the `Head Accessory` bone. **So the current behaviour is correct and
nothing needs changing.**

**The transform locks are deliberate.** The author advises against changing the axis locks
on most bones, feet excepted. This corroborates the measured
`BodyControlBoneIK.lock_location = (True, False, False)` — the sideways hip axis is locked
on purpose, which is why the Master Bone operators only compensate forward/back
(COMPAT_NOTES §2).

**Object-mode movement of the rig is locked, and still is.** The author says moving the
rig in Object Mode is disabled so it cannot happen by accident. Verified on the stock rig
in 5.0.1 — still intact:

```
Rig object: lock_location=(True, True, True)
            lock_rotation=(True, True, True)
            lock_scale=(True, True, True)
```

Move the rig with the master bone, not the object.

**The renaming safeguard is the `data.name = object.name` line.** The author describes
code that snaps the name back if you rename only the Armature tab. That is exactly the
line documented in §4 — the *data-block* name is forced to match the *object* name. Change
the name in the Object tab (or both), never the data tab alone.

**The User Manual button is present and working** — `EpicFigRigPanel` opens the author's
Google Doc via `wm.url_open`. Nothing to restore.

**Head size sliders have a real job.** They exist so the head bones can be enlarged when a
hat or helmet covers them, otherwise those bones are unselectable. Worth remembering that
these were completely dead until v1.0.13 — a user with a helmeted character had no way to
grab the head bone at all.
