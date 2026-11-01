# Test fixtures

| File | Source |
|---|---|
| `astronaut_face_record.png` | 112x112 aligned face record produced by the `faceliveness` SDK (`Engine.capture.png`) from face-liveness's `astronaut_face.rgb` — a crop of scikit-image's `astronaut.png`, NASA photo of Eileen Collins, public domain. Stands in for a real liveness capture. |

Use aligned face records (what the SDK produces) for matching tests: SFace scores an
unaligned crop of the same face at ~0.32, below the match threshold.
