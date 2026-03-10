"""Stretto — CLI tool that combines two audio files into one."""

from __future__ import annotations

import re
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
    print_success,
    print_warning,
)

_VERSION = Path(__file__).parent.joinpath("VERSION").read_text().strip()


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"stretto {_VERSION}")
        raise typer.Exit()


app = typer.Typer(
    name="stretto",
    help="Combine two audio files with crossfade looping, normalization, and web optimization.",
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# Pattern: <number><separator><1 or 2><separator><rest>
# Separator is space, hyphen, or underscore.
# Examples: "02 1 ears.mp3", "1_2_eyes.mp3", "0000003-2-noses.mp3"
_PAIR_RE = re.compile(
    r"^(\d+)[\s_-](1|2)[\s_-](.+)$"
)


def _scan_directory(directory: Path) -> list[tuple[Path, Path]]:
    """Scan a directory for numbered audio pairs.

    Returns a sorted list of (file1, file2) tuples where file1 is the
    background (marker 1) and file2 is the voiceover (marker 2).
    """
    # Group files by their leading number
    groups: dict[str, dict[str, Path]] = {}

    for f in directory.iterdir():
        if not f.is_file():
            continue
        match = _PAIR_RE.match(f.name)
        if not match:
            continue
        group_num = match.group(1).lstrip("0") or "0"  # normalize "002" -> "2"
        track_id = match.group(2)  # "1" or "2"

        if group_num not in groups:
            groups[group_num] = {}

        if track_id in groups[group_num]:
            print_warning(
                f"Duplicate track {track_id} for group {match.group(1)}: "
                f"'{f.name}' conflicts with '{groups[group_num][track_id].name}'. "
                "Skipping duplicate."
            )
            continue

        groups[group_num][track_id] = f

    # Build pairs, only include complete pairs
    pairs: list[tuple[int, Path, Path]] = []
    for group_num, tracks in groups.items():
        if "1" not in tracks or "2" not in tracks:
            missing = "1" if "1" not in tracks else "2"
            present = tracks.get("1") or tracks.get("2")
            print_warning(
                f"Group {group_num}: found '{present.name}' but missing track {missing}. Skipping."
            )
            continue
        pairs.append((int(group_num), tracks["1"], tracks["2"]))

    # Sort by group number
    pairs.sort(key=lambda t: t[0])
    return [(f1, f2) for _, f1, f2 in pairs]


def _process_pair(
    file1: str,
    file2: str,
    fade_in_ms: int,
    fade_out_ms: int,
    delay_ms: int,
    blend_ms: int,
    output_filename: str | None,
    output_dir: str | None,
    output_format: str,
    optimize: bool,
    bg_level_lufs: float,
    voice_level_lufs: float,
    yes_to_all: bool,
    dry_run: bool,
    verbose: bool,
) -> None:
    """Process a single pair of audio files."""
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
        name = f"{stem}_combined.{output_format.lower()}"
        if output_dir is not None:
            output_filename = str(Path(output_dir) / name)
        else:
            output_filename = name

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
        return

    # ── Confirm looping with user ───────────────────────────────────
    if needs_loop and not yes_to_all:
        if not confirm_loop(file1_info.duration_ms, d_target, iterations, blend_ms):
            console.print("[dim]Cancelled.[/dim]")
            return

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


@app.command()
def main(
    file1: Optional[str] = typer.Argument(  # noqa: UP007
        None,
        help="Path to primary audio file, or a directory containing numbered pairs.",
    ),
    file2: Optional[str] = typer.Argument(  # noqa: UP007
        None,
        help="Path to secondary audio file (omit when using directory mode).",
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
    version: Optional[bool] = typer.Option(  # noqa: UP007
        None,
        "--version",
        "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Combine two audio files into one with optional looping and crossfade.

    Pass two files directly, or pass a directory to batch-process numbered pairs.
    In directory mode, files must match: <NUMBER><sep><1|2><sep><rest>.ext
    (e.g. "02 1 ears.mp3", "1_2_eyes.mp3", "0000003-2-noses.mp3").
    """

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

    # ── Prompt for missing file1 ────────────────────────────────────
    if file1 is None:
        file1 = Prompt.ask(
            "[bold]Path to primary audio file or directory[/bold]"
        ).strip()
        if not file1:
            print_error("No path provided.")
            raise typer.Exit(code=1)

    # ── Directory mode ──────────────────────────────────────────────
    file1_path = Path(file1)
    if file1_path.is_dir():
        if file2 is not None:
            print_error("Cannot specify FILE2 when using directory mode.")
            raise typer.Exit(code=1)
        if output_filename is not None:
            print_error("Cannot use --output in directory mode (filenames are auto-generated).")
            raise typer.Exit(code=1)

        pairs = _scan_directory(file1_path)
        if not pairs:
            print_error(
                f"No matching audio pairs found in '{file1}'.\n"
                "Expected filenames like: 01 1 background.mp3, 01 2 voiceover.mp3"
            )
            raise typer.Exit(code=1)

        console.print(
            f"\n[bold]Found {len(pairs)} audio pair(s) in '{file1}':[/bold]"
        )
        for bg, vo in pairs:
            console.print(f"  [dim]•[/dim] {bg.name}  +  {vo.name}")
        console.print()

        for idx, (bg_file, vo_file) in enumerate(pairs, 1):
            console.print(
                f"[bold blue]── Pair {idx}/{len(pairs)} ──[/bold blue]"
            )
            _process_pair(
                file1=str(bg_file),
                file2=str(vo_file),
                fade_in_ms=fade_in_ms,
                fade_out_ms=fade_out_ms,
                delay_ms=delay_ms,
                blend_ms=blend_ms,
                output_filename=None,  # auto-generate per pair
                output_dir=str(file1_path),
                output_format=output_format,
                optimize=optimize,
                bg_level_lufs=bg_level_lufs,
                voice_level_lufs=voice_level_lufs,
                yes_to_all=yes_to_all,
                dry_run=dry_run,
                verbose=verbose,
            )

        if not dry_run:
            print_success(f"All {len(pairs)} pair(s) processed.")
        return

    # ── Two-file mode ───────────────────────────────────────────────
    if file2 is None:
        file2 = Prompt.ask("[bold]Path to secondary audio file[/bold]").strip()
        if not file2:
            print_error("No secondary audio file provided.")
            raise typer.Exit(code=1)

    _process_pair(
        file1=file1,
        file2=file2,
        fade_in_ms=fade_in_ms,
        fade_out_ms=fade_out_ms,
        delay_ms=delay_ms,
        blend_ms=blend_ms,
        output_filename=output_filename,
        output_dir=None,
        output_format=output_format,
        optimize=optimize,
        bg_level_lufs=bg_level_lufs,
        voice_level_lufs=voice_level_lufs,
        yes_to_all=yes_to_all,
        dry_run=dry_run,
        verbose=verbose,
    )


if __name__ == "__main__":
    app()
