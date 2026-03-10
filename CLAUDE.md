# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Stretto is a Python CLI tool that combines two audio files into one. The primary audio plays first, the secondary audio starts after a configurable delay on top of it. If the primary audio is too short, it loops with crossfade blending. The output is normalized to prevent clipping and optimized for web.

**GitHub:** git@github.com:theagitist/stretto.git

## Stack

- **Python** — base language
- **Typer** — CLI framework (type-hint-driven argument parsing)
- **Rich** — terminal UI (progress bars, tables, panels, prompts)
- **ffmpeg-python** — FFmpeg wrapper for building filtergraphs
- **pytest** — test framework
- Requires FFmpeg >= 6.1.x on the system

## Project Structure

```
stretto/
├── pyproject.toml       # Dependencies & build config
├── VERSION              # Semantic version (e.g., 1.0.0)
├── main.py              # CLI entry point (Typer app)
├── core/
│   ├── parser.py        # Time suffix parsing & validation
│   ├── processor.py     # FFmpeg filtergraph construction & execution
│   └── ui.py            # Rich progress bars, tables, prompts
└── tests/               # Unit tests (focus on parser and iteration math)
```

## Build & Development Commands

```bash
# Install dependencies
pip install -e .

# Run the CLI
python main.py <FILE1> <FILE2> [OPTIONS]

# Run all tests
pytest

# Run a single test
pytest tests/test_parser.py::test_function_name -v

# Run tests matching a keyword
pytest -k "parse_time" -v
```

## Architecture

### Time Parsing (`core/parser.py`)
Custom Typer callback that converts flexible time strings to integer milliseconds:
- Pure integers → milliseconds (e.g., `2000` → 2000)
- `ms` suffix → milliseconds (e.g., `1500ms` → 1500)
- `s` suffix → seconds × 1000 (e.g., `2s` → 2000, `1.5s` → 1500)
- Regex: `r"^(\d+\.?\d*)(ms|s)?$"`
- Negative values raise `typer.BadParameter`

### Looping & Crossfade (`core/processor.py`)
When primary audio is shorter than secondary + delay:
- **Iteration formula:** `N = ceil((D_target - blend) / (D1 - blend))`
- **Zero blend:** `N = ceil(D_target / D1)`
- **Guard:** `blend < D1` (else error — denominator would be zero)
- Crossfade chain has N-1 crossfades (last iteration has no trailing crossfade)
- Final output trimmed to exactly `D2 + delay`
- If N > 100, warn about processing time

### Audio Processing Pipeline
1. Validate inputs (files exist, FFmpeg available and >= 6.1.x)
2. Probe audio metadata (durations)
3. Calculate if looping is needed; if so, compute N and confirm with user
4. Build FFmpeg filtergraph: loop → crossfade → mix → loudnorm/dynaudnorm → encode
5. Apply fade-in/fade-out if requested
6. Encode: VBR LAME `-V 4`/`-V 5` (optimized) or `-b:a 320k` (no-optimize)

### Signal Handling
- Store FFmpeg `Popen` object globally or in context manager
- On SIGINT: call `process.terminate()`, then `process.kill()` after 1s timeout
- Clean up temp files in `/tmp/stretto/` via `finally` block

## CLI Parameters

| Flag | Short | Default | Description |
|------|-------|---------|-------------|
| `--fade-in` | `-i` | `0` | Fade-in duration |
| `--fade-out` | `-u` | `0` | Fade-out duration |
| `--delay` | `-d` | `2s` | Delay before FILE2 starts |
| `--format` | `-f` | `mp3` | Output format |
| `--loop-blend` | `-b` | `500ms` | Crossfade duration for loops |
| `--optimize/--no-optimize` | `-p` | `true` | Optimize for web size |
| `--bg-level` | `-g` | `-35` | Target loudness for background (LUFS) |
| `--voice-level` | `-l` | `-16` | Target loudness for voiceover (LUFS) |
| `--output` | `-x` | `[file1]_combined` | Output filename |
| `--yes-to-all` | `-y` | — | Skip prompts (headless mode) |
| `--dry-run` | `-n` | — | Show plan without processing |
| `--verbose` | `-v` | — | Print raw FFmpeg command |

All time parameters accept suffixes: `2s`, `1500ms`, `1500`, `1.5s`.

## Key Conventions

- Use `ffmpeg-python` filter chains (`.filter()`) — never manually concatenate filtergraph strings
- Error messages must specify exactly which file or value failed (no "blind debugging")
- `--yes-to-all` skips prompts but still prints plan info to stdout for log auditing
- Use `rich.prompt.Confirm` for user confirmations
- Platforms: macOS and Linux
