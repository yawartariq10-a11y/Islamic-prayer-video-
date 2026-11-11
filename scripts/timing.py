"""Narration-driven timeline for the reel.

The reel has seven narration sections:
    intro, fajr, dhuhr, asr, maghrib, isha, closing

Timing priority (first match wins):
  1. timing.json in the project root  -> explicit section start times (seconds)
  2. voiceover.mp3 in the project root -> section starts found automatically from
     the six longest pauses in the narration (ffmpeg silencedetect)
  3. the default narration timing below (silent preview)

All animation in build_scene.py is expressed relative to these section starts,
so re-running the build after adding a voiceover re-syncs everything.
"""
import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 30
SECTIONS = ["intro", "fajr", "dhuhr", "asr", "maghrib", "isha", "closing"]

# Default (silent preview) timing, matched to the narration script in NARRATION.md
DEFAULT_STARTS = {
    "intro": 0.0,
    "fajr": 9.0,
    "dhuhr": 14.5,
    "asr": 20.0,
    "maghrib": 26.5,
    "isha": 32.0,
    "closing": 37.5,
}
DEFAULT_END = 45.0
# Seconds of hold after the last word of the voiceover before the reel ends.
END_HOLD = 3.0
# Minimum length of the closing section so the final line can be read.
MIN_CLOSING = 7.0


def _probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def _silences(path, noise_db=-35, min_d=0.25):
    res = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af",
         f"silencedetect=noise={noise_db}dB:d={min_d}", "-f", "null", "-"],
        capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", res.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", res.stderr)]
    return list(zip(starts, ends))


def _from_voiceover(path):
    dur = _probe_duration(path)
    sil = _silences(path)
    speech_end = dur
    if sil and sil[-1][1] >= dur - 0.05:
        speech_end = sil[-1][0]
    # pauses strictly inside the speech
    inner = [(s, e) for s, e in sil if s > 0.5 and e < speech_end - 0.5]
    if len(inner) < 6:
        print(f"[timing] only {len(inner)} pauses found in voiceover; using proportional timing")
        scale = speech_end / (DEFAULT_STARTS["closing"] + 4.0)
        starts = {k: v * scale for k, v in DEFAULT_STARTS.items()}
    else:
        # the six longest pauses separate the seven sections
        longest = sorted(sorted(inner, key=lambda p: p[1] - p[0], reverse=True)[:6])
        starts = {"intro": 0.0}
        for name, (s, e) in zip(SECTIONS[1:], longest):
            # cut a little before speech resumes so the visual change leads the word
            starts[name] = max(s, e - 0.35)
    end = max(dur, speech_end + END_HOLD, starts["closing"] + MIN_CLOSING)
    return starts, end, dur


def load_timing():
    """Return dict with section starts (s), end (s), source and audio path."""
    tj = os.path.join(ROOT, "timing.json")
    vo = os.path.join(ROOT, "voiceover.mp3")
    audio = vo if os.path.exists(vo) else None
    if os.path.exists(tj):
        with open(tj) as f:
            data = json.load(f)
        starts = {k: float(data["starts"][k]) for k in SECTIONS}
        end = float(data.get("end", DEFAULT_END))
        if audio:
            end = max(end, _probe_duration(audio))
        src = "timing.json"
    elif audio:
        starts, end, _ = _from_voiceover(audio)
        src = "voiceover.mp3"
    else:
        starts, end, src = dict(DEFAULT_STARTS), DEFAULT_END, "default"
    return {"starts": starts, "end": end, "source": src, "audio": audio, "fps": FPS}


def frame(t):
    """Seconds -> 1-based frame number."""
    return int(round(t * FPS)) + 1


if __name__ == "__main__":
    t = load_timing()
    print(json.dumps(t, indent=2))
