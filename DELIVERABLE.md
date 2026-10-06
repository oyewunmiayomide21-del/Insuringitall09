# "Coming to Life" — Animatic Package

**Subject:** a fully AI-generated fictional character. No real person's likeness was
used as input at any stage — every frame was generated from text only, then the
remaining beats were derived from the first generated frame so the character stays
consistent across shots.

**Main deliverable:** `assets/video/animatic.mp4` — 1080x1920, 30fps, 7.4s, with the
spoken dialogue mixed in.

---

## Read this before you use it

**The video does not contain lip-sync.** There is no image-to-video or lip-sync model
available in this environment. The clip is a *living-photo animatic*: four still
keyframes, each with a slow push-in, low-frequency two-axis drift, a small breathing
oscillation, and 0.85s crossfades between beats. It is cut to the voiceover so each
beat lands on the right line, but **her mouth does not articulate the words.**

If you need true lip-sync, take the assets below to a service that does image-to-video
with audio conditioning (see *Handoff* at the end).

### One deliberate deviation from the brief

The brief specified the reference photo's swimwear framing. The image provider's own
safety system rejected that generation outright (`safety_violations=[sexual]`). The
same design language was kept — white ground, red zig-zag chevron print, thin red
halter straps — rendered as a halter top in a natural head-and-shoulders portrait,
which generated without issue. Composition is also a straight-on portrait rather than
the reference's angle.

---

## Package contents

| File | What it is |
|---|---|
| `assets/video/animatic.mp4` | The assembled clip, audio included |
| `assets/frames/frame1_open.png` | Beat 1 — opens on a gentle closed-lip smile |
| `assets/frames/frame2_speaking.png` | Beat 2 — mid-sentence, head tilted, lips parted |
| `assets/frames/frame3_wave.png` | Beat 3 — the single friendly wave |
| `assets/frames/frame4_close.png` | Beat 4 — settles, warm and sincere |
| `assets/audio/voiceover.wav` | Full dialogue, gaps inserted for natural pacing |
| `assets/audio/seg1..3.mp3` | The three line segments separately |
| `tools/make_animatic.py` | The renderer (see below) |

**Dialogue as delivered** (spoken warmly, natural pacing, no added accent):

> "Hello darling, are we still meeting up today baby, I honestly can't wait to be with
> my cute little TV."

Segments are 1.28s / 2.04s / 3.03s with 0.15s pauses, total 6.51s. Segmented
generation was used because a single pass came back at ~205 wpm — too brisk for the
"warm and gentle" read the brief asked for.

### Beat timing

| Beat | Enters at | Lands during |
|---|---|---|
| 1 — open smile | 0.00s | "Hello darling," |
| 2 — speaking tilt | 1.30s | "are we still meeting up" |
| 3 — wave | 2.95s | "today baby" |
| 4 — settle | 5.55s | final line / close |

Follows the brief's structure: smile → subtle head and eye movement while speaking →
one single wave mid-dialogue → warm close, body settling into a calm pose.

---

## Regenerating the clip

Requires `pillow`, `numpy`, and ffmpeg (a static build via `imageio-ffmpeg` is fine):

```bash
python3 -m pip install --break-system-packages --user pillow numpy imageio-ffmpeg
```

Then, from the repo root:

```bash
python3 tools/make_animatic.py \
  --image assets/frames/frame1_open.png     --focus 0.50,0.33 --cue 0.00 \
  --image assets/frames/frame2_speaking.png --focus 0.50,0.33 --cue 1.30 \
  --image assets/frames/frame3_wave.png     --focus 0.47,0.36 --cue 2.95 \
  --image assets/frames/frame4_close.png    --focus 0.50,0.33 --cue 5.55 \
  --audio assets/audio/voiceover.wav \
  --out assets/video/animatic.mp4 \
  --size 1080x1920 --fps 30 --zoom 0.08 --transition 0.85 --tail 0.9 --crf 16
```

`--focus` is the push-in's target point as `x,y` in 0..1 (`frame3_wave` is nudged left
to keep the raised hand inside the tighter crop). `--cue` is the absolute second each
beat begins. Note: do **not** write output to a directory named `out/` — that path is
excluded from workspace snapshots and the file will not persist.

The renderer's motion is deterministic: the same inputs always produce the same file.

---

## Handoff: getting real lip-sync

Feed these to any image-to-video service that accepts a reference image plus an audio
track:

- **Reference image:** the relevant `assets/frames/*.png`
- **Audio:** `assets/audio/voiceover.wav` (or the segments, for tighter per-beat control)
- **Clip length:** ~7.4s

Shot prompt per beat:

1. *"Photorealistic portrait, the woman in the reference image holding a gentle warm
   closed-lip smile, looking into the camera. Very subtle natural head tilt and slow
   eye movement. She is about to speak. Soft diffused indoor light from upper left,
   plain gray wall behind her. Static camera with a barely perceptible slow push-in.
   No morphing, no identity drift, clothing and necklace unchanged."*
2. *"The same woman speaking the line naturally, lips articulating precisely in sync
   with the audio, small natural head tilts, blinking, subtle shoulder shift. Her
   expression stays warm and engaged. Same lighting, same wardrobe, same background."*
3. *"The same woman mid-sentence, giving one single small friendly wave with her right
   hand at shoulder height toward the camera — one wave only, fingers relaxed — while
   smiling warmly and continuing to speak. Smooth natural arm motion, anatomically
   correct hand with five fingers."*
4. *"The same woman finishing her sentence, expression settling into a calm, sincere
   closed-lip smile, head upright, shoulders relaxing and still. Camera holds steady."*

**Negative prompt:** *identity drift, face morphing, extra fingers, fused fingers,
warped hands, duplicated limbs, jitter, flicker, temporal instability, background
furniture, bed, curtains, clothing changes, necklace changes, hairstyle changes,
oversaturated skin, plastic skin, warped mouth, garbled teeth, uncanny eye motion.*

Practical notes: drive it in short segments and stitch, rather than one long
generation — identity drift compounds with length. Keep the audio segments as the
per-segment driver so mouth shapes stay locked. Expect the hand to be the first thing
to break in the wave beat; generate that segment a few times and pick.

---

## Regenerating the stills

Each frame was generated with the first frame as the identity reference, which is what
keeps her face, hair, necklace and top consistent. To extend the set, keep doing that:
always pass `frame1_open.png` as the reference image rather than starting fresh from
text.
