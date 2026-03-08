"""FFmpeg validation, audio probing, filtergraph construction, and execution."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import ffmpeg

from core.parser import calculate_iterations
from core.ui import AudioInfo, console, print_error, print_warning

# Global handle for the running FFmpeg process (for signal cleanup).
_ffmpeg_process: subprocess.Popen | None = None

MINIMUM_FFMPEG_VERSION = (6, 1)
TEMP_DIR = Path(tempfile.gettempdir()) / "stretto"


# ── FFmpeg validation ───────────────────────────────────────────────────


def check_ffmpeg() -> str:
    """Verify FFmpeg is installed and meets the minimum version requirement.

    Returns:
        The version string (e.g. "6.1.1").

    Raises:
        SystemExit: If FFmpeg is not found or too old.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        print_error(
            "FFmpeg is not installed or not found in PATH. "
            "Install it from https://ffmpeg.org and try again."
        )
        raise SystemExit(1)

    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        print_error(f"Failed to run ffmpeg: {exc}")
        raise SystemExit(1) from exc

    match = re.search(r"ffmpeg version (\d+)\.(\d+)", result.stdout)
    if not match:
        print_error(
            "Could not determine FFmpeg version. "
            "Please ensure FFmpeg >= 6.1 is installed."
        )
        raise SystemExit(1)

    major, minor = int(match.group(1)), int(match.group(2))
    version_str = f"{major}.{minor}"

    if (major, minor) < MINIMUM_FFMPEG_VERSION:
        print_error(
            f"FFmpeg {version_str} is too old. "
            f"Stretto requires FFmpeg >= {MINIMUM_FFMPEG_VERSION[0]}.{MINIMUM_FFMPEG_VERSION[1]}."
        )
        raise SystemExit(1)

    return version_str


# ── Audio probing ───────────────────────────────────────────────────────


def probe_audio(filepath: str) -> AudioInfo:
    """Probe an audio file and return its metadata.

    Raises:
        SystemExit: If the file cannot be probed.
    """
    path = Path(filepath)
    if not path.exists():
        print_error(f"File not found: '{filepath}'")
        raise SystemExit(1)

    try:
        info = ffmpeg.probe(str(path))
    except ffmpeg.Error as exc:
        stderr_output = exc.stderr.decode() if exc.stderr else "unknown error"
        print_error(f"Cannot read '{filepath}': {stderr_output}")
        raise SystemExit(1) from exc

    audio_streams = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not audio_streams:
        print_error(f"No audio stream found in '{filepath}'.")
        raise SystemExit(1)

    stream = audio_streams[0]
    duration_s = float(info["format"].get("duration", 0))

    return AudioInfo(
        path=str(path),
        duration_ms=round(duration_s * 1000),
        codec=stream.get("codec_name", "unknown"),
        sample_rate=int(stream.get("sample_rate", 44100)),
        channels=int(stream.get("channels", 2)),
    )


# ── Signal handling ─────────────────────────────────────────────────────


def _signal_handler(signum: int, frame) -> None:  # noqa: ANN001
    """Handle SIGINT — terminate FFmpeg process and clean up."""
    global _ffmpeg_process
    console.print("\n[yellow]Interrupted — cleaning up…[/yellow]")
    if _ffmpeg_process is not None:
        _ffmpeg_process.terminate()
        try:
            _ffmpeg_process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            _ffmpeg_process.kill()
        _ffmpeg_process = None
    _cleanup_temp()
    raise SystemExit(130)


def _install_signal_handler() -> None:
    signal.signal(signal.SIGINT, _signal_handler)


def _cleanup_temp() -> None:
    """Remove the temporary directory if it exists."""
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR, ignore_errors=True)


# ── Filtergraph construction & execution ────────────────────────────────


def build_and_run(
    file1_info: AudioInfo,
    file2_info: AudioInfo,
    delay_ms: int,
    blend_ms: int,
    fade_in_ms: int,
    fade_out_ms: int,
    output_filename: str,
    output_format: str,
    optimize: bool,
    needs_loop: bool,
    iterations: int,
    verbose: bool,
) -> None:
    """Build the FFmpeg filtergraph and execute it.

    This constructs the full pipeline:
      1. Loop primary audio with crossfade if needed
      2. Delay secondary audio
      3. Mix both streams
      4. Apply loudness normalization
      5. Apply fade-in / fade-out
      6. Encode to the target format
    """
    global _ffmpeg_process
    _install_signal_handler()
    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    try:
        target_duration_s = (file2_info.duration_ms + delay_ms) / 1000.0

        # ── Step 1: Prepare primary audio (loop if needed) ──────────
        if needs_loop and iterations > 1:
            looped_path = _build_looped_audio(
                file1_info, iterations, blend_ms, target_duration_s, verbose
            )
            primary_input = ffmpeg.input(looped_path)
        else:
            primary_input = ffmpeg.input(file1_info.path)
            if file1_info.duration_ms > round(target_duration_s * 1000):
                primary_input = primary_input.filter(
                    "atrim", duration=target_duration_s
                )

        # ── Step 2: Delay secondary audio ───────────────────────────
        secondary_input = ffmpeg.input(file2_info.path)
        if delay_ms > 0:
            # Use "delays" keyword; values are per-channel in ms.
            # Pad with silence so the stream length is preserved.
            delay_val = "|".join([str(delay_ms)] * file2_info.channels)
            secondary_input = secondary_input.filter(
                "adelay", delays=delay_val,
            )

        # ── Step 3: Mix ─────────────────────────────────────────────
        mixed = ffmpeg.filter(
            [primary_input, secondary_input],
            "amix",
            inputs=2,
            duration="longest",
            dropout_transition=0,
        )

        # ── Step 4: Trim to target duration ─────────────────────────
        mixed = mixed.filter("atrim", duration=target_duration_s)

        # ── Step 5: Loudness normalization ──────────────────────────
        mixed = mixed.filter(
            "dynaudnorm",
            framelen=500,
            gausssize=31,
            peak=0.95,
        )

        # ── Step 6: Fade-in / fade-out ──────────────────────────────
        if fade_in_ms > 0:
            mixed = mixed.filter(
                "afade", type="in", duration=fade_in_ms / 1000.0
            )
        if fade_out_ms > 0:
            mixed = mixed.filter(
                "afade",
                type="out",
                start_time=target_duration_s - (fade_out_ms / 1000.0),
                duration=fade_out_ms / 1000.0,
            )

        # ── Step 7: Output encoding ────────────────────────────────
        output_kwargs: dict = {"y": None}  # overwrite output
        if output_format.lower() == "mp3":
            if optimize:
                output_kwargs["q:a"] = 4  # LAME VBR ~165 kbps
            else:
                output_kwargs["b:a"] = "320k"
        elif output_format.lower() == "wav":
            pass  # PCM defaults are fine
        else:
            if optimize:
                output_kwargs["q:a"] = 4

        output = ffmpeg.output(mixed, output_filename, **output_kwargs)

        # ── Execute ─────────────────────────────────────────────────
        cmd = output.compile()
        if verbose:
            console.print(
                f"\n[dim]FFmpeg command:[/dim]\n{' '.join(cmd)}\n"
            )

        from rich.progress import (
            BarColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeElapsedColumn,
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Processing audio…", total=100)

            _ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            stderr_data = b""
            while True:
                chunk = _ffmpeg_process.stderr.read(1024)
                if not chunk:
                    break
                stderr_data += chunk

                # Parse progress from FFmpeg stderr
                text = chunk.decode("utf-8", errors="replace")
                time_match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", text)
                if time_match:
                    h, m, s = (
                        int(time_match.group(1)),
                        int(time_match.group(2)),
                        float(time_match.group(3)),
                    )
                    current_s = h * 3600 + m * 60 + s
                    pct = min(100, (current_s / target_duration_s) * 100)
                    progress.update(task, completed=pct)

            _ffmpeg_process.wait()
            progress.update(task, completed=100)

        if _ffmpeg_process.returncode != 0:
            stderr_text = stderr_data.decode("utf-8", errors="replace")
            print_error(f"FFmpeg failed (exit code {_ffmpeg_process.returncode}):\n{stderr_text[-500:]}")
            raise SystemExit(1)

        _ffmpeg_process = None

        # Verify output
        if not Path(output_filename).exists():
            print_error(f"Output file was not created: '{output_filename}'")
            raise SystemExit(1)

        size_kb = Path(output_filename).stat().st_size / 1024
        from core.ui import print_success

        print_success(f"Output saved to [bold]{output_filename}[/bold] ({size_kb:.1f} KB)")

    finally:
        _cleanup_temp()


def _build_looped_audio(
    file1_info: AudioInfo,
    iterations: int,
    blend_ms: int,
    target_duration_s: float,
    verbose: bool,
) -> str:
    """Build a looped version of the primary audio using chained crossfades.

    For large iteration counts, this uses a staged approach to avoid
    hitting FFmpeg filtergraph complexity limits.

    Returns:
        Path to the looped temporary file.
    """
    global _ffmpeg_process
    looped_path = str(TEMP_DIR / "looped.wav")
    blend_s = blend_ms / 1000.0

    if iterations > 100:
        print_warning(
            f"Looping {iterations} times — this may take a while. "
            "Consider using a longer source file."
        )

    # Build a filtergraph with N inputs and N-1 acrossfade filters.
    inputs = [ffmpeg.input(file1_info.path) for _ in range(iterations)]

    if blend_ms == 0:
        # No crossfade — simple concatenation.
        joined = ffmpeg.concat(*inputs, v=0, a=1)
    else:
        # Chain acrossfade: [0][1] -> xf01, [xf01][2] -> xf02, …
        current = inputs[0]
        for i in range(1, iterations):
            current = ffmpeg.filter(
                [current, inputs[i]],
                "acrossfade",
                d=blend_s,
                c1="tri",
                c2="tri",
            )

        joined = current

    # Trim to target duration
    joined = joined.filter("atrim", duration=target_duration_s)

    output = ffmpeg.output(joined, looped_path, y=None)

    cmd = output.compile()
    if verbose:
        console.print(
            f"\n[dim]FFmpeg loop command:[/dim]\n{' '.join(cmd)}\n"
        )

    _ffmpeg_process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    _, stderr_data = _ffmpeg_process.communicate()

    if _ffmpeg_process.returncode != 0:
        stderr_text = stderr_data.decode("utf-8", errors="replace")
        print_error(f"FFmpeg looping failed:\n{stderr_text[-500:]}")
        raise SystemExit(1)

    _ffmpeg_process = None
    return looped_path
