#!/usr/bin/env python3
"""
make_animatic.py — assemble a subtle-motion "living photo" animatic MP4 from a set
of keyframe stills plus a voiceover track.

WHAT THIS IS
    Stills + camera movement + crossfades + real audio. There is NO generative
    video and NO lip-sync: the subject's mouth does not articulate the words.
    This is a previs / animatic tool, not a talking-head generator. Never label
    its output as lip-synced.

MOTION MODEL
    Each shot gets a slow push-in (widest -> tightest), a low-frequency drift on
    both axes, and a small breathing oscillation so the frame never reads as a
    frozen JPEG. Motion is deterministic (phase derived from shot index), so the
    same inputs always produce the same file.
"""

import argparse
import math
import os
import re
import shutil
import subprocess

import numpy as np
from PIL import Image


def find_ffmpeg() -> str:
    """Locate ffmpeg: PATH first, then the imageio-ffmpeg static build."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise SystemExit(
        "No ffmpeg found. Install it, or run:\n"
        "  python3 -m pip install --break-system-packages --user imageio-ffmpeg"
    )


def media_duration(ffmpeg: str, path: str) -> float:
    """Read a media file's duration from ffmpeg's stderr banner."""
    proc = subprocess.run([ffmpeg, "-hide_banner", "-i", path],
                          capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not m:
        raise SystemExit(f"Could not read duration of {path!r}")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def ease_in_out(p: float) -> float:
    """Smoothstep so push-in starts/stops never snap."""
    p = min(max(p, 0.0), 1.0)
    return p * p * (3.0 - 2.0 * p)


class Shot:
    """One still, pre-scaled once, then sampled through a moving viewport."""

    def __init__(self, path, canvas_w, canvas_h, focus=(0.5, 0.4), zoom=0.08, index=0):
        self.W, self.H = canvas_w, canvas_h
        self.fx, self.fy = focus
        self.zoom = zoom

        src = Image.open(path).convert("RGB")
        sw, sh = src.size

        # Scale so the widest viewport still covers the canvas at full zoom-out.
        # The 1.03 margin absorbs the breathing term and rounding, otherwise the
        # viewport can exceed the scaled image and produce negative box offsets.
        self.extra = 1.0 + zoom
        margin = 1.03
        scale = max(
            (canvas_w * self.extra * margin) / sw,
            (canvas_h * self.extra * margin) / sh,
        )
        self.sw = max(int(round(sw * scale)), canvas_w + 4)
        self.sh = max(int(round(sh * scale)), canvas_h + 4)
        self.scaled = src.resize((self.sw, self.sh), Image.LANCZOS)

        self.phase = (index * 2.399963) % (2.0 * math.pi)

    def frame(self, t_global: float, p: float) -> Image.Image:
        """Render one canvas-sized frame; p is this shot's 0..1 progress."""
        e = ease_in_out(p)

        vw = self.W * (self.extra - self.zoom * e)
        breath = 1.0 + 0.004 * math.sin(2.0 * math.pi * 0.22 * t_global + self.phase)
        vw *= breath
        vh = vw * (self.H / self.W)

        # Safety net: never let the viewport leave the pre-scaled image.
        vw = min(vw, self.sw - 2.0)
        vh = min(vh, self.sh - 2.0)

        dx = 0.0045 * math.sin(2.0 * math.pi * 0.11 * t_global + self.phase)
        dy = 0.0060 * math.sin(2.0 * math.pi * 0.08 * t_global + self.phase * 1.7)

        cx = self.fx * self.sw + dx * self.sw
        cy = self.fy * self.sh + dy * self.sh

        hw, hh = vw / 2.0, vh / 2.0
        cx = min(max(cx, hw), self.sw - hw)
        cy = min(max(cy, hh), self.sh - hh)

        box = (cx - hw, cy - hh, cx + hw, cy + hh)
        return self.scaled.resize((self.W, self.H), Image.BICUBIC, box=box)


def build_plan(duration, weights_in, transition, fps, starts_in=None):
    """Map each frame to a shot, and inside overlaps to a blend pair."""
    total = max(int(round(duration * fps)), 1)

    if starts_in is not None:
        starts = list(starts_in)
        span_end = duration
        lengths = []
        for i, s in enumerate(starts):
            nxt = starts[i + 1] if i + 1 < len(starts) else span_end
            lengths.append(nxt - s)
    else:
        w = np.array(weights_in, dtype=float)
        w = w / w.sum()
        span = duration + transition * (len(w) - 1)
        starts, cursor = [], 0.0
        for x in w:
            starts.append(cursor)
            cursor += x * span
        lengths = [x * span for x in w]

    plan = []
    for i in range(total):
        t = (i + 0.5) / fps
        idx = 0
        for j, s in enumerate(starts):
            if t >= s:
                idx = j
        blend = None
        if idx + 1 < len(starts):
            nxt = idx + 1
            if t >= starts[nxt] and transition > 0:
                a = (t - starts[nxt]) / transition
                blend = (idx, nxt, min(max(a, 0.0), 1.0))
        plan.append((t, idx, lengths, starts, blend))
    return plan, lengths, starts


def render(args):
    ffmpeg = find_ffmpeg()
    W, H = args.size
    fps = args.fps
    n = len(args.image)

    focus = args.focus or [(0.5, 0.4)] * n
    while len(focus) < n:
        focus += [focus[-1]]

    shots = [Shot(p, W, H, focus=focus[i], zoom=args.zoom, index=i)
             for i, p in enumerate(args.image)]

    # Timeline length: explicit duration, else the audio length, plus a tail.
    audio_dur = media_duration(ffmpeg, args.audio)
    dur = round((args.duration if args.duration else audio_dur) + args.tail, 3)

    # --cue lets each shot start at an absolute second (used to land the wave and
    # the closing beat on specific words). Falls back to proportional weights.
    starts = args.cue if args.cue else None
    if starts:
        starts = sorted(starts)
        if len(starts) != n:
            raise SystemExit("--cue must be given once per --image")

    weights = args.weights or [1.0] * n
    if len(weights) != n:
        raise SystemExit("--weights must be given once per --image")

    plan, lengths, starts = build_plan(dur, weights, args.transition, fps, starts)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
        "-i", args.audio,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "slower", "-crf", str(args.crf),
        "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        "-t", f"{dur:.3f}",
        args.out,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    try:
        for t, idx, lengths_, starts_, blend in plan:
            p = (t - starts_[idx]) / max(lengths_[idx], 1e-6)
            base = shots[idx].frame(t, p)

            if blend is None:
                arr = np.asarray(base, dtype=np.uint8)
            else:
                # Both sides keep moving through the crossfade — caching the
                # incoming frame here would freeze it for the fade duration.
                b_idx, alpha = blend[1], blend[2]
                pb = (t - starts_[b_idx]) / max(lengths_[b_idx], 1e-6)
                nxt = shots[b_idx].frame(t, pb)
                a = np.asarray(base, dtype=np.float32)
                b = np.asarray(nxt, dtype=np.float32)
                arr = (a * (1.0 - alpha) + b * alpha).astype(np.uint8)

            proc.stdin.write(arr.tobytes())
    finally:
        proc.stdin.close()
        rc = proc.wait()

    if rc != 0:
        raise SystemExit(f"ffmpeg failed with code {rc}")
    return args.out, dur


def parse_focus(v):
    x, y = v.split(",")
    return (float(x), float(y))


def main():
    ap = argparse.ArgumentParser(description="Stills + motion + audio -> animatic MP4")
    ap.add_argument("--image", action="append", required=True,
                    help="keyframe path (repeat per shot)")
    ap.add_argument("--focus", action="append", type=parse_focus,
                    help="focus point per image as x,y in 0..1")
    ap.add_argument("--cue", action="append", type=float,
                    help="absolute start second per image (overrides --weights)")
    ap.add_argument("--weights", action="append", type=float,
                    help="relative time share per image")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--duration", type=float, default=None,
                    help="timeline seconds (default: audio length)")
    ap.add_argument("--tail", type=float, default=0.7,
                    help="seconds held after the audio ends")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", type=lambda s: tuple(int(v) for v in s.lower().split("x")),
                    default=(1080, 1920))
    ap.add_argument("--zoom", type=float, default=0.08,
                    help="total push-in as a fraction (0.08 = 8 percent)")
    ap.add_argument("--transition", type=float, default=0.9,
                    help="crossfade seconds")
    ap.add_argument("--crf", type=int, default=17)
    args = ap.parse_args()

    out, dur = render(args)
    print(f"wrote {out}  ({dur:.2f}s, {args.size[0]}x{args.size[1]} @ {args.fps}fps)")


if __name__ == "__main__":
    main()
