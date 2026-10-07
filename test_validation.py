"""Validation regression test for plate / vehicle_type (AUT-318).

Run: python test_validation.py
"""

import sys

from pydantic import ValidationError

from main import LookupRequest


def test_valid_plates_normalise():
    cases = [
        ("1ABC123", "1ABC123"),
        ("  abc123  ", "ABC123"),
        ("3b4pv", "3B4PV"),
        ("ABC12D", "ABC12D"),
    ]
    for value, expected in cases:
        got = LookupRequest(plate=value, state="QLD").plate
        assert got == expected, f"{value!r}: expected {expected!r}, got {got!r}"


def test_invalid_plates_rejected():
    cases = [
        "<svg/onload=1>",
        "' OR '1'='1",
        "1;ls",
        "..//etc/passwd",
        "ABC123DEF",      # 9 chars
        "AB C 123",       # spaces inside
        "1-ABC-1",
    ]
    for value in cases:
        try:
            LookupRequest(plate=value, state="QLD")
        except ValidationError:
            continue
        raise AssertionError(f"plate {value!r} should have been rejected")


def test_vehicle_type_enum():
    for vt in ("car", "motorcycle"):
        assert LookupRequest(plate="1ABC123", state="QLD", vehicle_type=vt).vehicle_type == vt
    try:
        LookupRequest(plate="1ABC123", state="QLD", vehicle_type="boat")
    except ValidationError:
        return
    raise AssertionError("vehicle_type='boat' should have been rejected")


if __name__ == "__main__":
    sys.path.insert(0, ".")
    test_valid_plates_normalise()
    test_invalid_plates_rejected()
    test_vehicle_type_enum()
    print("all tests passed")
