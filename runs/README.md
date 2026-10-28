# Saved experimental runs

| Run | Machine | Summary |
| --- | --- | --- |
| `windows-2026-10-25` | Windows 11, AMD Ryzen 7 PRO 6850U, Python 3.12.10 | [Windows results](windows-2026-10-25/results/summary.md) |
| `macos-2026-10-27` | macOS 15.2, Apple M4 Pro, Python 3.13.5 | [Mac results](macos-2026-10-27/results/summary.md) |

Each folder contains the original raw data, results, figures, configuration,
dependencies, and benchmark source. `manifest.json` records provenance and
SHA-256 checksums. The Windows files were recovered from commit `e2958ac`.
The Mac outputs were copied from the completed local run. Neither run was
recomputed or regenerated during preservation.

Both experiments used the original benchmark source, before the subsequent
cross-platform memory and environment corrections. The saved Mac environment
therefore still says `arm`; Apple M4 Pro was identified separately afterwards.
The Windows configuration hash reflects CRLF line endings on its measurement
machine; Git stores the same configuration with LF endings.

The root `data/raw` and `results` folders remain the Mac working results.
Root source files contain the newer compatibility changes. Changes to the root
files do not update these snapshots. Use a new name for every future saved run:

```text
python -m password_benchmark save-run MACHINE-PERSON-DATE
```

Both saved runs predate three harness corrections made on 2026-10-28: pool
workers now start before the batch clock, concurrent memory is measured in a
fresh process, and Linux memory uses `VmHWM`. Use a new run collected with
`python -m password_benchmark final` for the report tables, and cite these two
runs only as earlier, superseded measurements. Their process-pool breakdown can
be reproduced with `analyze` on a copy of their `data/raw` folder.

Keep each machine's measurements separate. Select one complete run for the
proposal's main controlled-machine comparison; additional runs can be presented
as supplementary results. These machines differ in hardware and software, so
their performance difference cannot be attributed to the operating system alone.
