# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## How to run
```bash
python pomodoro.py
```

## Architecture

Single-file Tkinter desktop app — no build system, no package manager, no tests.

**`PomodoroApp`** is the sole class. It manages three timer modes (pomodoro / short_break / long_break), a circular canvas progress ring, and a per-day session log.

**State files** (auto-created alongside `pomodoro.py`):
- `pomodoro_settings.json` — user-configured durations (in seconds) + completed pomodoro count
- `pomodoro_log.json` — per-day log entries keyed by `"YYYY-MM-DD"`

**Settings dialog** allows adjusting duration for each mode (1–120 minutes), validated on save.

## Platform dependency

`winsound.Beep` is used for completion alerts — Windows only. Porting to other platforms requires replacing this call.
