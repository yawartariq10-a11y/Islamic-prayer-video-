# Why Do We Pray Five Times a Day? — 3D reel

A vertical 1080 × 1920, 30 fps reel of about 45 seconds, built and animated entirely
with Blender and Python.

- **Video:** `out/five-daily-prayers.mp4`
- **Editable Blender project:** `blender/five_daily_prayers.blend` (Blender 4.2 or later, textures and fonts packed)
- **Narration script:** `NARRATION.md`

## The scene

There is one room and one mat throughout:

- **Room:** sage-green walls, a cream plaster arch around an arched window, and walnut planks running toward the qibla wall.
- **Mat:** an emerald prayer mat with a geometric gold border, woven bump and fringes. It unrolls in the opening shot.
- **Figure:** a single faceless worshipper in a loose cream thobe and kufi, modelled from the reference sheets in `assets/reference/`. The camera always stays behind them. The pose changes with each prayer: qiyam → rukūʿ → sujūd → jalsa → qiyam.
- **Outside the window:** a sky backdrop with a horizon, a dome-and-minaret silhouette, a sun disc, stars and a sun glow, all animated through the day.

| Section | Light | On screen |
|---|---|---|
| Opening | Mat unrolls close-up, camera pulls back | WHY DO WE PRAY / FIVE TIMES A DAY? (two beats) |
| Fajr | Cool blue, thin dawn band, sun below the horizon | FAJR · DAWN TO SUNRISE |
| Dhuhr | Bright warm daylight, sun just past its highest point, short shadow | DHUHR · AFTER SOLAR NOON |
| Asr | Amber light, window shadow stretches across the floor | ASR · AFTERNOON + "Check your local timetable for the exact start." |
| Maghrib | Sun sinks below the horizon, rose and orange sky | MAGHRIB · JUST AFTER SUNSET |
| Isha | Glow fades to navy, lantern lights the mat | ISHA · AFTER TWILIGHT |
| Closing | Gentle pull-back | All five names in order + "Check your local mosque's prayer timetable." |

Text sits in a column nudged left of centre (x ≈ 70–910 px) and in the top half of the frame (y < 1250 px). That keeps it clear of the TikTok and Reels UI at the bottom and right.

## Building it

```bash
# Blender 4.2 as a Python module (Python 3.11)
uv venv -p python3.11 .venv && uv pip install -p .venv/bin/python bpy==4.2.0 pillow
PYTHON=.venv/bin/python ./make_reel.sh
```

`make_reel.sh` runs these steps in order:

1. `scripts/make_textures.py` generates the mat and walnut textures.
2. `scripts/build_scene.py` builds and animates everything and saves the .blend.
3. `scripts/render.py` renders the frames with EEVEE. It is resumable, and `--times 12 30 --scale 25` renders quick stills.
4. ffmpeg encodes the MP4 with a soft vignette.

## Voiceover sync

All animation is keyed to section start times from `scripts/timing.py`:

1. **`timing.json`**, if present, sets the times by hand (see `timing.example.json`).
2. **`voiceover.mp3`**, if present: the six longest pauses become the section cuts, the reel length follows the narration plus a 3-second hold, and the voiceover is the only audio in the MP4.
3. Otherwise the default 45-second timing is used and a **silent preview** is rendered.

Drop in `voiceover.mp3` and re-run `./make_reel.sh` to re-sync.

Fonts: EB Garamond and Montserrat (SIL Open Font License).
