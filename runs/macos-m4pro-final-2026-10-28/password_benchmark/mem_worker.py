"""Child process that verifies passwords and reports its peak working set.

The parent starts this module, waits for the ready event, then sends "go".
Peak working set is read after verification returns, so a short hash cannot
be missed between samples.

A job with "tasks" runs one verification per task at the same time, each on
its own thread. The threads are started before the first peak reading and
wait on a barrier, so their creation is not counted in the delta.
"""

import json
import platform
import sys
import threading

import psutil

from password_benchmark.hashers import make_hasher


def _linux_vmhwm(status_path: str = "/proc/self/status") -> int:
    with open(status_path, encoding="ascii") as handle:
        for line in handle:
            if line.startswith("VmHWM:"):
                return int(line.split()[1]) * 1024
    raise RuntimeError("VmHWM is missing from /proc/self/status")


def _peak_bytes() -> int:
    system = platform.system()
    if system == "Windows":
        return int(psutil.Process().memory_info().peak_wset)
    if system == "Linux":
        # Linux keeps ru_maxrss across fork and exec, so a fresh child starts
        # with the parent's high-water mark. VmHWM belongs to the new image only.
        return _linux_vmhwm()
    # resource is unavailable on Windows. Darwin reports bytes; other Unix
    # platforms report KiB. This records the high-water mark, even after free().
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if system == "Darwin" else peak * 1024)


def _start_concurrent(hasher, tasks: list[dict]):
    barrier = threading.Barrier(len(tasks) + 1)
    outcomes = [False] * len(tasks)

    def run(index: int, task: dict) -> None:
        barrier.wait()
        outcomes[index] = bool(hasher.verify(task["password"], task["encoded"]))

    threads = [threading.Thread(target=run, args=(index, task), daemon=True) for index, task in enumerate(tasks)]
    for thread in threads:
        thread.start()

    def release() -> bool:
        barrier.wait()
        for thread in threads:
            thread.join()
        return all(outcomes)

    return release


def main() -> int:
    try:
        job = json.loads(sys.stdin.readline())
        hasher = make_hasher(job["algorithm"], job["params"])
        tasks = job.get("tasks")
        release = _start_concurrent(hasher, tasks) if tasks else None
        baseline_rss = psutil.Process().memory_info().rss
        peak_before = _peak_bytes()
        print(json.dumps({"event": "ready", "rss": int(baseline_rss)}), flush=True)
        sys.stdin.readline()
        if release is not None:
            ok = release()
        else:
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
