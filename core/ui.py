"""Rich-based terminal UI for Stretto."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

if TYPE_CHECKING:
    pass

console = Console()
error_console = Console(stderr=True)


@dataclass
class AudioInfo:
    """Metadata for an audio file."""

    path: str
    duration_ms: int
    codec: str
    sample_rate: int
    channels: int

    @property
    def duration_s(self) -> float:
        return self.duration_ms / 1000.0

    def duration_display(self) -> str:
        """Human-readable duration string."""
        total_s = self.duration_ms / 1000.0
        if total_s < 60:
            return f"{total_s:.1f}s"
        minutes = int(total_s // 60)
        seconds = total_s % 60
        return f"{minutes}m {seconds:.1f}s"


def print_error(message: str) -> None:
    """Print a formatted error message to stderr."""
    error_console.print(f"[bold red]Error:[/bold red] {message}")


def print_warning(message: str) -> None:
    """Print a formatted warning message."""
    console.print(f"[bold yellow]Warning:[/bold yellow] {message}")


def print_success(message: str) -> None:
    """Print a formatted success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def display_plan(
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
    iterations: int | None = None,
) -> None:
    """Display the execution plan as a Rich table inside a panel."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Property", style="bold cyan")
    table.add_column("Value")

    table.add_row("File 1 (primary)", file1_info.path)
    table.add_row("  Duration", file1_info.duration_display())
    table.add_row("  Codec", file1_info.codec)
    table.add_row("  Sample rate", f"{file1_info.sample_rate} Hz")
    table.add_row("  Channels", str(file1_info.channels))
    table.add_row("", "")
    table.add_row("File 2 (secondary)", file2_info.path)
    table.add_row("  Duration", file2_info.duration_display())
    table.add_row("  Codec", file2_info.codec)
    table.add_row("  Sample rate", f"{file2_info.sample_rate} Hz")
    table.add_row("  Channels", str(file2_info.channels))
    table.add_row("", "")
    table.add_row("Delay", f"{delay_ms}ms")

    if needs_loop:
        table.add_row("Looping", f"[yellow]{iterations} iterations[/yellow]")
        table.add_row("Loop blend", f"{blend_ms}ms crossfade")
    else:
        table.add_row("Looping", "[green]Not needed[/green]")

    if fade_in_ms > 0:
        table.add_row("Fade-in", f"{fade_in_ms}ms")
    if fade_out_ms > 0:
        table.add_row("Fade-out", f"{fade_out_ms}ms")

    table.add_row("", "")
    table.add_row("Output", output_filename)
    table.add_row("Format", output_format)
    table.add_row("Optimized", "[green]Yes[/green]" if optimize else "[yellow]No[/yellow]")

    console.print(Panel(table, title="[bold]Stretto — Execution Plan[/bold]", border_style="blue"))


def confirm_loop(
    d1_ms: int,
    d_target_ms: int,
    iterations: int,
    blend_ms: int,
) -> bool:
    """Prompt the user to confirm looping. Returns True if confirmed."""
    d1_s = d1_ms / 1000.0
    dt_s = d_target_ms / 1000.0
    console.print(
        f"\n[yellow]Primary audio ({d1_s:.1f}s) is shorter than target "
        f"({dt_s:.1f}s).[/yellow]"
    )
    return Confirm.ask(
        f"Loop [bold]{iterations}[/bold] times with [bold]{blend_ms}ms[/bold] crossfade?",
        default=True,
    )
