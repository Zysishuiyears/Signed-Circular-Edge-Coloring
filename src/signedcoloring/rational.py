from __future__ import annotations

from fractions import Fraction
from typing import Any


def parse_fraction(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if isinstance(value, int):
        return Fraction(value, 1)
    if isinstance(value, float):
        return Fraction(str(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("Expected a non-empty rational value.")
        return Fraction(stripped)
    raise TypeError(f"Unsupported rational value type: {type(value)!r}")


def fraction_to_string(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def normalize_on_circle(value: Fraction, circumference: Fraction) -> Fraction:
    if circumference <= 0:
        raise ValueError("Circle circumference must be positive.")
    reduced = value % circumference
    if reduced < 0:
        reduced += circumference
    if reduced == circumference:
        return Fraction(0, 1)
    return reduced


def circle_distance(x: Fraction, y: Fraction, circumference: Fraction) -> Fraction:
    left = normalize_on_circle(x, circumference)
    right = normalize_on_circle(y, circumference)
    diff = abs(left - right)
    return min(diff, circumference - diff)
