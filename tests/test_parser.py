"""Tests for core.parser — time suffix parsing and iteration math."""

import pytest
import typer

from core.parser import calculate_iterations, parse_time


# ── parse_time: valid inputs ────────────────────────────────────────────

class TestParseTimeValid:
    def test_pure_integer(self):
        assert parse_time("2000") == 2000

    def test_zero(self):
        assert parse_time("0") == 0

    def test_ms_suffix(self):
        assert parse_time("1500ms") == 1500

    def test_zero_ms(self):
        assert parse_time("0ms") == 0

    def test_s_suffix(self):
        assert parse_time("2s") == 2000

    def test_zero_s(self):
        assert parse_time("0s") == 0

    def test_float_seconds(self):
        assert parse_time("1.5s") == 1500

    def test_float_ms(self):
        assert parse_time("100.7ms") == 101

    def test_case_insensitive_ms(self):
        assert parse_time("500MS") == 500

    def test_case_insensitive_s(self):
        assert parse_time("2.5S") == 2500

    def test_whitespace_stripped(self):
        assert parse_time("  2s  ") == 2000

    def test_large_value(self):
        assert parse_time("60s") == 60000

    def test_fractional_rounding(self):
        assert parse_time("1.5555s") == 1556


# ── parse_time: invalid inputs ──────────────────────────────────────────

class TestParseTimeInvalid:
    def test_negative_integer(self):
        with pytest.raises(typer.BadParameter, match="cannot be negative"):
            parse_time("-500")

    def test_negative_with_suffix(self):
        with pytest.raises(typer.BadParameter, match="cannot be negative"):
            parse_time("-2s")

    def test_non_numeric(self):
        with pytest.raises(typer.BadParameter, match="Invalid time format"):
            parse_time("abc")

    def test_empty_string(self):
        with pytest.raises(typer.BadParameter, match="Invalid time format"):
            parse_time("")

    def test_unsupported_unit(self):
        with pytest.raises(typer.BadParameter, match="Invalid time format"):
            parse_time("5m")

    def test_unit_without_number(self):
        with pytest.raises(typer.BadParameter, match="Invalid time format"):
            parse_time("ms")

    def test_malformed_number(self):
        with pytest.raises(typer.BadParameter, match="Invalid time format"):
            parse_time("2.5.3s")

    def test_negative_ms_suffix(self):
        with pytest.raises(typer.BadParameter, match="cannot be negative"):
            parse_time("-100ms")


# ── calculate_iterations ────────────────────────────────────────────────

class TestCalculateIterations:
    def test_no_loop_needed(self):
        assert calculate_iterations(d_target=5000, d1=10000, blend=500) == 1

    def test_exact_fit(self):
        assert calculate_iterations(d_target=10000, d1=10000, blend=500) == 1

    def test_standard_loop_with_blend(self):
        # ceil((60000 - 500) / (10000 - 500)) = ceil(59500 / 9500) = ceil(6.26) = 7
        assert calculate_iterations(d_target=60000, d1=10000, blend=500) == 7

    def test_zero_blend(self):
        # ceil(5000 / 2000) = 3
        assert calculate_iterations(d_target=5000, d1=2000, blend=0) == 3

    def test_short_source_with_blend(self):
        # ceil((5000 - 500) / (2000 - 500)) = ceil(4500 / 1500) = 3
        assert calculate_iterations(d_target=5000, d1=2000, blend=500) == 3

    def test_blend_equals_d1_raises(self):
        with pytest.raises(ValueError, match="cannot be equal to or greater"):
            calculate_iterations(d_target=5000, d1=1000, blend=1000)

    def test_blend_exceeds_d1_raises(self):
        with pytest.raises(ValueError, match="cannot be equal to or greater"):
            calculate_iterations(d_target=5000, d1=500, blend=600)

    def test_very_short_source(self):
        # 1s clip under 60s track, no blend: ceil(60000/1000) = 60
        assert calculate_iterations(d_target=60000, d1=1000, blend=0) == 60

    def test_very_short_source_with_blend(self):
        # ceil((60000 - 200) / (1000 - 200)) = ceil(59800 / 800) = ceil(74.75) = 75
        assert calculate_iterations(d_target=60000, d1=1000, blend=200) == 75
