"""VIC lookup worker — runs undetected_chromedriver in its own process group.

Run as a subprocess by providers._run_uc. A hard SIGALRM watchdog plus the
parent's process-group kill guarantee Chrome/chromedriver are reaped even when
the CDP session hangs (which otherwise accumulates zombies and makes later
lookups flaky on the Docker host).
"""

import json
import os
import signal
import sys
import threading
import time

from undetected import uc_lookup  # noqa: E402  (sets up imports after cwd)
from providers import NotFound, UpstreamBlocked, UpstreamError  # noqa: E402

WATCHDOG_SECONDS = 40


def _nuke(signum, frame):
    os.killpg(0, signal.SIGKILL)


def _watchdog_thread():
    time.sleep(WATCHDOG_SECONDS + 5)
    os.killpg(0, signal.SIGKILL)


def main():
    plate, state = sys.argv[1], sys.argv[2]
    vehicle_type = sys.argv[3] if len(sys.argv) > 3 else "car"
    signal.signal(signal.SIGALRM, _nuke)
    signal.alarm(WATCHDOG_SECONDS)
    # SIGALRM only runs when Python regains control; a thread kill covers the
    # process stuck in a native CDP call (hung chrome).
    threading.Thread(target=_watchdog_thread, daemon=True).start()
    try:
        result = uc_lookup(plate, state, vehicle_type)
        print(json.dumps({"ok": True, "result": result}))
    except NotFound:
        print(json.dumps({"ok": False, "kind": "notfound"}))
    except UpstreamBlocked as e:
        print(json.dumps({"ok": False, "kind": "blocked", "message": str(e)}))
    except UpstreamError as e:
        print(json.dumps({"ok": False, "kind": "error", "message": str(e)}))
    except Exception as e:
        print(json.dumps({"ok": False, "kind": "error", "message": f"{type(e).__name__}: {e}"}))
    finally:
        signal.alarm(0)


main()
