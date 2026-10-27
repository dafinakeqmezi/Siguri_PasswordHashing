"""Child process that verifies one password and reports its peak working set.

The parent starts this module, waits for the ready event, then sends "go".
Peak working set is read after verification returns, so a short hash cannot
be missed between samples.
"""

import json
import platform
import sys

import psutil

from password_benchmark.hashers import make_hasher


def _peak_bytes() -> int:
    if platform.system() == "Windows":
        return int(psutil.Process().memory_info().peak_wset)
    # resource is unavailable on Windows. Darwin reports bytes; other Unix
    # platforms report KiB. This records the high-water mark, even after free().
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if platform.system() == "Darwin" else peak * 1024)


def main() -> int:
    try:
        job = json.loads(sys.stdin.readline())
        hasher = make_hasher(job["algorithm"], job["params"])
        baseline_rss = psutil.Process().memory_info().rss
        peak_before = _peak_bytes()
        print(json.dumps({"event": "ready", "rss": int(baseline_rss)}), flush=True)
        sys.stdin.readline()
        ok = bool(hasher.verify(job["password"], job["encoded"]))
        peak_after = _peak_bytes()
        print(
            json.dumps(
                {
                    "baseline_rss": int(baseline_rss),
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
