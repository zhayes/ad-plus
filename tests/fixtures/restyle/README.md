# Restyle test fixtures

`reference_expected.json` describes the 32s foot-bath reference ad used to
validate the Restyle analysis. The video itself is **local only** and lives at:

```
uploads/20261107/ref-footbath-32s.mp4
```

`uploads/` is gitignored. Do not commit the source video: it is a competitor
ad and may contain a real person's likeness.

The JSON is the assertion target for `adplus/restyle/analysis.py`:

- 32.067s, 720x1280, 30fps, 9:16, with audio
- 22 shots from 21 cuts at scene threshold 0.18
- expected groups: 4 scenes / 3 outfits
- expected captions: 22
- face shots: ~7; water/hand-risk shots: ~7

Small tolerances are expected: scene detection may find one extra or miss one
soft cut. Tests should assert `20 <= shots <= 23` and compare cut times within
0.15s, not exact equality.
