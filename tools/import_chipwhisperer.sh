#!/usr/bin/env bash
# Copy the parts of the ChipWhisperer firmware build system this repository needs
# into firmware/mcu (and jupyter/Setup_Scripts), at the same paths as in ChipWhisperer. The STM32F4 HAL comes
# from the firmware/mcu/hal/chipwhisperer-fw-extra submodule, not from this script.
#
#   tools/import_chipwhisperer.sh /path/to/chipwhisperer
set -euo pipefail
CW="$(cd "${1:?usage: $0 /path/to/chipwhisperer}" && pwd)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$CW/firmware/mcu"
DST="$ROOT/firmware/mcu"

FILES=(
  Makefile.inc
  crypto/Makefile.crypto
  hal/Makefile.hal
  hal/PLATFORM_INCLUDE.mk
  hal/hal.c
  hal/hal.h
  simpleserial/Makefile.simpleserial
  simpleserial/simpleserial.c
  simpleserial/simpleserial.h
)
for f in "${FILES[@]}"; do
  mkdir -p "$DST/$(dirname "$f")"
  cp "$SRC/$f" "$DST/$f"
done
cp "$CW/LICENSE.txt" "$DST/LICENSE-chipwhisperer.txt"

# Jupyter setup script (scope / target / prog / reset_target), same path as in ChipWhisperer.
# In ChipWhisperer, jupyter/ is a submodule (chipwhisperer-jupyter); take the commit it pins.
JUP=$(git -C "$CW" ls-tree HEAD jupyter 2>/dev/null | awk '{print $3}')
mkdir -p "$ROOT/jupyter/Setup_Scripts"
if [ -n "$JUP" ] && curl -sSf -o "$ROOT/jupyter/Setup_Scripts/Setup_Generic.ipynb" \
     "https://raw.githubusercontent.com/newaetech/chipwhisperer-jupyter/$JUP/Setup_Scripts/Setup_Generic.ipynb"; then
  JUP_NOTE="chipwhisperer-jupyter $JUP"
else
  cp "$CW/jupyter/Setup_Scripts/Setup_Generic.ipynb" "$ROOT/jupyter/Setup_Scripts/"
  JUP_NOTE="chipwhisperer-jupyter (copied from local checkout)"
fi

printf "chipwhisperer %s\n%s\n" "$(git -C "$CW" rev-parse HEAD 2>/dev/null || echo unknown)" "$JUP_NOTE" > "$DST/CHIPWHISPERER_VERSION"
echo "copied ${#FILES[@]} files from $CW"
cat "$DST/CHIPWHISPERER_VERSION"
