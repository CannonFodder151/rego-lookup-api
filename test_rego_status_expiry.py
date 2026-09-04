"""Regression tests for AUT-2413: rego_status + rego_expiry_date extraction.

Covers text regex, DOM parsing across the dominant AU state site patterns
(QLD dt/dd rows, NSW 2-cell tr/th+td rows, VIC vhr-panel dt/dd pairs),
status normalisation (valid/expired/unknown) and ISO 8601 expiry parsing
across the date formats used by AU state rego sites.

Run: python test_rego_status_expiry.py
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__) or ".")

from providers import (_extract_result, _extract_text, _normalise_status,
                       _parse_expiry)


# ---------------------------------------------------------------- text regex

def test_text_extracts_qld_format():
    text = ("Registration number: 123ABC Registration status: Current "
            "Registration expiry: 12/03/2025 Make: TOYOTA Model: COROLLA "
            "Year: 2018 Colour: WHITE Body type: SEDAN")
    r = _extract_text(text)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2025-03-12", r
    assert r["make"] == "TOYOTA", r


def test_text_extracts_expired_status():
    text = ("Registration status: Expired Registration expiry date: 01/01/2020 "
            "Make: HOLDEN Model: COMMODORE")
    r = _extract_text(text)
    assert r["rego_status"] == "expired", r
    assert r["rego_expiry_date"] == "2020-01-01", r


def test_text_unknown_status_when_no_known_word():
    text = "Registration status: Pending verification"
    r = _extract_text(text)
    assert r["rego_status"] == "unknown", r


def test_text_unparseable_expiry_returns_none():
    text = "Registration status: Current Registration expiry: sometime soon Make: TOYOTA"
    r = _extract_text(text)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] is None, r


# ---------------------------------------------------------------- DOM QLD

QLD_RESULT_HTML = """
<div class="row"><dt>Registration number</dt><dd>123ABC</dd></div>
<div class="row"><dt>Registration status</dt><dd>Current</dd></div>
<div class="row"><dt>Registration expiry date</dt><dd>12 March 2025</dd></div>
<div class="row"><dt>Make</dt><dd>TOYOTA</dd></div>
<div class="row"><dt>Model</dt><dd>COROLLA</dd></div>
<div class="row"><dt>Year of manufacture</dt><dd>2018</dd></div>
<div class="row"><dt>Colour</dt><dd>WHITE</dd></div>
<div class="row"><dt>Body type</dt><dd>SEDAN</dd></div>
<div class="row"><dt>VIN/Chassis number</dt><dd>JTNB13HK903001234</dd></div>
"""


def test_dom_qld_extracts_status_and_expiry():
    r = _extract_result("", QLD_RESULT_HTML)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2025-03-12", r
    assert r["make"] == "TOYOTA", r
    assert r["year"] == 2018, r


# ---------------------------------------------------------------- DOM NSW (same-row tr)

NSW_RESULT_HTML = """
<table>
  <tr><th>Registration status</th><td>Registered</td></tr>
  <tr><th>Registration expiry date</th><td>15/06/2025</td></tr>
  <tr><th>Make</th><td>HONDA</td></tr>
  <tr><th>Model</th><td>CIVIC</td></tr>
  <tr><th>Year</th><td>2017</td></tr>
  <tr><th>Colour</th><td>GREY</td></tr>
  <tr><th>Body type</th><td>HATCHBACK</td></tr>
  <tr><th>VIN/Chassis</th><td>SHHFK2860CU123456</td></tr>
</table>
"""


def test_dom_nsw_same_row_extracts_status_and_expiry():
    r = _extract_result("", NSW_RESULT_HTML)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2025-06-15", r
    assert r["make"] == "HONDA", r
    assert r["model"] == "CIVIC", r


# ---------------------------------------------------------------- DOM VIC (vhr-panel)

VIC_RESULT_HTML = """
<div class="vhr-panel__list-item-container">
 <dt class="vhr-panel__list-item--term">Registration status</dt>
 <dd class="vhr-panel__list-item--description">Currently registered</dd>
</div>
<div class="vhr-panel__list-item-container">
 <dt class="vhr-panel__list-item--term">Registration expiry</dt>
 <dd class="vhr-panel__list-item--description">15 Jun 2025</dd>
</div>
<div class="vhr-panel__list-item-container">
 <dt class="vhr-panel__list-item--term">Year</dt>
 <dd class="vhr-panel__list-item--description">2017</dd>
</div>
<div class="vhr-panel__list-item-container">
 <dt class="vhr-panel__list-item--term">Make</dt>
 <dd class="vhr-panel__list-item--description">HONDA</dd>
</div>
<div class="vhr-panel__list-item-container">
 <dt class="vhr-panel__list-item--term">Model</dt>
 <dd class="vhr-panel__list-item--description">CIVIC</dd>
</div>
<div class="vhr-panel__list-item-container">
 <dt class="vhr-panel__list-item--term">Colour</dt>
 <dd class="vhr-panel__list-item--description">GREY</dd>
</div>
<div class="vhr-panel__list-item-container">
 <dt class="vhr-panel__list-item--term">Body type</dt>
 <dd class="vhr-panel__list-item--description">HATCHBACK</dd>
</div>
<div class="vhr-panel__list-item-container">
 <dt class="vhr-panel__list-item--term">VIN/Chassis</dt>
 <dd class="vhr-panel__list-item--description">SHHFK2860CU123456</dd>
</div>
"""


def test_dom_vic_extracts_status_and_expiry():
    r = _extract_result("", VIC_RESULT_HTML)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2025-06-15", r
    assert r["make"] == "HONDA", r


# ---------------------------------------------------------------- VIC expired

def test_dom_vic_expired():
    html = VIC_RESULT_HTML.replace("Currently registered", "Expired").replace("15 Jun 2025", "1 Jan 2020")
    r = _extract_result("", html)
    assert r["rego_status"] == "expired", r
    assert r["rego_expiry_date"] == "2020-01-01", r


# ---------------------------------------------------------------- helpers

def test_normalise_status_known_phrases():
    assert _normalise_status("Currently registered") == "valid"
    assert _normalise_status("Registered") == "valid"
    assert _normalise_status("Active") == "valid"
    assert _normalise_status("Expired") == "expired"
    assert _normalise_status("Lapsed") == "expired"
    assert _normalise_status("Not currently registered") == "expired"
    assert _normalise_status("Cancelled") == "expired"
    assert _normalise_status("Pending verification") == "unknown"
    assert _normalise_status("") is None
    assert _normalise_status(None) is None


def test_parse_expiry_formats():
    assert _parse_expiry("12/03/2025") == "2025-03-12"
    assert _parse_expiry("12/03/25") == "2025-03-12"
    assert _parse_expiry("12 March 2025") == "2025-03-12"
    assert _parse_expiry("15 Jun 2025") == "2025-06-15"
    assert _parse_expiry("1st January 2024") == "2024-01-01"
    assert _parse_expiry("2025-03-12") == "2025-03-12"
    assert _parse_expiry("sometime soon") is None
    assert _parse_expiry("") is None
    assert _parse_expiry(None) is None


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"all {len(tests)} tests passed")
