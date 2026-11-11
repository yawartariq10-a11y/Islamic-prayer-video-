# Narration — "Why Do We Pray Five Times a Day?"

Target length is about 45 seconds at a calm pace (~2.4 words per second).
Record it as **one take** and leave a clear pause (about half a second or more)
between the seven sections below. `scripts/timing.py` finds the six longest
pauses and uses them as the section cuts, so every prayer name appears when its
line starts.

| # | Section | Default start | Line |
|---|---------|---------------|------|
| 1 | Intro   | 0.0 s  | *(about 1.5 s of quiet while the mat unrolls)* Why do we pray five times a day? On the Night Journey, the Prophet, peace be upon him, was given the five daily prayers: a gift that brings us back to Allah throughout the day. |
| 2 | Fajr    | 9.0 s  | Fajr is prayed at dawn, from first light until sunrise. |
| 3 | Dhuhr   | 14.5 s | Dhuhr begins just after the sun passes its highest point. |
| 4 | Asr     | 20.0 s | Asr is the afternoon prayer, as the shadows grow long. Check your local timetable for the exact start. |
| 5 | Maghrib | 26.5 s | Maghrib is prayed just after the sun has set. |
| 6 | Isha    | 32.0 s | And Isha, once the last light of twilight has faded. |
| 7 | Closing | 37.5 s | Five prayers, from dawn until night. Check your local mosque's prayer timetable. |

The reel ends about 3 seconds after the last word (minimum 7 seconds for the
closing section) so the final line stays on screen long enough to read.

On screen, the Night Journey appears only in the narration. No visuals depict it.

## Syncing a recorded voiceover

1. Save the recording as `voiceover.mp3` in the project root.
2. Run `./make_reel.sh`. It rebuilds the scene against the voiceover and renders.
   The voiceover is the only audio in the MP4.
3. If a pause is detected in the wrong place, copy `timing.example.json` to
   `timing.json`, set the start times by hand, and run it again. `timing.json`
   always takes priority.
