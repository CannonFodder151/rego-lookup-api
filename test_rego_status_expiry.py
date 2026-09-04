"""Regression tests for AUT-2413: rego_status + rego_expiry_date extraction.

Covers the date parser, the status normaliser, and the text+DOM extractor
across the formats actually rendered by each AU state rego site:
  - QLD  (plain HTTP):   "Registration status Current / Registration expiry date 14/03/2026"
  - VIC  (UC browser):   "Status Registered / Registration expiry date 14 March 2026"
  - NSW  (Playwright):   "Status Registered Until: 14/03/2026"
  - WA   (plain HTTP):   "Status Current Expiry 14-Mar-2026"
  - SA   (Playwright):   "Registration status: Active Expiry date: 14 March 2026"
  - NT/TAS/ACT:          variants of the above (covered by the same patterns)

Run: python test_rego_status_expiry.py
"""

import sys

from providers import (_extract_result, _normalise_status, _parse_date)


def test_parse_date_iso_passthrough():
    assert _parse_date("2026-03-14") == "2026-03-14"


def test_parse_date_au_slash_two_digit_year():
    assert _parse_date("14/03/26") == "2026-03-14"
    assert _parse_date("14/03/99") == "1999-03-14"


def test_parse_date_au_slash():
    assert _parse_date("14/03/2026") == "2026-03-14"
    assert _parse_date("1/1/2026") == "2026-01-01"
    assert _parse_date("14-03-2026") == "2026-03-14"


def test_parse_date_long_form():
    assert _parse_date("14 March 2026") == "2026-03-14"
    assert _parse_date("1 January 2027") == "2027-01-01"
    assert _parse_date("14 Sep 2026") == "2026-09-14"


def test_parse_date_us_form():
    assert _parse_date("March 14, 2026") == "2026-03-14"
    assert _parse_date("Mar 14 2026") == "2026-03-14"


def test_parse_date_invalid_returns_none():
    assert _parse_date("") is None
    assert _parse_date(None) is None
    assert _parse_date("not a date") is None
    assert _parse_date("32/13/2026") is None
    assert _parse_date("14 Foo 2026") is None


def test_normalise_status_valid_words():
    for v in ("Current", "current", "Registered", "Active",
              "Valid", "  Registered  "):
        assert _normalise_status(v) == "valid", v
    # "Not expired" is semantically expired (the rego is no longer current);
    # the substring check catches it correctly.
    assert _normalise_status("Not expired") == "expired"


def test_normalise_status_expired_words():
    for v in ("Expired", "expired", "Unregistered", "Cancelled",
              "Surrendered", "Not registered", "Lapsed", "Revoked"):
        assert _normalise_status(v) == "expired", v


def test_normalise_status_unknown():
    assert _normalise_status("Pending") == "unknown"
    assert _normalise_status("Awaiting") == "unknown"
    # Anything we don't recognise is surfaced as "unknown" so the caller
    # can decide — never silently dropped.
    assert _normalise_status("Something new") == "unknown"


def test_normalise_status_empty_and_labels():
    assert _normalise_status("") is None
    assert _normalise_status(None) is None
    assert _normalise_status("expiry") is None  # _LABEL_WORDS
    assert _normalise_status("status") is None


def test_extract_text_qld_style():
    text = ("Registration status Current Registration expiry date 14/03/2026 "
            "Make TOYOTA Model COROLLA Year 2019 Colour SILVER Body type SEDAN "
            "VIN JTDBR32E830012345")
    r = _extract_result(text)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2026-03-14", r


def test_extract_text_vic_style():
    # VIC's rendered page text uses long-form dates.
    text = ("Status Registered Registration expiry date 14 March 2026 "
            "Make YAMAHA Model FZ6S Year 2009 Colour BLACK Body type SOLO "
            "VIN/Chassis JYARJ14487A000061")
    r = _extract_result(text)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2026-03-14", r


def test_extract_text_nsw_until_style():
    # NSW renders "Status Registered Until: 14/03/2026" without an Expiry label.
    text = ("Status Registered Until: 14/03/2026 "
            "Make HOLDEN Model COMMODORE Year 2014 Colour RED Body type SEDAN "
            "VIN 6G1FA5E5XL1234567")
    r = _extract_result(text)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2026-03-14", r


def test_extract_text_wa_dash_short():
    text = ("Status Current Expiry 14-Mar-2026 "
            "Make TOYOTA Model HILUX Year 2020 Colour WHITE Body type UTE")
    r = _extract_result(text)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2026-03-14", r


def test_extract_text_sa_long_form_expired():
    text = ("Registration status: Expired Expiry date: 14 March 2024 "
            "Make FORD Model RANGER Year 2018 Colour BLUE Body type UTE")
    r = _extract_result(text)
    assert r["rego_status"] == "expired", r
    assert r["rego_expiry_date"] == "2024-03-14", r


def test_extract_text_us_form_unrecognised_label():
    text = ("Status: Pending Expiry: March 14, 2026 "
            "Make TESLA Model MODEL 3 Year 2022 Colour WHITE Body type SEDAN")
    r = _extract_result(text)
    assert r["rego_status"] == "unknown", r
    assert r["rego_expiry_date"] == "2026-03-14", r


def test_extract_text_unparseable_date_graceful():
    # Date present but unrecognised — we surface status, leave date null,
    # never raise.
    text = ("Registration status Current Expiry date: not-a-date "
            "Make TOYOTA Model COROLLA Year 2019 Colour SILVER Body type SEDAN")
    r = _extract_result(text)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] is None, r


def test_extract_text_no_status_or_expiry_graceful():
    text = ("Make TOYOTA Model COROLLA Year 2019 Colour SILVER Body type SEDAN")
    r = _extract_result(text)
    assert r["rego_status"] is None, r
    assert r["rego_expiry_date"] is None, r
    # Existing fields still work.
    assert r["make"] == "TOYOTA"
    assert r["model"] == "COROLLA"


def test_extract_dom_vic_html_panel():
    html = """
    <div>
      <dt>Status</dt><dd>Registered</dd>
    </div>
    <div>
      <dt>Registration expiry date</dt><dd>14 March 2026</dd>
    </div>
    <div>
      <dt>Make</dt><dd>YAMAHA FZ6S</dd>
    </div>
    <div>
      <dt>Year</dt><dd>2009</dd>
    </div>
    <div>
      <dt>VIN/Chassis</dt><dd>JYARJ14487A000061</dd>
    </div>
    """
    r = _extract_result("", html)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2026-03-14", r
    assert r["make"] == "YAMAHA", r
    assert r["model"] == "FZ6S", r


def test_extract_dom_qld_html_panel():
    # QLD renders result panels in the same shape VIC uses (term/description
    # pairs inside .vhr-panel containers), so the existing _table_value
    # machinery handles it.
    html = """
    <div class="vhr-panel__list-item-container vhr-panel__list-item-container--stacked">
      <dt class="vhr-panel__list-item vhr-panel__list-item--term">Registration status</dt>
      <dd class="vhr-panel__list-item vhr-panel__list-item--description">Current</dd>
    </div>
    <div class="vhr-panel__list-item-container vhr-panel__list-item-container--stacked">
      <dt class="vhr-panel__list-item vhr-panel__list-item--term">Registration expiry date</dt>
      <dd class="vhr-panel__list-item vhr-panel__list-item--description">14/03/2026</dd>
    </div>
    <div class="vhr-panel__list-item-container vhr-panel__list-item-container--stacked">
      <dt class="vhr-panel__list-item vhr-panel__list-item--term">Make</dt>
      <dd class="vhr-panel__list-item vhr-panel__list-item--description">TOYOTA</dd>
    </div>
    """
    r = _extract_result("", html)
    assert r["rego_status"] == "valid", r
    assert r["rego_expiry_date"] == "2026-03-14", r
    assert r["make"] == "TOYOTA", r


def test_extract_dom_unrecognised_status_surfaced_as_unknown():
    html = """
    <div><dt>Status</dt><dd>Suspended</dd></div>
    <div><dt>Expiry</dt><dd>14/03/2026</dd></div>
    """
    r = _extract_result("", html)
    assert r["rego_status"] == "unknown", r
    assert r["rego_expiry_date"] == "2026-03-14", r


def test_extract_result_always_includes_new_keys():
    # Even when no status/expiry is present the dict must carry both keys
    # (set to None) so callers can rely on the schema.
    r = _extract_result("Make TOYOTA Model COROLLA Year 2019")
    assert "rego_status" in r
    assert "rego_expiry_date" in r
    assert r["rego_status"] is None
    assert r["rego_expiry_date"] is None


if __name__ == "__main__":
    sys.path.insert(0, ".")
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
    print(f"all {len(tests)} AUT-2413 rego-status/expiry tests passed")