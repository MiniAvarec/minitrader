#!/usr/bin/env bash
# Build-time, best-effort: install the Exness MT5 terminal into the (already
# initialized) Wine prefix from the tobix/pywine base. Runs under xvfb-run.
set -uo pipefail

export WINEPREFIX=${WINEPREFIX:-/wine}
export WINEDEBUG=-all

echo ">> downloading Exness MT5 terminal"
# Exness ships a branded MT5 installer. Override MT5_URL (build arg / mirror)
# if this 404s — see README "Exness / MT5 setup".
MT5_URL="${MT5_URL:-https://download.mql5.com/cdn/web/exness.technologies.ltd/mt5/exness5setup.exe}"
if ! wget -q -O /tmp/mt5setup.exe "${MT5_URL}"; then
    echo "!! Exness MT5 download failed (${MT5_URL})" >&2
    exit 1
fi

echo ">> silent-installing MT5 under Wine"
# MT5 setup supports /auto for unattended install.
wine /tmp/mt5setup.exe /auto || true
# Give the installer time to lay down terminal64.exe.
for i in $(seq 1 30); do
    if find "${WINEPREFIX}/drive_c" -iname terminal64.exe 2>/dev/null | grep -q .; then
        echo ">> terminal64.exe present"
        break
    fi
    sleep 3
done
rm -f /tmp/mt5setup.exe
find "${WINEPREFIX}/drive_c" -iname terminal64.exe 2>/dev/null | head -1 || \
    echo "!! terminal64.exe not found after install (will retry at runtime)"
echo ">> install step complete"
