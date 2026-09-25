#!/bin/bash
# Copy the installation onto the Raspberry Pi, which runs it standalone.
#
#   ./deploy.sh                          program + config + clips (fast)
#   ./deploy.sh --with-photos            also send frames/ (~2GB, first time)
#   ./deploy.sh --with-photos user@host /home/user /Volumes/JuJu/_SVA/mouse-installation
#
# With the photos on the Pi, everything lives there: build and run on the Pi and
# nothing else needs to be attached.
set -e
cd "$(dirname "$(readlink -f "$0")")"

PHOTOS=0
if [ "$1" = "--with-photos" ]; then PHOTOS=1; shift; fi
TARGET="${1:-sophie@raspberrypi.local}"
DEST="${2:-/home/sophie/mouse-installation}"
SRC="${3:-/Volumes/JuJu/_SVA/mouse-installation}"

echo "Sending to $TARGET:$DEST"
ssh "$TARGET" "mkdir -p '$DEST'"

rsync -avh --progress \
  mouse_video.py monitor.html build_scenes.py mic_check.py diagnose_loop.py watchdog.py scenes.json start_mouse.sh requirements.txt \
  "$TARGET:$DEST/"

if [ "$PHOTOS" = "1" ]; then
  [ -d "$SRC/frames" ] || { echo "No frames/ at $SRC — is the drive mounted?"; exit 1; }
  echo
  echo "Sending photos ($(du -sh "$SRC/frames" | cut -f1)). Interrupt and re-run to resume."
  rsync -avh --partial --progress "$SRC/frames/" "$TARGET:$DEST/frames/"
fi

if [ -d build ] && [ -n "$(ls -A build/*.mp4 2>/dev/null)" ]; then
  rsync -avh --delete --progress build/ "$TARGET:$DEST/build/"
fi

cat <<MSG

Done. On the Pi:
    sudo apt install mpv ffmpeg libportaudio2
    pip install numpy sounddevice --break-system-packages
    cd $DEST
    python3 build_scenes.py     # photos -> clips (slow the first time)
    python3 mouse_video.py
MSG
