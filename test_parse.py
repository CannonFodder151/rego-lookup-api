"""Regression test for Make/Model parsing (VIC reports them combined).

Run: python test_parse.py
"""

import sys

from bs4 import BeautifulSoup

from providers import _extract_result, _split_make_model


def test_split_make_model():
    cases = [
        ("YAMAHA FZ6S", ("YAMAHA", "FZ6S")),
        ("TOYOTA", ("TOYOTA", None)),
        ("LAND ROVER DISCOVERY", ("LAND ROVER", "DISCOVERY")),
        ("MERCEDES-BENZ C200", ("MERCEDES-BENZ", "C200")),
        ("ASTON MARTIN DB11", ("ASTON MARTIN", "DB11")),
        ("RANGE ROVER EVOQUE", ("RANGE ROVER", "EVOQUE")),
        ("KAWASAKI NINJA 250R", ("KAWASAKI", "NINJA 250R")),
        ("TOYOTA LAND CRUISER PRADO", ("TOYOTA", "LAND CRUISER PRADO")),
        ("GAS GAS EC300", ("GAS GAS", "EC300")),
        ("HOLDEN COMMODORE", ("HOLDEN", "COMMODORE")),
        ("TESLA MODEL 3", ("TESLA", "MODEL 3")),
        ("SUZUKI GSX-R600", ("SUZUKI", "GSX-R600")),
    ]
    for value, expected in cases:
        got = _split_make_model(value)
        assert got == expected, f"{value!r}: expected {expected}, got {got}"


VIC_RESULT_HTML = """
<div class="vhr-panel__list-item-container vhr-panel__list-item-container--stacked">
 <dt class="vhr-panel__list-item vhr-panel__list-item--term">Year</dt>
 <dd class="vhr-panel__list-item vhr-panel__list-item--description">2009</dd>
</div>
<div class="vhr-panel__list-item-container vhr-panel__list-item-container--stacked">
 <dt class="vhr-panel__list-item vhr-panel__list-item--term">Make</dt>
 <dd class="vhr-panel__list-item vhr-panel__list-item--description">YAMAHA FZ6S</dd>
</div>
<div class="vhr-panel__list-item-container vhr-panel__list-item-container--stacked">
 <dt class="vhr-panel__list-item vhr-panel__list-item--term">Body type</dt>
 <dd class="vhr-panel__list-item vhr-panel__list-item--description">SOLO</dd>
</div>
<div class="vhr-panel__list-item-container vhr-panel__list-item-container--stacked">
 <dt class="vhr-panel__list-item vhr-panel__list-item--term">Colour</dt>
 <dd class="vhr-panel__list-item vhr-panel__list-item--description">BLACK</dd>
</div>
<div class="vhr-panel__list-item-container vhr-panel__list-item-container--stacked">
 <dt class="vhr-panel__list-item vhr-panel__list-item--term">VIN/Chassis</dt>
 <dd class="vhr-panel__list-item vhr-panel__list-item--description">JYARJ14487A000061</dd>
</div>
"""


def test_extract_result_splits_vic_combined_make():
    result = _extract_result("", VIC_RESULT_HTML)
    assert result["make"] == "YAMAHA", result
    assert result["model"] == "FZ6S", result
    assert result["year"] == 2009, result
    assert result["colour"] == "BLACK", result
    assert result["body_type"] == "SOLO", result


def test_extract_result_keeps_separate_make_model():
    html = """
    <div class="row">
      <dt>Make</dt><dd>TOYOTA</dd>
    </div>
    <div class="row">
      <dt>Model</dt><dd>COROLLA</dd>
    </div>
    """
    result = _extract_result("", html)
    assert result["make"] == "TOYOTA", result
    assert result["model"] == "COROLLA", result


def test_extract_result_leaves_single_word_make():
    html = """
    <div class="row">
      <dt>Make</dt><dd>TOYOTA</dd>
    </div>
    """
    result = _extract_result("", html)
    assert result["make"] == "TOYOTA", result
    assert result["model"] is None, result


if __name__ == "__main__":
    sys.path.insert(0, ".")
    test_split_make_model()
    test_extract_result_splits_vic_combined_make()
    test_extract_result_keeps_separate_make_model()
    test_extract_result_leaves_single_word_make()
    print("all tests passed")
