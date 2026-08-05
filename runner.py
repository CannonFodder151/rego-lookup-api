import asyncio
import json
import sys

from providers import NotFound, UpstreamBlocked, UpstreamError
from browser import browser_lookup


def main():
    plate, state = sys.argv[1], sys.argv[2]
    first = sys.argv[3] if len(sys.argv) > 3 else None
    last = sys.argv[4] if len(sys.argv) > 4 else None
    print(f"runner start {state}", file=sys.stderr, flush=True)
    try:
        result = asyncio.run(browser_lookup(plate, state, first, last))
        print(json.dumps({"ok": True, "result": result}))
    except NotFound:
        print(json.dumps({"ok": False, "kind": "notfound"}))
    except UpstreamBlocked as e:
        print(json.dumps({"ok": False, "kind": "blocked", "message": str(e)}))
    except UpstreamError as e:
        print(json.dumps({"ok": False, "kind": "error", "message": str(e)}))
    except Exception as e:
        print(json.dumps({"ok": False, "kind": "error", "message": f"{type(e).__name__}: {e}"}))


main()
