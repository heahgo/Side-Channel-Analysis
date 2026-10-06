#!/usr/bin/env bash
# Copy the ML-KEM implementations used by the firmware from a pqm4 checkout into
# firmware/mcu/pqm4, keeping pqm4's own directory layout and resolving its
# symlinks into real files (Windows-safe).
#
#   tools/import_pqm4.sh /path/to/pqm4      (pqm4 cloned with --recursive)
set -euo pipefail
PQM4="$(cd "${1:?usage: $0 /path/to/pqm4}" && pwd)"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST="$ROOT/firmware/mcu/pqm4"

rm -rf "$DST/crypto_kem" "$DST/common" "$DST/mupq" "$DST/VERSION"
mkdir -p "$DST/common" "$DST/mupq/common"

# Keccak permutation (pqm4/common) and FIPS 202 / randombytes / compat (pqm4/mupq/common)
cp -L "$PQM4/common/keccakf1600.S" "$DST/common/"
cp -L "$PQM4/mupq/common/fips202.c" "$PQM4/mupq/common/fips202.h" \
      "$PQM4/mupq/common/keccakf1600.h" "$PQM4/mupq/common/randombytes.h" \
      "$PQM4/mupq/common/compat.h" "$DST/mupq/common/"

for n in 512 768 1024; do
  for impl in m4fspeed m4fstack; do
    d="crypto_kem/ml-kem-$n/$impl"
    mkdir -p "$DST/$d"
    cp -L "$PQM4/$d"/* "$DST/$d/"
  done
  d="mupq/pqclean/crypto_kem/ml-kem-$n/clean"
  mkdir -p "$DST/$d"
  ( cd "$PQM4/$d" && cp -L *.c *.h LICENSE "$DST/$d/" )
done

cat > "$DST/VERSION" <<EOV
pqm4   $(git -C "$PQM4" rev-parse HEAD 2>/dev/null || echo unknown)
mupq   $(git -C "$PQM4/mupq" rev-parse HEAD 2>/dev/null || echo unknown)
EOV
echo "imported into $DST"
cat "$DST/VERSION"
