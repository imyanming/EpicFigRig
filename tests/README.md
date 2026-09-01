# EpicFigRig test suite

Every check here exists because something actually went wrong during the port
to Blender 5.0. They assert measured numbers, not just "it didn't throw" — a
failure that reads `character moved 4.991, wanted < 0.05` is worth ten that
say `False`.

Requires **Blender 5.0.1** and the three `.blend` sources in the repo root.

---

## Running

Two commands. Both must pass.

```bash
# main suite -- run windowed
blender Append.blend --python tests/run_tests.py -- report.txt

# smear check -- run on its own, background is fine
blender -b --python tests/check_smear.py
```

**Run the main suite windowed, not with `-b`.** Several operators call
`bpy.ops.view3d.snap_cursor_to_selected` and `bpy.ops.anim.keyframe_insert_menu`,
and both fail `poll()` without a real 3D View. The suite says so on startup
rather than reporting green on tests that never ran.

The path after `--` is optional and gets a copy of the report, written line by
line. Blender can hard-crash while tearing a scene down, which loses buffered
stdout and with it every result — the file survives and names the module it
died in. Worth passing in CI.

`check_smear.py` exits non-zero on failure. `run_tests.py` does too in
background mode; windowed it prints `exit code would be N` and closes Blender,
because Blender ignores the exit code once a window is open.

To run one module: `... -- report.txt test_pivot`

---

## What is covered

| Module | Checks | The bug it guards against |
|---|---|---|
| `test_master_bone` | 12 | Snap Master Bone displaced the character by the same amount it moved the root, accumulating every press (4.99 → 9.98 → 14.97 → 19.96). Also: a 180° turn was silently dropped and the character spun back to front. |
| `test_pivot` | 13 | The 3D cursor was borrowed as scratch space and never restored; an unpaired `frame_set(+1)` crept the timeline forward on every press. |
| `test_accessory` | 6 | Snap accuracy and previous-frame restore. These use a `COPY_TRANSFORMS` constraint rather than manual matrix maths, so they never had the coordinate bug — covered to keep it that way. |
| `test_interpolation` | 4 | Every key the buttons wrote came out stepped, so animation looked like bad stop-motion. Also that the interpolation preference is restored on *both* exit paths, including when an operator raises. |
| `test_robustness` | 36 | On an empty scene or a non-EpicFigRig armature, the nine operators raised raw Python tracebacks in 21 of 32 cases. Now zero. |
| `check_smear` | 12 | The smear proxy appeared but the real arm or leg never hid, so both drew on top of each other. |

**71 checks in the suite, 12 in the smear check.**

---

## Things worth knowing before you edit these

**Probe the hip, not `Center of Mass`.** The hierarchy is

```
Center of Mass    -> MasterBone
BodyControlBoneIK -> ... -> Center of Mass -> MasterBone
```

`Center of Mass` is a direct child of the root and therefore *must* travel with
it. Measuring "did the character move" there reports a 4.99 failure for
completely correct behaviour. The body hangs off `BodyControlBoneIK`, whose
compensating offset is what actually keeps the character standing still.

**Read driven values off the depsgraph.** Drivers write to the evaluated copy,
not to `bpy.data`. Reading `obj.hide_viewport` straight off the datablock gives
the stored value and makes a working driver look broken. Use
`harness.evaluated()`.

**`hasattr()` on a *type* is the wrong API probe.** RNA properties are not
Python class attributes, so `hasattr(bpy.types.PoseBone, "select")` is `False`
for a property that works perfectly well. Use `"select" in
PoseBone.bl_rna.properties`.

**Roughly 0.01 of residual movement per press is expected.** It comes from
about 0.001 of skew in the rig's own bone matrices, not from the operators'
arithmetic. `RESIDUAL` in `test_master_bone` is set accordingly. It is real and
it does slowly accumulate.

**Order matters in `run_tests.py`.** `test_robustness` resets the scene
outright, so it runs last.

---

## Known gap

**The Auto-Key *on* recording path is not verified end to end.**
`bpy.ops.anim.keyframe_insert_menu` cannot be driven far enough from a script
to reproduce a real animator's session. `test_interpolation` covers what the
keys look like after one press; a full recorded sequence still needs a human.

`check_smear.py` is separate for a reason that is not understood, only
characterised: driving `auto.rig` from inside `run_tests.py` hard-crashes
Blender before the first assertion, in both background and windowed mode,
while the identical operator is fine in a self-contained script. If you work
out why, the two files can merge.
