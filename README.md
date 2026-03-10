# Stretto

A CLI tool that combines two audio files into a single output. The primary audio plays first, the secondary audio starts after a configurable delay on top of it. If the primary audio is too short, it loops with smooth crossfade blending. The output is normalized to prevent clipping and optimized for web.

## Requirements

- **Python** >= 3.10
- **FFmpeg** >= 6.1 (must be available in PATH)

## Installation

```bash
# From source
git clone git@github.com:theagitist/stretto.git
cd stretto
pip install -e .

# With dev dependencies (for running tests)
pip install -e ".[dev]"
```

## Usage

You can run Stretto in two ways:

```bash
# If installed via pip (available system-wide)
stretto background.mp3 voiceover.mp3

# Or directly from the project directory
./stretto background.mp3 voiceover.mp3
```

### Examples

```bash
# Basic usage — combine two audio files with default settings
stretto background.mp3 voiceover.mp3

# Custom delay before second audio starts
stretto background.wav narration.mp3 -d 5s

# Add fade-in and fade-out
stretto bg.mp3 voice.mp3 -i 1s -u 2s

# Output as WAV, no size optimization
stretto bg.mp3 voice.mp3 -f wav --no-optimize

# Custom output filename
stretto bg.mp3 voice.mp3 -x final_output.mp3

# Preview the plan without processing
stretto bg.mp3 voice.mp3 --dry-run

# Headless mode (no prompts, for automation)
stretto bg.mp3 voice.mp3 -y

# Adjust volume levels (background quieter, voice louder)
stretto bg.mp3 voice.mp3 --bg-level -40 --voice-level -14

# See the raw FFmpeg command
stretto bg.mp3 voice.mp3 --verbose
```

## Options

```
Usage: stretto [OPTIONS] <FILE1> <FILE2>

Arguments:
  <FILE1>  Path to the primary audio file (loops if too short)
  <FILE2>  Path to the secondary audio file (starts after delay)

Options:
  -i, --fade-in <MS>           Fade-in duration [default: 0]
  -u, --fade-out <MS>          Fade-out duration [default: 0]
  -d, --delay <MS>             Delay before FILE2 starts [default: 2s]
  -f, --format <STR>           Output format [default: mp3]
  -b, --loop-blend <MS>        Crossfade duration for loops [default: 500ms]
  -p, --optimize / -P, --no-optimize
                               Optimize for web [default: optimize]
  -x, --output <PATH>          Output filename [default: <file1>_combined.<format>]
  -g, --bg-level <LUFS>        Target loudness for background audio [default: -35]
  -l, --voice-level <LUFS>     Target loudness for voiceover audio [default: -16]
  -y, --yes-to-all             Skip confirmation prompts
  -n, --dry-run                Show execution plan without processing
  -v, --verbose                Print raw FFmpeg commands
  -h, --help                   Show this help message
```

### Time format

All time parameters (`--delay`, `--fade-in`, `--fade-out`, `--loop-blend`) accept flexible formats:

| Input    | Result     |
|----------|------------|
| `2000`   | 2000 ms    |
| `1500ms` | 1500 ms    |
| `2s`     | 2000 ms    |
| `1.5s`   | 1500 ms    |

## How it works

1. **Probes** both audio files for duration, codec, and metadata.
2. **Calculates** whether the primary audio needs looping to cover the secondary audio + delay.
3. If looping is needed, **chains crossfade** filters to create smooth loop transitions (configurable blend duration).
4. **Analyzes loudness** (EBU R128) and adjusts volume levels so the voiceover is clear above the background.
5. **Mixes** the primary and delayed secondary audio.
6. Applies **loudness normalization** (`loudnorm`) to prevent clipping.
7. Applies optional **fade-in** and **fade-out**.
8. **Encodes** the output (LAME VBR for optimized MP3, or high bitrate when not optimized).

## Running tests

```bash
pytest
pytest tests/test_parser.py -v
pytest -k "test_function_name" -v
```

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
