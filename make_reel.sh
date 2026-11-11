#!/usr/bin/env bash
# Build the Blender scene, render every frame and encode out/five-daily-prayers.mp4.
#
#   ./make_reel.sh               full pipeline (resumes an interrupted render)
#   ./make_reel.sh --encode-only re-encode existing frames
#
# PYTHON must point at a Python that can `import bpy` (Blender 4.2 as a module,
# e.g. `pip install bpy==4.2.0` on Python 3.11) or use Blender itself:
#   PYTHON="blender -b --python-exit-code 1 --python" ./make_reel.sh
set -euo pipefail
cd "$(dirname "$0")"
PYTHON=${PYTHON:-python3}
FRAMES=out/frames
OUT=out/five-daily-prayers.mp4

if [[ "${1:-}" != "--encode-only" ]]; then
  $PYTHON scripts/make_textures.py
  $PYTHON scripts/build_scene.py
  # stale frames from an older timeline would be wrong -> clear when the blend is newer
  if [[ -d $FRAMES && -n "$(find blender/five_daily_prayers.blend -newer "$FRAMES" 2>/dev/null)" ]]; then
    rm -rf "$FRAMES"
  fi
  $PYTHON scripts/render.py
fi

N=$(ls "$FRAMES"/*.png | wc -l)
FPS=30
mkdir -p out
if [[ -f voiceover.mp3 ]]; then
  echo "Encoding $N frames with voiceover.mp3 as the only audio"
  ffmpeg -y -hide_banner -loglevel warning -framerate $FPS -start_number 1 -i "$FRAMES/%04d.png" \
    -i voiceover.mp3 -map 0:v -map 1:a \
    -vf "vignette=angle=PI/6:mode=forward" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -profile:v high -level 4.2 \
    -c:a aac -b:a 192k -af apad -shortest -movflags +faststart "$OUT"
else
  echo "voiceover.mp3 not found: encoding a silent preview ($N frames)"
  ffmpeg -y -hide_banner -loglevel warning -framerate $FPS -start_number 1 -i "$FRAMES/%04d.png" \
    -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=48000 -map 0:v -map 1:a \
    -vf "vignette=angle=PI/6:mode=forward" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -profile:v high -level 4.2 \
    -c:a aac -b:a 128k -shortest -movflags +faststart "$OUT"
fi
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate:format=duration -of compact "$OUT"
