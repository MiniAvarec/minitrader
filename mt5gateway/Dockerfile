# MT5 gateway sidecar — Exness has no REST API, so this container runs the
# MetaTrader 5 terminal under Wine plus the mt5linux RPyC server, and the
# backend's ExnessBroker drives it (operationally identical to the IBKR
# `ibgateway` sidecar).
#
# Based on tobix/pywine: a maintained image with Wine + a Windows Python
# already installed and the Wine prefix initialized. Building Wine from apt
# ourselves failed at `wineboot` under BuildKit (kernel32 c0000135); using a
# prebuilt Wine base avoids that entire class of problem.
#
#   WINEPREFIX=/wine  ·  Windows Python at C:\Python3xx (/wine/drive_c/Python3xx)
# Python 3.11 (not 3.12): numpy must be <1.25 to avoid pywine-Wine's missing
# C99 complex ucrt funcs (crealf) — and numpy 1.24.x has no cp312 wheel, so
# we need a cp311 Windows Python.
FROM tobix/pywine:3.11

ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:99 \
    WINEDEBUG=-all

# Linux-side deps: Xvfb (the MT5 terminal needs a display even headless),
# plus a Linux python3 to run the mt5linux *server launcher* (which in turn
# spawns the Wine python).
RUN apt-get update && apt-get install -y --no-install-recommends \
        xvfb xauth wget ca-certificates python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Windows-side: MetaTrader5 + mt5linux into the Wine python. tobix/pywine
# exposes the Windows interpreter via its entrypoint wrapper (not applied to
# build RUN steps), so call it explicitly as `wine python` under Xvfb.
# numpy pinned <1.25: newer numpy calls C99 complex ucrt funcs (crealf) that
# pywine's Wine build doesn't implement, which aborts MetaTrader5 on import.
RUN xvfb-run -a wine python -m pip install --upgrade pip \
    && xvfb-run -a wine python -m pip install "MetaTrader5>=5.0.45" "mt5linux>=0.1.9" "rpyc==5.2.3" "numpy==1.24.4"

# Linux-side mt5linux launcher only. --no-deps so it doesn't try to pull the
# Windows-only MetaTrader5 wheel onto Linux.
RUN pip3 install --break-system-packages --no-cache-dir "rpyc==5.2.3" \
    && pip3 install --break-system-packages --no-cache-dir --no-deps "mt5linux>=0.1.9"

WORKDIR /opt/mt5

# Best-effort silent install of the Exness MT5 terminal. Non-fatal: if the
# installer URL changes the gateway still builds and the failure surfaces
# clearly at connect time (see README "Exness / MT5 setup").
COPY install_mt5.sh /opt/mt5/install_mt5.sh
RUN chmod +x /opt/mt5/install_mt5.sh && (xvfb-run -a /opt/mt5/install_mt5.sh || echo "!! MT5 terminal install non-fatal failure; see logs")

COPY entrypoint.sh /opt/mt5/entrypoint.sh
RUN chmod +x /opt/mt5/entrypoint.sh

EXPOSE 18812
ENTRYPOINT ["/opt/mt5/entrypoint.sh"]
