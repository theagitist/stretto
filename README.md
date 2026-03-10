# Stretto

A CLI tool that combines two audio files into a single output. The primary audio (background) plays first, the secondary audio (voiceover) starts after a configurable delay on top of it. If the primary audio is too short, it loops with smooth crossfade blending. The output is normalized to prevent clipping and optimized for web.

Supports **batch processing** — pass a directory of numbered file pairs to combine them all at once.

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

### Two-file mode

```bash
stretto background.mp3 voiceover.mp3
```

### Directory mode (batch)

Place numbered file pairs in a directory using the naming pattern:

```
<NUMBER><sep><1|2><sep><rest>.ext
```

Where `<sep>` is a space, hyphen, or underscore. The number `1` marks the background audio, `2` marks the voiceover. Examples:

```
audio/
├── 01 1 rain.mp3          # pair 1, background
├── 01 2 intro.mp3         # pair 1, voiceover
├── 02_1_wind.mp3          # pair 2, background
├── 02_2_chapter-one.mp3   # pair 2, voiceover
├── 003-1-ocean.mp3        # pair 3, background
└── 003-2-outro.mp3        # pair 3, voiceover
```

Then run:

```bash
stretto audio/
```

All pairs are processed in order. Output files are saved into the same directory, auto-named from the background file (e.g. `audio/01 1 rain_combined.mp3`).

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

# Batch process a directory of numbered pairs
stretto ./my-audio-pairs/

# Batch process with custom settings
stretto ./my-audio-pairs/ -d 3s --bg-level -40 -y

# See the raw FFmpeg command
stretto bg.mp3 voice.mp3 --verbose
```

## Options

```
Usage: stretto [OPTIONS] <FILE1|DIR> [FILE2]

Arguments:
  <FILE1|DIR>  Path to primary audio file, or directory of numbered pairs
  [FILE2]      Path to secondary audio file (omit in directory mode)

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
  -V, --version                Show version and exit
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
