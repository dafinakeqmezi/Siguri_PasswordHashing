"""Child process that verifies one password and reports its peak working set.

The parent starts this module, waits for the ready event, then sends "go".
Peak working set is read after verification returns, so a short hash cannot
be missed between samples.
"""

import json
import sys

import psutil

from password_benchmark.hashers import make_hasher


def _peak_bytes(info) -> int:
    for name in ("peak_wset", "peak_rss"):
        value = getattr(info, name, None)
        if value:
            return int(value)
    return int(info.rss)


def main() -> int:
    try:
        job = json.loads(sys.stdin.readline())
        hasher = make_hasher(job["algorithm"], job["params"])
        before = psutil.Process().memory_full_info()
        print(json.dumps({"event": "ready", "rss": int(before.rss)}), flush=True)
        sys.stdin.readline()
        ok = bool(hasher.verify(job["password"], job["encoded"]))
        after = psutil.Process().memory_full_info()
        peak_before = _peak_bytes(before)
        peak_after = _peak_bytes(after)
        print(
            json.dumps(
                {
                    "baseline_rss": int(before.rss),
                    "delta_rss": max(0, peak_after - peak_before),
                    "event": "done",
                    "ok": ok,
                    "peak_rss": peak_after,
                }
            ),
            flush=True,
        )
        return 0
    except Exception as exc:
        print(
            json.dumps({"event": "done", "ok": False, "error": f"{type(exc).__name__}: {exc}"}),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
