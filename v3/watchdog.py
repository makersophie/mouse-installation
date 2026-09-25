#!/usr/bin/env python3
"""
Reset button + hang detector for the mouse installation.

Runs as its own process, deliberately: if mouse_video.py hangs, anything living
inside it hangs too. A separate supervisor can still act.

  short press  restart the installation
  hold 3s      reboot the Pi
  automatic    restart if ~/mouse.log stops updating (the program writes it
               twice a second, so a stale file means it is wedged or dead)

WIRING — no resistor needed, the pull-up is internal:

    button leg 1  ->  GPIO 17   (physical pin 11)
    button leg 2  ->  GND       (physical pin 9)

Pressing connects the pin to ground; the code reads that as a press.
Change BUTTON_PIN below if you wire it elsewhere. Set BUTTON_PIN = None to run
as a hang detector only, with no button attached.

    python3 watchdog.py
    python3 watchdog.py --test    # report button presses only, restart nothing
"""
import os
import subprocess
import sys
import time

# Module level, not a local inside main(): gpiozero stops delivering events if
# the Button object is ever garbage collected, and a stray local makes that
# possible. Keeping the reference here removes the question entirely.
BUTTON = None

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "mouse_video.py")
LOGFILE = os.path.expanduser("~/mouse.log")
EVENTS_FILE = os.path.expanduser("~/mouse_events.log")   # shown by the monitor

BUTTON_PIN = 17
STALE_SECONDS = 15.0      # log older than this = wedged
CHECK_EVERY = 2.0
GRACE_SECONDS = 25.0      # after a restart, allow time to come up


def launch():
    """Start the installation with the display environment it needs. Over SSH
    or from a service there is no display set, so provide it explicitly."""
    env = os.environ.copy()
    env.setdefault("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")
    subprocess.Popen([sys.executable, TARGET], env=env,
                     start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def note(msg):
    """Add a line to the event log the monitor page shows, so a restart at 3am
    is still visible in the morning."""
    try:
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "  watchdog: " + msg + "\n")
    except OSError:
        pass


def restart(reason):
    print(f"[{time.strftime('%H:%M:%S')}] restarting — {reason}", flush=True)
    note(f"restarting — {reason}")
    subprocess.run(["pkill", "-f", "mouse_video.py"])
    subprocess.run(["pkill", "mpv"])
    time.sleep(2)
    try:
        os.remove(LOGFILE)          # so a stale log can't retrigger us
    except OSError:
        pass
    launch()
    return time.time() + GRACE_SECONDS


def reboot():
    print("hold detected — rebooting", flush=True)
    note("button held — rebooting the Pi")
    subprocess.run(["sudo", "reboot"])


def running():
    return subprocess.run(["pgrep", "-f", "mouse_video.py"],
                          stdout=subprocess.DEVNULL).returncode == 0


def log_age():
    try:
        return time.time() - os.path.getmtime(LOGFILE)
    except OSError:
        return None


def main():
    quiet_until = time.time() + GRACE_SECONDS
    pending = []

    test_only = "--test" in sys.argv

    if BUTTON_PIN is not None:
        global BUTTON
        try:
            from gpiozero import Button
            BUTTON = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05, hold_time=3)

            def on_press():
                print(f"[{time.strftime('%H:%M:%S')}] button pressed", flush=True)
                pending.append("button")

            def on_release():
                print(f"[{time.strftime('%H:%M:%S')}] button released", flush=True)

            def on_hold():
                print(f"[{time.strftime('%H:%M:%S')}] button held", flush=True)
                pending.append("hold")

            BUTTON.when_pressed = on_press
            BUTTON.when_released = on_release
            BUTTON.when_held = on_hold
            print(f"button on GPIO {BUTTON_PIN} (to GND) — press to restart, "
                  f"hold 3s to reboot", flush=True)
            print(f"  idle reads {'HIGH (correct)' if not BUTTON.is_pressed else 'LOW — stuck closed?'}",
                  flush=True)
        except Exception as e:
            print(f"no button: {e}\n  (running as a hang detector only)", flush=True)

    if test_only:
        print("\n--test: reporting button events only, nothing will be "
              "restarted. Ctrl+C to stop.\n", flush=True)
        while True:
            time.sleep(0.2)

    print(f"watching {LOGFILE}, stale after {STALE_SECONDS:.0f}s", flush=True)
    while True:
        if pending:
            what = pending.pop()
            pending.clear()
            if what == "hold":
                reboot()
            else:
                quiet_until = restart("button pressed")
            time.sleep(1)
            continue

        if time.time() >= quiet_until:
            age = log_age()
            if not running():
                quiet_until = restart("not running")
            elif age is not None and age > STALE_SECONDS:
                quiet_until = restart(f"log stale for {age:.0f}s")

        time.sleep(0.1 if BUTTON_PIN is not None else CHECK_EVERY)


if __name__ == "__main__":
    main()
