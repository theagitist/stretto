"""Stretto — CLI tool that combines two audio files into one."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.prompt import Prompt

from core.parser import calculate_iterations, parse_time
from core.processor import build_and_run, check_ffmpeg, probe_audio
from core.ui import (
    confirm_loop,
    console,
    display_plan,
    print_error,
    print_warning,
)

app = typer.Typer(
    name="stretto",
    help="Combine two audio files with crossfade looping, normalization, and web optimization.",
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _time_callback(value: str) -> int:
    """Typer callback for time parameters."""
    return parse_time(value)


@app.command()
def main(
    file1: Optional[str] = typer.Argument(  # noqa: UP007
        None,
        help="Path to the primary audio file (loops if too short).",
    ),
    file2: Optional[str] = typer.Argument(  # noqa: UP007
        None,
        help="Path to the secondary audio file (starts after delay).",
    ),
    fade_in: str = typer.Option(
        "0",
        "--fade-in",
        "-i",
        help="Fade-in duration (e.g. 500ms, 2s).",
    ),
    fade_out: str = typer.Option(
        "0",
        "--fade-out",
        "-u",
        help="Fade-out duration (e.g. 500ms, 2s).",
    ),
    delay: str = typer.Option(
        "2s",
        "--delay",
        "-d",
        help="Delay before FILE2 starts (e.g. 2s, 2000ms).",
    ),
    output_format: str = typer.Option(
        "mp3",
        "--format",
        "-f",
        help="Output format (mp3, wav, etc.).",
    ),
    loop_blend: str = typer.Option(
        "500ms",
        "--loop-blend",
        "-b",
        help="Crossfade duration for loops (e.g. 500ms, 0).",
    ),
    optimize: bool = typer.Option(
        True,
        "--optimize/--no-optimize",
        "-p/-P",
        help="Optimize for web (smaller file size).",
    ),
    output_filename: Optional[str] = typer.Option(  # noqa: UP007
        None,
        "--output",
        "-x",
        help="Output filename. Default: [file1]_combined.<format>.",
    ),
    yes_to_all: bool = typer.Option(
        False,
        "--yes-to-all",
        "-y",
        help="Skip confirmation prompts (headless mode).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show execution plan without processing.",
    ),
    bg_level: str = typer.Option(
        "-35",
        "--bg-level",
        "-g",
        help="Target loudness for background audio in LUFS (e.g. -35, -30).",
    ),
    voice_level: str = typer.Option(
        "-16",
        "--voice-level",
        "-l",
        help="Target loudness for voiceover audio in LUFS (e.g. -16, -14).",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Print raw FFmpeg commands.",
    ),
) -> None:
    """Combine two audio files into one with optional looping and crossfade."""

    # ── Prompt for missing file arguments ───────────────────────────
    if file1 is None:
        file1 = Prompt.ask("[bold]Path to primary audio file[/bold]").strip()
        if not file1:
            print_error("No primary audio file provided.")
            raise typer.Exit(code=1)

    if file2 is None:
        file2 = Prompt.ask("[bold]Path to secondary audio file[/bold]").strip()
        if not file2:
            print_error("No secondary audio file provided.")
            raise typer.Exit(code=1)

    # ── Parse time parameters ───────────────────────────────────────
    try:
        fade_in_ms = parse_time(fade_in)
        fade_out_ms = parse_time(fade_out)
        delay_ms = parse_time(delay)
        blend_ms = parse_time(loop_blend)
    except typer.BadParameter as exc:
        print_error(str(exc))
        raise typer.Exit(code=1) from exc

    # ── Parse LUFS levels ──────────────────────────────────────
    try:
        bg_level_lufs = float(bg_level)
        voice_level_lufs = float(voice_level)
    except ValueError:
        print_error("--bg-level and --voice-level must be numeric LUFS values (e.g. -35, -16).")
        raise typer.Exit(code=1)

    # ── Validate output format ──────────────────────────────────────
    supported_formats = {"mp3", "wav", "ogg", "flac", "aac", "m4a", "opus", "wma"}
    if output_format.lower() not in supported_formats:
        print_error(
            f"Unsupported format: '{output_format}'. "
            f"Supported: {', '.join(sorted(supported_formats))}."
        )
        raise typer.Exit(code=1)

    # ── Check FFmpeg ────────────────────────────────────────────────
    ffmpeg_version = check_ffmpeg()
    if verbose:
        console.print(f"[dim]FFmpeg version: {ffmpeg_version}[/dim]")

    # ── Probe audio files ───────────────────────────────────────────
    file1_info = probe_audio(file1)
    file2_info = probe_audio(file2)

    # ── Calculate target duration and looping ───────────────────────
    d_target = file2_info.duration_ms + delay_ms
    needs_loop = file1_info.duration_ms < d_target
    iterations = 1

    if needs_loop:
        try:
            iterations = calculate_iterations(d_target, file1_info.duration_ms, blend_ms)
        except ValueError as exc:
            print_error(str(exc))
            raise typer.Exit(code=1) from exc

        if iterations > 100:
            print_warning(
                f"This requires {iterations} loop iterations. "
                "Processing may be slow — consider a longer source file."
            )

    # ── Determine output filename ───────────────────────────────────
    if output_filename is None:
        stem = Path(file1).stem
        output_filename = f"{stem}_combined.{output_format.lower()}"

    # ── Display plan ────────────────────────────────────────────────
    display_plan(
        file1_info=file1_info,
        file2_info=file2_info,
        delay_ms=delay_ms,
        blend_ms=blend_ms,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
        output_filename=output_filename,
        output_format=output_format,
        optimize=optimize,
        needs_loop=needs_loop,
        iterations=iterations if needs_loop else None,
    )

    # ── Dry run stops here ──────────────────────────────────────────
    if dry_run:
        console.print("\n[dim]Dry run — no files were processed.[/dim]")
        raise typer.Exit(code=0)

    # ── Confirm looping with user ───────────────────────────────────
    if needs_loop and not yes_to_all:
        if not confirm_loop(file1_info.duration_ms, d_target, iterations, blend_ms):
            console.print("[dim]Cancelled.[/dim]")
            raise typer.Exit(code=0)

    # ── Build and run ───────────────────────────────────────────────
    build_and_run(
        file1_info=file1_info,
        file2_info=file2_info,
        delay_ms=delay_ms,
        blend_ms=blend_ms,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
        output_filename=output_filename,
        output_format=output_format,
        optimize=optimize,
        needs_loop=needs_loop,
        iterations=iterations,
        bg_level_lufs=bg_level_lufs,
        voice_level_lufs=voice_level_lufs,
        verbose=verbose,
    )


if __name__ == "__main__":
    app()
