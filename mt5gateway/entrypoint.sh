#!/usr/bin/env bash
# Runtime: headless display + the mt5linux RPyC server. The server runs
# *inside the Wine python* (that's where MetaTrader5 lives) and exposes it
# over rpyc on :18812. The backend's ExnessBroker is the rpyc client.
# EXNESS_* (if set) seed a default logged-in session so the credential-less
# public path (instruments_refresh) also works.
set -uo pipefail

export WINEPREFIX=${WINEPREFIX:-/opt/wineprefix}
export WINEDEBUG=-all
export DISPLAY=:99
BRIDGE_PORT="${MT5_BRIDGE_PORT:-18812}"

# Wine Python (tobix/pywine installs to C:\Python), excluding the venv copy.
WINPY="${WINEPREFIX}/drive_c/Python/python.exe"
if [[ ! -f "${WINPY}" ]]; then
    WINPY=$(find "${WINEPREFIX}/drive_c" -maxdepth 3 -iname python.exe 2>/dev/null \
            | grep -vi venv | head -1)
fi
if [[ -z "${WINPY}" || ! -f "${WINPY}" ]]; then
    echo "!! Wine python not found under ${WINEPREFIX}/drive_c — image build issue" >&2
    exit 1
fi
TERMINAL=$(find "${WINEPREFIX}/drive_c" -iname terminal64.exe 2>/dev/null | head -1 || true)

# Stale X lock files are baked in from build-time xvfb-run; clear them so our
# Xvfb can own :99.
rm -f /tmp/.X*-lock 2>/dev/null || true
rm -f /tmp/.X11-unix/X99 2>/dev/null || true

echo ">> starting Xvfb :99"
Xvfb :99 -screen 0 1280x1024x24 -nolisten tcp &
sleep 3

if [[ -z "${TERMINAL}" ]]; then
    echo ">> terminal64.exe missing; retrying Exness MT5 install at runtime"
    /opt/mt5/install_mt5.sh || echo "!! runtime MT5 install also failed"
    TERMINAL=$(find "${WINEPREFIX}/drive_c" -iname terminal64.exe 2>/dev/null | head -1 || true)
fi
echo ">> winpy=${WINPY}"
echo ">> terminal=${TERMINAL:-NOT FOUND}"

# Seed a default MT5 session for the credential-less public path.
if [[ -n "${EXNESS_LOGIN:-}" && -n "${EXNESS_PASSWORD:-}" && -n "${EXNESS_SERVER:-}" ]]; then
    echo ">> seeding default session ${EXNESS_SERVER} (login ${EXNESS_LOGIN})"
    cat > /tmp/seed.py <<EOF
import MetaTrader5 as mt5
kw = {"login": int("${EXNESS_LOGIN}"), "password": "${EXNESS_PASSWORD}", "server": "${EXNESS_SERVER}"}
term = r"${TERMINAL}"
ok = mt5.initialize(term, **kw) if term else mt5.initialize(**kw)
print("seed initialize:", ok, "last_error:", mt5.last_error())
ai = mt5.account_info()
print("account:", None if ai is None else (ai.login, ai.server, ai.currency, ai.balance, ai.equity))
EOF
    wine "${WINPY}" /tmp/seed.py 2>&1 || echo "!! seed login failed (per-user keys can still log in)"
fi

echo ">> starting mt5linux RPyC server on 0.0.0.0:${BRIDGE_PORT} (under wine python)"
exec wine "${WINPY}" -m mt5linux --host 0.0.0.0 --port "${BRIDGE_PORT}"
