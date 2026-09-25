# Troubleshooting Log

Everything that went wrong while building this, and how each was solved. If the
installation misbehaves, start here — most symptoms below have a known cause.

The single most important fix is #5 (mpv Vulkan → OpenGL). If the program runs
but nothing shows on screen, that's almost certainly it.

---

## 1. Black screen a few seconds into playback

**Symptom.** Video played, then the screen went black after a few seconds. It
came back whenever a sound was made.

**Cause.** The microphone was read on the main loop with a call that blocks for
about a second each time. That stall interfered with mpv's display and blanked
the screen.

**Fix.** Read the microphone in a **background (daemon) thread** that only
publishes the latest level into a shared variable. The main loop never blocks,
and mpv keeps displaying. This is why `audio_loop()` runs on its own thread.

---

## 2. Sound detection not sensitive enough

**Symptom.** After moving the mic off the main loop, short sounds (a single
clap) often didn't register.

**Cause.** We were recording a full 1-second chunk and averaging it, so a brief
sound was diluted across the second.

**Fix.** Switched to **sounddevice** reading small `0.05 s` blocks continuously.
Short sounds now show up immediately.

---

## 3. Microphone not found / wrong device index

**Symptom.** sounddevice couldn't open the mic, or read silence.

**Cause.** The **sounddevice index is not the ALSA card number**, and it changes
between machines and OS images. On the Pi Zero 2 W it was `1`; after moving to
the Pi 5 with the newer OS it was `0` — while ALSA still called the mic
`hw:2,0`.

**Fix.** Always confirm the index on the actual machine:

```bash
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```

Set `audio.device` in `scenes.json` to the number in front of the
`USB PnP Sound Device ... (N in, ...)` line.

---

## 4. Mouse never comes out

**Symptom.** The mouse stays hidden. In the log, `quiet` keeps resetting to `0`
and `state` stays `EMPTY`.

**Cause.** Background noise in the room is above the threshold, so the program
thinks there is always sound. Our threshold of `0.02` worked at home but the
classroom's ambient level sat around `0.022`, constantly retriggering.

**Fix.** This is what `"auto_threshold": true` now handles for you — see #12.
With it off, raise `audio.threshold` in `scenes.json`. Compare `vol=` and `thr=`
in `~/mouse.log`: the threshold wants to sit just above the room's resting
level. Too high and the mouse ignores real sounds; too low and it never comes
out.

---

## 5. Autostart runs, but the screen is frozen and the mouse never moves

**This was the big one — and the cause was not obvious.**

**Symptom.** On boot the program was clearly running (`pgrep -f mouse_video.py`
returned a PID) and `~/mouse.log` showed correct state changes (e.g.
`state=EATING`). But the screen stayed on the first frame, and mpv ignored every
command sent over its socket. Running the exact same program **manually** worked
fine.

**How we found it.** Running mpv directly in the terminal printed the real
error, which `--no-terminal` had been hiding:

```
[vo/gpu/libplacebo] vk->CreateSwapchainKHR(...): VK_ERROR_OUT_OF_HOST_MEMORY
[vo/gpu/libplacebo] Failed (re)creating swapchain!
```

**Cause.** mpv's default GPU backend on the Pi 5 is **Vulkan**, and creating the
Vulkan swapchain failed with out-of-memory. mpv then looped forever retrying, so
the process was alive but displayed nothing and stopped responding to socket
commands. The state machine kept running (hence the log looked healthy), but its
`loadfile` commands went nowhere.

**Fix.** Force mpv to use **OpenGL** instead of Vulkan by adding to the mpv
launch arguments:

```
--vo=gpu --gpu-api=opengl
```

With that, mpv displays correctly and responds to commands. This is in
`start_mpv()`.

**Debugging tip.** When mpv seems frozen, run one clip directly and read the
output:

```bash
XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 \
  mpv --vo=gpu --gpu-api=opengl --fullscreen --loop-file=inf build/<clip>.mp4
```

---

## 6. Wayland vs X11 environment (labwc)

**Background.** Current Raspberry Pi OS uses the **labwc** Wayland compositor,
not X11. That affects how you point mpv at the screen.

- **Manual run over SSH:** the SSH session has no display set, so provide it:
  `XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0 python3 mouse_video.py`.
  The socket name (`wayland-0`) can be confirmed with
  `ls /run/user/$(id -u)/wayland-*`. `DISPLAY=:0` also works via Xwayland.
- **Autostart:** labwc's `~/.config/labwc/autostart` is run after the desktop is
  up and already provides `WAYLAND_DISPLAY`, so the program finds the screen
  without extra setup. Our wrapper still exports the variables to be safe.

**Gotcha.** labwc will not run `autostart` unless that file is **executable**:

```bash
chmod +x ~/.config/labwc/autostart
```

---

## 7. Screen goes blank when idle (screen blanking)

**Note.** We suspected screen blanking early on, but it turned out the "black
screen" was #1 (mic blocking), confirmed because a single looping mpv never
blanked. If you *do* see true idle blanking on labwc, it is controlled by
`swayidle` in `~/.config/labwc/autostart`; a single always-updating video
usually keeps the screen awake anyway.

---

## 8. Fullscreen offset to the bottom-right after a power-cut reboot

**Symptom.** Once, after pulling power, the video wasn't centered/fullscreen —
it sat toward the bottom-right.

**Status.** The screen resolution was still correct (1920x1080), so this was an
mpv/HDMI timing hiccup at boot, not a resolution change. A clean reboot restored
it. If it recurs often, add explicit geometry to mpv (e.g. `--geometry=100%x100%+0+0`)
and consider avoiding hard power-cuts.

---

## 9. The mouse skipped its emerge and appeared instantly

**Symptom.** Now and then the emerge sequence didn't play — the mouse was just
suddenly out and eating.

**Cause.** `near_end()` asked mpv for `time-remaining` immediately after
`loadfile`. mpv hadn't loaded the new clip yet, so it answered about the clip
that had just been *replaced* — which was at its end. The state machine read
that as "emerge finished" and jumped straight to the idle.

**Fix.** mpv's properties are now watched with `observe_property` and cached by
a reader thread, tagged with the file they belong to. `progress()` refuses to
answer unless the reported `path` matches the file we actually asked for, so a
stale number can't be mistaken for the current one.

---

## 10. mpv stopped responding after running for a long time

**Symptom.** After hours, mpv ignored socket commands — the same symptom as #5,
but with OpenGL already in use.

**Cause.** mpv pushes *events* down the IPC socket continuously, and the old
code only ever read from that socket inside `get_property()`. Unread bytes
accumulated in the kernel buffer until it filled, at which point mpv blocked
trying to write to it and stopped servicing commands.

**Fix.** A dedicated reader thread drains the socket continuously. Nothing is
ever left unread.

---

## 11. Short claps sometimes ignored

**Symptom.** A single sharp clap occasionally didn't send the mouse back, even
with the threshold set correctly.

**Two causes, both fixed.**

1. `sd.rec()` was called in a loop, which opens a stream, records a block, and
   closes it again. The mic was **deaf in the gap between blocks**, so a short
   sound landing in a gap was never seen. It is now a continuous
   `sd.InputStream` with a callback — no gaps.

2. The debounce counted *main-loop iterations* above the threshold. The main
   loop spins every 30ms but the mic only produces a sample every 50ms, so
   three "consecutive loud reads" were often the same sample counted three
   times — the debounce wasn't debouncing anything. It now counts distinct mic
   samples within `flee_hit_window`.

---

## 12. Threshold has to be re-tuned in every room

**Symptom.** A threshold tuned at home left the mouse permanently hidden in the
classroom (this is #4).

**Fix.** `"auto_threshold": true` in `scenes.json` measures the room's own noise
floor over a rolling 30 seconds and sets the trigger at `noise_margin` times
that. The fridge and the extractor fan get learned instead of fought. `thr=` in
`~/mouse.log` shows the live value. Set it to `false` to go back to a fixed
number.

---

## 13. mpv crashed and the piece ran blind

**Symptom.** A dead mpv left the program looping forever against nothing; the
log looked healthy but the screen was frozen.

**Fix.** The main loop checks `mpv_proc.poll()` each pass and relaunches mpv
into the empty scene if it has died.

---

## 14. Visible lag when one sequence changes to the next

**Symptom.** A hitch each time the mouse went from coming out, to looping, to
going back in.

**Cause.** Every transition was an mpv `loadfile`, which tears down the demuxer
and decoder and opens a new file — a couple of hundred milliseconds on the Pi.
Against clips as short as 0.4s that reads as a stutter.

**Fix, in two parts.**

1. Each character's out, loop and in are now encoded into **one continuous
   file** (`<name>__main.mp4`), with the boundaries between them written to
   `build/segments.json`. The loop is held with mpv's `ab-loop-a`/`ab-loop-b`,
   and releasing it lets playback run straight on into the in sequence. Those
   two transitions involve no load, no seek, and no gap — they are just
   playback continuing.
2. Clips are encoded **all-intra** (`-g 1 -bf 0`), so the first frame after a
   real load appears immediately, and mpv runs with `--audio=no --cache=no` and
   a trimmed lavf probe.

The only load left mid-mouse is `1 - 1R`, because the rewind runs the other way
down a separate file. That one is a startle anyway.

**If you change fps or sequences,** re-run `build_scenes.py` — the segment
boundaries are recomputed with the clips, and a stale `segments.json` would put
the loop in the wrong place.

---

## 15. Mouse stays out, looping, and ignores every sound

**Symptom.** After running a while the mouse sits in its loop forever. Claps do
nothing. The program is running, `~/mouse.log` keeps updating and says
`mic=ok` — but `vol=` never changes. The watchdog doesn't restart anything,
because the log looks fresh.

**Cause.** The USB mic's stream stopped delivering (a USB hiccup, a brown-out, a
knock to the cable). sounddevice simply stops calling the callback; nothing
raises an error. The last level and status stay frozen at their last values, so
everything *looked* healthy while `is_loud()` could never be True again. And a
mic that failed to open at boot was never retried.

**Fix.** `Mic` now has a supervisor thread. If no sample has arrived for
`audio.stale_seconds` (2s), or the stream has stopped or errored, it closes the
stream, restarts PortAudio (so a replugged mic is found again), and reopens —
trying `audio.device` first, then any input whose name contains
`audio.device_name` (`"USB"`), since the number shifts between boots (#3).
`~/mouse.log` shows `mic_age=` — seconds since the last sample — and
`mic=stalled: …` while it is recovering. Every loss and recovery goes in the
event log.

---

## 16. Screen frozen on one frame, program still running

**Symptom.** Same picture as #5/#10: the log changes state, the screen doesn't.

**Fix.** The main loop watches mpv's playback position. Every clip either loops
or is left within seconds, so a position that hasn't moved for 12s means mpv has
stopped responding; the program kills it and the existing check relaunches it
into the empty scene. Also fixed: a relaunched mpv used to leave the previous
socket reader running, and two readers on one socket drop messages. And state
`OUT` now gives up after 5s if mpv never reports a position for the clip.

---

## The monitor page

With the installation running, open **http://raspberrypi.local:8080** from a
laptop or phone on the same Wi-Fi. It shows:

- **Microphone** — "last sample … ms ago" is the heartbeat. If it climbs past
  2s the mic is dead (#15), whatever the status says.
- **Sound level** — the live level against the threshold and the room's noise
  floor, with ▲ where a sound was detected and the state changes marked. Clap:
  the bar should cross the red line.
- **State / quiet timer / video** — where the state machine is and whether mpv's
  position is moving (#16).
- **Event log** — history from `~/mouse_events.log`, which survives restarts and
  includes the watchdog's restarts and button presses. **copy** puts it on the
  clipboard to paste into an issue or a chat.
- A one-line **diagnosis** at the top, in plain words.

The page is read-only. It cannot listen for itself: a USB mic can be held by one
program at a time. For the same reason, stop the installation before running
`mic_check.py`. Change the port with `"monitor": {"port": 8080}` in
`scenes.json`; `0` turns the page off.

---

## Quick diagnosis checklist

```bash
pgrep -f mouse_video.py        # is the program running?
pgrep -f mpv | wc -l           # exactly one mpv should be running
cat ~/mouse.log                # vol / thr / state / character / quiet — read it twice
tail -30 ~/mouse_events.log    # what happened, and when — or open the monitor page
ls build/*.mp4 | wc -l         # clips built? if 0, run: python3 build_scenes.py
python3 build_scenes.py --check  # validate scenes.json without encoding
ls -l /tmp/mpvsocket           # mpv control socket should exist
```

- Program running, log updates, but screen frozen → **#5 (use OpenGL)**, or
  **#10** if it had been running for hours.
- `mic=error` in the log → **#3 (wrong DEVICE index)**.
- Mouse out, looping, deaf; `mic_age=` keeps growing → **#15** (should now
  recover by itself within a few seconds; if not, reseat the USB mic).
- `quiet` never climbs, mouse hidden → **#4 / #12 (threshold vs. the room)**.
- Mouse appears without playing its emerge → **#9**.
- A clap is sometimes ignored → **#11**.
- `Missing clips` on startup → run `python3 build_scenes.py`.
- Black screen only when the mic reads → **#1 (mic must be on a thread)**.
