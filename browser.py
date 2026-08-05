import re
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from playwright_stealth import Stealth

from providers import NotFound, UpstreamBlocked, UpstreamError, _extract_text, UA

_lib = None  # (playwright, browser)

BROWSER_TIMEOUT = 45000
RESULT_TIMEOUT = 30000

_PLATE_HINTS = ("plate", "rego", "registration", "vehicle number", "number plate")


def _browser():
    global _lib
    if _lib is not None and _lib[1] is not None and _lib[1].is_connected():
        return _lib[1]
    if _lib is None:
        _lib = [sync_playwright().start(), None]
    if _lib[1] is None or not _lib[1].is_connected():
        _lib[1] = _lib[0].chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage",
                                                "--disable-blink-features=AutomationControlled"])
    return _lib[1]


def _new_context(browser):
    ctx = browser.new_context(user_agent=UA, locale="en-AU",
                              viewport={"width": 1280, "height": 900})
    ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return ctx


def _wait_input(page, state):
    try:
        page.wait_for_selector("input:visible", timeout=BROWSER_TIMEOUT)
    except PWTimeout:
        text = page.inner_text("body")
        if _is_challenge(text):
            raise UpstreamBlocked(f"{state}: bot security verification did not resolve")
        raise UpstreamError(f"{state}: timed out waiting for the lookup form")


def _fill_plate(page, plate, selector=None, state=""):
    if selector:
        page.locator(selector).first.wait_for(state="visible", timeout=BROWSER_TIMEOUT)
        page.fill(selector, plate)
        return
    _wait_input(page, state)
    inputs = page.locator("input:visible")
    target = None
    for i in range(inputs.count()):
        el = inputs.nth(i)
        ctx = (
            (el.get_attribute("title") or "")
            + " " + (el.get_attribute("placeholder") or "")
            + " " + (el.get_attribute("name") or "")
            + " " + (el.get_attribute("id") or "")
        ).lower()
        if any(h in ctx for h in _PLATE_HINTS):
            target = el
            break
    if target is None:
        for i in range(inputs.count()):
            el = inputs.nth(i)
            if el.get_attribute("type") in (None, "", "text"):
                target = el
                break
    if target is None:
        raise UpstreamError("no plate input found on page")
    target.fill(plate)


def _click_submit(page, text=None):
    if text:
        page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=15000)
        page.get_by_text(text, exact=False).first.click(timeout=15000)
        return
    for sel in ("button[type=submit]:visible", "input[type=submit]:visible"):
        loc = page.locator(sel)
        if loc.count():
            loc.first.click(timeout=15000)
            return
    raise UpstreamError("no submit button found on page")


def _looks_like_not_found(t):
    t = t.lower()
    for p in ("registration not found", "no registration details", "no vehicle registration",
              "not currently registered", "registration number not found", "no record of this",
              "cannot be found", "is not registered", "no registration found", "not registered"):
        if p in t:
            return True
    return False


def _is_challenge(text):
    t = text.lower()
    for p in ("just a moment", "enable javascript", "security verification", "you are not a bot",
              "checking your browser", "cloudflare", "challenge"):
        if p in t:
            return True
    return False


def _check_blocked(state, text):
    t = text.lower()
    if state == "SA" and ("outside australia" in t or "unavailable from outside" in t):
        raise UpstreamBlocked("SA: geo-blocked (non-Australian IP)")


# per-state navigation ----------------------------------------------------

def _vic(page, plate):
    page.goto("https://www.vicroads.vic.gov.au/registration/buy-sell-or-transfer-a-vehicle/check-vehicle-registration",
              wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    _fill_plate(page, plate, state="VIC")
    _click_submit(page)


def _nsw(page, plate):
    page.goto("https://www.service.nsw.gov.au/transaction/check-a-vehicle-registration",
              wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    link = page.get_by_text("Check online", exact=False).first
    link.wait_for(state="visible", timeout=BROWSER_TIMEOUT)
    link.click()
    page.wait_for_load_state("networkidle", timeout=BROWSER_TIMEOUT)
    _fill_plate(page, plate, state="NSW")
    _click_submit(page)


def _sa(page, plate):
    page.goto("https://account.ezyreg.sa.gov.au/account/check-registration.htm",
              wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    _fill_plate(page, plate, selector="#plateNumber", state="SA")
    page.click("#step-1-2-submit", timeout=15000)


def _nt(page, plate):
    page.goto("https://nt.gov.au/driving/rego/existing-nt-registration/rego-check",
              wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    _fill_plate(page, plate, state="NT")
    _click_submit(page)


def _tas(page, plate):
    page.goto("https://transport.stgro-2780.saas.squiz.cloud/rego-status/search",
              wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    _fill_plate(page, plate, selector="input[name=plate]", state="TAS")
    _click_submit(page)


def _wa(page, plate):
    page.goto("https://online.transport.wa.gov.au/webExternal/registration",
              wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    _fill_plate(page, plate, state="WA")
    _click_submit(page)


def _act(page, plate):
    page.goto("https://www.accesscanberra.act.gov.au/app/answers/detail/a_id/1594/~/check-vehicle-registration",
              wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    _fill_plate(page, plate, state="ACT")
    _click_submit(page)


FUNCS = {"VIC": _vic, "NSW": _nsw, "SA": _sa, "NT": _nt, "TAS": _tas, "WA": _wa, "ACT": _act}


def browser_lookup(plate, state):
    browser = _browser()
    ctx = _new_context(browser)
    page = ctx.new_page()
    Stealth(navigator_user_agent=False).apply_stealth_sync(page)
    try:
        FUNCS[state](page, plate)
        deadline = time.time() + RESULT_TIMEOUT
        challenge_seen = False
        while time.time() < deadline:
            page.wait_for_timeout(2000)
            try:
                text = page.inner_text("body")
            except Exception:
                continue
            if _is_challenge(text):
                challenge_seen = True
                continue
            _check_blocked(state, text)
            if _looks_like_not_found(text):
                raise NotFound(plate)
            result = _extract_text(text)
            if any(result.values()):
                return result
        if challenge_seen:
            raise UpstreamBlocked(f"{state}: bot security verification did not resolve")
        raise UpstreamError(f"{state}: vehicle details could not be retrieved")
    except PWTimeout as e:
        raise UpstreamError(f"{state}: timed out: {e}")
    finally:
        ctx.close()
