#!/bin/bash
set -euo pipefail
# Optional: Datafox DFCom (libDFCom.so) von datafox.de laden und lokal bauen.
# Die Bibliothek ist Software von Datafox GmbH, nicht Teil von Opentakt Zeit (AGPL).
# Wir spiegeln das SDK nicht. HTTP-Terminals funktionieren ohne dieses Skript.
#
# Als root (Produktion):
#   bash deploy/install-dfcom.sh
# Ergebnis: /opt/zeiterfassung/lib/libDFCom.so
#
# Ohne root / anderer Pfad:
#   DFCOM_LIBDIR=$HOME/lib bash deploy/install-dfcom.sh
#
# Air-Gap: Zip selbst von Datafox laden, dann
#   DFCOM_ZIP=/pfad/Datafox-DFComDLL-04.03.23-Source.zip bash deploy/install-dfcom.sh

DFCOM_VERSION="${DFCOM_VERSION:-04.03.23}"
DFCOM_URL="${DFCOM_URL:-https://www.datafox.de/download/Datafox%20DFComDLL%20${DFCOM_VERSION}-Source.zip}"
# SHA-256 des offiziellen Source-Zips 04.03.23 (Stand Prüfung 2026-09-07).
DFCOM_SHA256="${DFCOM_SHA256:-2d314c97d2733ed88c0e8ffe6c2c0cab5e0c5dfe410274d73f961a0a92bc8a35}"
DFCOM_SKIP_HASH="${DFCOM_SKIP_HASH:-0}"

if [ "$(id -u)" -eq 0 ]; then
  DFCOM_LIBDIR="${DFCOM_LIBDIR:-/opt/zeiterfassung/lib}"
else
  REPO="${REPO:-$(cd "$(dirname "$0")/.." && pwd)}"
  DFCOM_LIBDIR="${DFCOM_LIBDIR:-$REPO/lib}"
fi

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Es fehlt: $1" >&2
    exit 1
  }
}

install_build_deps() {
  if [ "$(id -u)" -ne 0 ]; then
    return 0
  fi
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y --no-install-recommends \
    ca-certificates curl unzip make g++
}

verify_hash() {
  local file="$1"
  local expect="$2"
  local got
  got=$(sha256sum "$file" | awk '{print $1}')
  if [ "$got" != "$expect" ]; then
    echo "SHA-256 stimmt nicht:" >&2
    echo "  erwartet $expect" >&2
    echo "  erhalten $got" >&2
    echo "URL oder Datei prüfen. DFCOM_SKIP_HASH=1 nur wenn ihr die Datei selbst geprüft habt." >&2
    exit 1
  fi
}

echo "Datafox DFCom $DFCOM_VERSION — Download von datafox.de, Bau lokal."
echo "DFCom bleibt Software von Datafox GmbH. Opentakt Zeit liefert sie nicht mit."

install_build_deps
need curl
need unzip
need make
need g++
need sha256sum

WORKDIR=$(mktemp -d /tmp/opentakt-dfcom-XXXXXX)
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

ZIP="$WORKDIR/dfcom-source.zip"
if [ -n "${DFCOM_ZIP:-}" ]; then
  if [ ! -f "$DFCOM_ZIP" ]; then
    echo "DFCOM_ZIP nicht gefunden: $DFCOM_ZIP" >&2
    exit 1
  fi
  cp "$DFCOM_ZIP" "$ZIP"
else
  echo "Lade $DFCOM_URL"
  if ! curl -fL --retry 3 --retry-delay 2 -A "opentakt-zeit-install-dfcom" -o "$ZIP" "$DFCOM_URL"; then
    echo "Download fehlgeschlagen. Zip von Datafox laden und DFCOM_ZIP=/pfad/zur.zip setzen." >&2
    echo "Dokumentation: https://www.datafox.de/files/html_en/dfc_using_library.html" >&2
    exit 1
  fi
fi

if [ "$DFCOM_SKIP_HASH" != "1" ]; then
  verify_hash "$ZIP" "$DFCOM_SHA256"
fi

unzip -q -o "$ZIP" -d "$WORKDIR/src"
LIBDIR=$(find "$WORKDIR/src" -type d -name DatafoxLibraryIV | head -n 1)
if [ -z "$LIBDIR" ] || [ ! -f "$LIBDIR/Makefile" ]; then
  echo "Im Zip fehlt DatafoxLibraryIV/Makefile — anderes SDK-Paket?" >&2
  exit 1
fi

echo "Baue libDFCom.so in $LIBDIR"
mkdir -p "$LIBDIR/Release"
# Nur die Shared Library, nicht die Beispielprogramme.
make -C "$LIBDIR" -j"$(nproc 2>/dev/null || echo 2)" Release/libDFCom.so

SO="$LIBDIR/Release/libDFCom.so"
if [ ! -f "$SO" ]; then
  echo "Build ohne libDFCom.so beendet" >&2
  exit 1
fi

mkdir -p "$DFCOM_LIBDIR"
install -m 644 "$SO" "$DFCOM_LIBDIR/libDFCom.so"
printf '%s\n' "$DFCOM_VERSION" >"$DFCOM_LIBDIR/dfcom-sdk-version.txt"
if id zeiterfassung >/dev/null 2>&1 && id deploy >/dev/null 2>&1; then
  chown -R deploy:zeiterfassung "$DFCOM_LIBDIR" || true
fi

echo "Fertig: $DFCOM_LIBDIR/libDFCom.so"
echo "HTTP-Stempeln braucht diese Datei nicht. Polling: Einstellungen → Datafox-Polling, plus TCP zum Gerät (Port 8000)."
echo "Lizenz: Dateien von Datafox GmbH, eigene Bedingungen, nicht Teil der AGPL von Opentakt Zeit."
