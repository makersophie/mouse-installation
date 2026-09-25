# Sound-Reactive Mouse Installation

A screen-based interactive installation for the studio kitchen. Mice live in a
hole in the wall. When the room has been quiet for long enough one of them creeps
out and settles in. The moment it hears a sound it rushes back into the wall.
Every so often a dog turns up instead.

Runs standalone on a Raspberry Pi connected to a screen, with a USB microphone.
The microphone reads the current sound *level* only — nothing is recorded.

## The three versions

| | What it is | Status |
|---|---|---|
| **[v1/](v1/)** | The original prototype. Four video clips of plush mice, a fixed sound threshold, one mouse. | Archived |
| **[v2/](v2/)** | `prototype.html` — a browser tool for tuning timing and speed against the real photos, on a laptop. | Live tool |
| **[v3/](v3/)** | The installation as it runs. Hand-made stop-motion, seven mouse characters, two dog easter eggs, a loading sequence. | **Current** |

## v3 — what runs in the kitchen

Seven characters (`taro`, `tequila`, `jerry`, `sam_and_ham`, `shrek`, `gusgus`,
`marshmallow`), each with three shot sequences, plus two dogs and a loading
sequence. 274 photographs in all.

```
0 base   the wall, no mouse          4 easter egg   the dogs
1 out    comes out                   5 loading      startup
2 loop   stays, loops
3 in     goes back in                1R             rewind of 1
```

```
Normal:      0 - 1 - 2 (loops until sound) - 3 - 0
Easter egg:  0 - 4 - 0          Startup:  0 - 5 - 0
```

A sound during **1** rewinds it (`1 - 1R - 0`) rather than cutting to **3** — the
mouse turns around from exactly the frame it had reached. A sound during **2**
releases the loop straight into **3**.

Each character's `out + loop + in` is encoded as **one continuous file**, so
those transitions involve no file load and no gap at all.

Full detail in **[v3/SCENES.md](v3/SCENES.md)**.

## v2 — tuning in a browser

Open `v2/prototype.html` in Chrome, point it at your photo folder, and it finds
the characters and sequences by itself. Runs the same state machine as the Pi
and reads and writes the same `scenes.json`, so tuning in the browser *is*
tuning the installation — there is no second set of numbers to keep in step.

Load `frames_preview/` rather than `frames/`: the full-resolution stills are
~6.5 GB decoded and the browser will not survive them.

## Running it

Photos and encoded clips are large and are **not** in this repo:

```
frames/          the photographs, on the Pi
build/           clips built from them by build_scenes.py
```

```bash
cd v3
python3 build_scenes.py     # photos -> clips
python3 mouse_video.py      # run
```

While it runs, **http://raspberrypi.local:8080** (from any laptop or phone on the
same network) shows a live monitor: what the mic hears against the threshold,
the current state, and an event log. See
[TROUBLESHOOTING.md](v3/TROUBLESHOOTING.md#the-monitor-page).

`watchdog.py` adds a hardware reset button on GPIO 17 and restarts the program
automatically if it stops responding. Register it in `~/.config/labwc/autostart`
to bring everything up on boot.

## Documentation

- **[v3/SCENES.md](v3/SCENES.md)** — how the scenes are organised: the state
  machine, speed, rewinding, thresholds, and a tuning cheat-sheet. Read this to
  change how the piece behaves.
- **[v3/TROUBLESHOOTING.md](v3/TROUBLESHOOTING.md)** — every problem hit while
  building this and how each was solved. Read it before changing the playback or
  audio code.

## Working on this together

Clone, change, commit, push. Pull before each session. Photos and clips are
shared separately and live next to the program on the Pi.
