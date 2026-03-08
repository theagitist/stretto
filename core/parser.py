"""Time suffix parsing and iteration math for Stretto."""

import math
import re

import typer

# Matches: optional negative sign, digits (with optional decimal), optional unit (ms or s)
_TIME_PATTERN = re.compile(r"^(-?)(\d+\.?\d*)(ms|s)?$", re.IGNORECASE)


def parse_time(value: str) -> int:
    """Parse a time string into integer milliseconds.

    Supported formats:
        - Pure integers: "2000" → 2000 ms
        - Millisecond suffix: "1500ms" → 1500 ms
        - Second suffix: "2s" → 2000 ms
        - Floats with suffix: "1.5s" → 1500 ms

    Raises:
        typer.BadParameter: If format is invalid or value is negative.
    """
    stripped = value.strip()
    match = _TIME_PATTERN.match(stripped)

    if not match:
        raise typer.BadParameter(
            f"Invalid time format: '{value}'. Use '2s', '1500ms', or '1500'."
        )

    sign, number_str, unit = match.groups()

    if sign == "-":
        raise typer.BadParameter(
            f"Time value cannot be negative: '{value}'."
        )

    numeric = float(number_str)

    if unit and unit.lower() == "s":
        numeric *= 1000

    return round(numeric)


def calculate_iterations(d_target: int, d1: int, blend: int) -> int:
    """Calculate the number of loop iterations needed to reach d_target.

    Each iteration after the first adds (d1 - blend) milliseconds because the
    crossfade overlaps the end of one iteration with the start of the next.

    Args:
        d_target: Target duration in milliseconds.
        d1: Duration of the primary audio in milliseconds.
        blend: Crossfade duration in milliseconds.

    Returns:
        Number of iterations (N >= 1).

    Raises:
        ValueError: If blend >= d1 (would cause zero or negative denominator).
    """
    if blend >= d1:
        raise ValueError(
            f"Loop blend duration ({blend}ms) cannot be equal to or greater "
            f"than the source audio duration ({d1}ms)."
        )

    if d_target <= d1:
        return 1

    if blend == 0:
        return math.ceil(d_target / d1)

    return math.ceil((d_target - blend) / (d1 - blend))
