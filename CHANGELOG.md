# Changelog

## Unreleased

### Changed
- Machine-specific settings moved to an optional `~/.config/laptop-doctor/config.json`
  (`config.example.json`): the notes folder for `laptop snapshot`, the backup unit, an editor or
  assistant plugin cache, extra review folders and extra toolchain versions. Nothing is assumed
  when a key is missing.
- The daily service runs `laptop` from `~/.local/bin`, where the installer links it.
- Released under the MIT license with the author's full name; CI runs the tests.

## v2.0.0 - 2026-11-01

First tagged release. The version number follows `pyproject.toml`, which counts the desktop app
rebuild as version 2.

### Added
- Tests for the checks fed with canned command output: disk thresholds, failed and stale units,
  journal error counts, backups, open ports including IPv6 wildcards, pending updates,
  temperature, battery health and unit formatting.
- MIT license, a Tests section and a "What it does not do" section in the README.

### Fixed
- `uv run pytest` now finds the `laptop_doctor` package; before, only `python -m pytest` worked.

## Before v2.0.0

- 2026-10-26: the GUI no longer crashes when a background task finishes; OOM kills and boots are
  read from the kernel log; memory is grouped by application; checks run in parallel.
- 2026-10-19: kernel logs are read across all boots, and the GPU check survives a wedged driver.
- 2026-09-30: rebuilt as a desktop app with a tray icon, dashboard, monitor and optimizer.
- 2026-09-30: first version: the `laptop` command (check, crashes, clean, updates, report) and the
  daily timer.
