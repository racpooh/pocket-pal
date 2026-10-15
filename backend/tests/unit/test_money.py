"""FI-1..FI-3. Expected values computed by hand, not by the implementation."""

import pytest

from finassist.domain.money import MoneyParseError, format_thb, parse_thb, split_evenly


@pytest.mark.parametrize(
    "text, expected",
    [
        ("10", 1_000),
        ("0.01", 1),
        ("1234.50", 123_450),
        ("1,234.5", 123_450),
        ("฿1,234.50", 123_450),
        ("1,234.50 บาท", 123_450),
        ("THB 120.00", 12_000),
        ("1,000,000", 100_000_000),
        ("๑๒๐.๕๐", 12_050),  # Thai digits
        ("  99.9 ", 9_990),
    ],
)
def test_parse_valid(text, expected):
    assert parse_thb(text) == expected


@pytest.mark.parametrize(
    "text",
    ["", "   ", "0", "0.00", "-5", "+5", "(5)", "1.234", "1,23", "12,34.00", "1,234,5",
     "1e3", "1.", ".5", "abc", "1.2.3", "١٢", "100000001"],
)
def test_parse_rejects(text):
    with pytest.raises(MoneyParseError):
        parse_thb(text)


def test_parse_rejects_non_string():
    with pytest.raises(MoneyParseError):
        parse_thb(12.5)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "satang, expected",
    [(0, "0.00"), (1, "0.01"), (12_050, "120.50"), (123_456_789, "1,234,567.89"), (-1_050, "-10.50")],
)
def test_format(satang, expected):
    assert format_thb(satang) == expected


def test_format_rejects_float_and_bool():
    with pytest.raises(TypeError):
        format_thb(1.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        format_thb(True)


def test_split_evenly_reports_remainder():
    # 1,000.00 THB over 7 days: 14285 * 7 = 99995, remainder 5 satang
    assert split_evenly(100_000, 7) == (14_285, 5)
    share, rem = split_evenly(100_000, 7)
    assert share * 7 + rem == 100_000


def test_split_evenly_rejects_negative_and_zero_parts():
    with pytest.raises(ValueError):
        split_evenly(-1, 3)
    with pytest.raises(ValueError):
        split_evenly(100, 0)
