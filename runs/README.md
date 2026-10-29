# Saved experimental runs

| Run | Machine | Status | Summary |
| --- | --- | --- | --- |
| `macos-m4pro-final-2026-10-28` | macOS 15.2, Apple M4 Pro, Python 3.13.5 | Final; main controlled-machine result | [Mac final](macos-m4pro-final-2026-10-28/results/summary.md), [supplementary](macos-m4pro-final-2026-10-28/results/supplementary/summary.md) |
| `windows-ryzen-final-2026-10-28` | Windows 11, AMD Ryzen 7 PRO 6850U, Python 3.12.10 | Final; replication on a second machine | [Windows final](windows-ryzen-final-2026-10-28/results/summary.md), [supplementary](windows-ryzen-final-2026-10-28/results/supplementary/summary.md) |
| `mac-before-final-2026-10-28` | macOS 15.2, Apple M4 Pro, Python 3.13.5 | Registered experiment only, corrected harness | [Mac registered run](mac-before-final-2026-10-28/results/summary.md) |
| `macos-2026-10-27` | macOS 15.2, Apple M4 Pro, Python 3.13.5 | Superseded | [Mac results](macos-2026-10-27/results/summary.md) |
| `windows-2026-10-25` | Windows 11, AMD Ryzen 7 PRO 6850U, Python 3.12.10 | Superseded | [Windows results](windows-2026-10-25/results/summary.md) |

Each folder contains the original raw data, results, figures, configuration,
dependencies, and benchmark source. `manifest.json` records provenance and
SHA-256 checksums. No run was recomputed or regenerated during preservation.

## Final runs of 2026-10-28

Both final runs were collected with `python -m password_benchmark final`, which
runs the registered experiment and every supplementary experiment. They used
the same source, the same `config/experiment.yaml` (SHA-256 `fed42fd6...`), and
the same `config/supplementary.yaml` (SHA-256 `0e77f628...`). Each machine ran
and analyzed its own run independently; neither saw the other's results first.
Use these two runs for the report tables.

- `macos-m4pro-final-2026-10-28` was saved with `save-run` from the root
  `data/raw` and `results` folders, which hold the Mac final run.
- `windows-ryzen-final-2026-10-28` was recovered byte for byte from commit
  `3d0548f` after the merge replaced the root folders with the Mac run. Its
  manifest says so. The Windows machine used the Balanced power scheme.
- `mac-before-final-2026-10-28` is a registered-only Mac run with the same
  source, saved before the final run started.

The side-by-side comparison is in
[comparisons/macos-m4pro-final-2026-10-28__windows-ryzen-final-2026-10-28](../comparisons/macos-m4pro-final-2026-10-28__windows-ryzen-final-2026-10-28/comparison.md).
It was produced with:

```text
python -m password_benchmark compare macos-m4pro-final-2026-10-28 windows-ryzen-final-2026-10-28
```

## Superseded runs

`windows-2026-10-25` and `macos-2026-10-27` used the original benchmark source,
before the harness corrections of 2026-10-28: pool workers now start before the
batch clock, concurrent memory is measured in a fresh process, and Linux memory
uses `VmHWM`. Cite them only as earlier measurements. Their process-pool
breakdown can be reproduced with `analyze` on a copy of their `data/raw` folder.

The Windows files of that first run were recovered from commit `e2958ac`; the
Mac outputs were copied from the completed local run. The saved Mac environment
says `arm`; Apple M4 Pro was identified separately afterwards. The Windows
configuration hash reflects CRLF line endings on its measurement machine; Git
stores the same configuration with LF endings.

## Saving and comparing future runs

Root source files may change later; that does not update these snapshots. Use a
new name for every saved run:

```text
python -m password_benchmark save-run MACHINE-PERSON-DATE
```

Keep each machine's measurements separate. Select one complete run for the
proposal's main controlled-machine comparison; additional runs can be presented
as supplementary results. These machines differ in hardware and software, so
their performance difference cannot be attributed to the operating system alone.
