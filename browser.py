import asyncio
import os
import re
import time

from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from playwright_stealth import Stealth

from providers import (NotFound, UpstreamBlocked, UpstreamError, _extract_result,
                       _looks_like_not_found, UA)

BROWSER_TIMEOUT = 45000
RESULT_TIMEOUT = 30000

_PLATE_HINTS = ("plate", "rego", "registration", "vehicle number", "number plate")

ENTRY = {
    "VIC": "https://www.vicroads.vic.gov.au/registration/buy-sell-or-transfer-a-vehicle/check-vehicle-registration",
    "NSW": "https://www.service.nsw.gov.au/transaction/check-a-vehicle-registration",
    "SA": "https://account.ezyreg.sa.gov.au/account/check-registration.htm",
    "NT": "https://nt.gov.au/driving/rego/existing-nt-registration/rego-check",
    "TAS": "https://transport.stgro-2780.saas.squiz.cloud/rego-status/search",
    "WA": "https://online.transport.wa.gov.au/webExternal/registration",
    "ACT": "https://www.accesscanberra.act.gov.au/app/answers/detail/a_id/1594/~/check-vehicle-registration",
}


def _fsr_base():
    return (os.getenv("FLARESOLVERR_URL") or "").strip().rstrip("/") or None


def _fsr_prewarm(url):
    base = _fsr_base()
    if not base:
        return UA, []
    try:
        import requests
        r = requests.post(base + "/v1", json={
            "cmd": "request.get", "url": url, "maxTimeout": 30000}, timeout=45)
        data = r.json()
        if data.get("status") != "ok":
            return UA, []
        sol = data["solution"]
        cookies = []
        for c in sol.get("cookies", []):
            domain = (c.get("domain") or "").lstrip(".")
            if domain:
                cookies.append({"name": c["name"], "value": c["value"],
                                "domain": domain, "path": c.get("path", "/")})
        return sol.get("userAgent") or UA, cookies
    except Exception:
        return UA, []


async def _is_plate_input(inp):
    attrs = []
    for a in ("placeholder", "title", "name", "id", "aria-label"):
        v = await inp.get_attribute(a)
        if v:
            attrs.append(v)
    ctx = " ".join(attrs).lower()
    return any(h in ctx for h in _PLATE_HINTS)


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


async def _fill_plate(page, plate, state="", selector=None):
    if selector:
        await page.locator(selector).first.wait_for(state="visible", timeout=15000)
        await page.fill(selector, plate)
        return
    try:
        await page.wait_for_selector("input:visible", timeout=BROWSER_TIMEOUT)
    except PWTimeout:
        text = await page.inner_text("body")
        if _is_challenge(text):
            raise UpstreamBlocked(f"{state}: bot security verification did not resolve")
        raise UpstreamError(f"{state}: timed out waiting for the lookup form")
    inputs = page.locator("input:visible")
    target = None
    for i in range(await inputs.count()):
        el = inputs.nth(i)
        if await _is_plate_input(el):
            target = el
            break
    if target is None:
        for i in range(await inputs.count()):
            el = inputs.nth(i)
            if await el.get_attribute("type") in (None, "", "text"):
                target = el
                break
    if target is None:
        raise UpstreamError("no plate input found on page")
    await target.fill(plate)


async def _click_submit(page, text=None):
    if text:
        try:
            await page.get_by_role("button", name=text).first.click(timeout=8000)
            return
        except Exception:
            pass
    for sel in ("button[type=submit]:visible", "input[type=submit]:visible"):
        loc = page.locator(sel)
        if await loc.count():
            await loc.first.click(timeout=8000)
            return
    raise UpstreamError("no submit button found on page")


async def _vic(page, plate, first, last):
    await page.goto(ENTRY["VIC"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    try:
        await page.locator("#RegistrationNumbercar").first.wait_for(state="visible", timeout=15000)
        await page.fill("#RegistrationNumbercar", plate)
    except Exception:
        await _fill_plate(page, plate, state="VIC")
    await _click_submit(page, text="Search")


async def _nsw(page, plate, first, last):
    await page.goto(ENTRY["NSW"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    try:
        link = page.get_by_text("Check online", exact=False).first
        await link.wait_for(state="visible", timeout=15000)
        await link.click()
        await page.wait_for_timeout(3000)
    except Exception:
        pass
    await _fill_plate(page, plate, state="NSW")
    await _click_submit(page)


async def _sa(page, plate, first, last):
    await page.goto(ENTRY["SA"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    await page.locator("#plateNumber").wait_for(state="visible", timeout=BROWSER_TIMEOUT)
    await page.fill("#plateNumber", plate)
    await page.click("#step-1-2-submit", timeout=8000)


async def _nt(page, plate, first, last):
    # first/last name fields on the NT form are hidden honeypots; do not fill them
    await page.goto(ENTRY["NT"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    await page.locator("#rego").wait_for(state="visible", timeout=15000)
    await page.fill("#rego", plate)
    await page.click("#search", timeout=8000)


async def _tas(page, plate, first, last):
    await page.goto(ENTRY["TAS"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    await page.locator("input[name=plate]").first.wait_for(state="visible", timeout=BROWSER_TIMEOUT)
    await page.fill("input[name=plate]", plate)
    await _click_submit(page)


async def _wa(page, plate, first, last):
    await page.goto(ENTRY["WA"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    try:
        el = page.locator("input[title*=plate]").first
        await el.wait_for(state="visible", timeout=15000)
        await el.fill(plate)
    except Exception:
        await _fill_plate(page, plate, state="WA")
    await _click_submit(page)


async def _act(page, plate, first, last):
    await page.goto(ENTRY["ACT"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    await _fill_plate(page, plate, state="ACT")
    await _click_submit(page)


FUNCS = {"VIC": _vic, "NSW": _nsw, "SA": _sa, "NT": _nt, "TAS": _tas, "WA": _wa, "ACT": _act}


async def browser_lookup(plate, state, first_name=None, last_name=None):
    try:
        return await asyncio.wait_for(
            _browser_impl(plate, state, first_name, last_name), timeout=95)
    except asyncio.TimeoutError:
        raise UpstreamError(f"{state}: lookup timed out")


async def _browser_impl(plate, state, first_name=None, last_name=None):
    _t0 = time.time()
    pw = await async_playwright().start()
    browser = None
    ctx = None
    page = None
    try:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage",
                                                 "--disable-blink-features=AutomationControlled"])
        print(f"[browser] {state} launch {time.time() - _t0:.1f}s", flush=True)
        ua, cookies = await asyncio.to_thread(_fsr_prewarm, ENTRY[state])
        print(f"[browser] {state} prewarm {time.time() - _t0:.1f}s cookies={len(cookies)}", flush=True)
        ctx = await browser.new_context(user_agent=ua, locale="en-AU",
                                        viewport={"width": 1280, "height": 900})
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        if cookies:
            try:
                await ctx.add_cookies(cookies)
            except Exception:
                pass
        page = await ctx.new_page()
        await Stealth(navigator_user_agent=False).apply_stealth_async(page)
        await FUNCS[state](page, plate, first_name, last_name)
        print(f"[browser] {state} flow done {time.time() - _t0:.1f}s", flush=True)
        deadline = time.time() + RESULT_TIMEOUT
        challenge_seen = False
        while time.time() < deadline:
            await page.wait_for_timeout(2000)
            try:
                text = await asyncio.wait_for(
                    page.evaluate("() => document.body ? document.body.innerText : ''"),
                    timeout=5)
            except Exception:
                continue
            if _is_challenge(text):
                challenge_seen = True
                continue
            _check_blocked(state, text)
            if _looks_like_not_found(text):
                raise NotFound(plate)
            result = _extract_result(text)
            if any(result.values()):
                try:
                    html = await asyncio.wait_for(page.content(), timeout=5)
                    result = _extract_result(text, html)
                except Exception:
                    pass
                return result
        if challenge_seen:
            raise UpstreamBlocked(f"{state}: bot security verification did not resolve")
        raise UpstreamError(f"{state}: vehicle details could not be retrieved")
    except PWTimeout as e:
        raise UpstreamError(f"{state}: timed out: {e}")
    except UpstreamError:
        raise
    except Exception as e:
        raise UpstreamError(f"{state}: browser lookup failed: {e}")
    finally:
        for closer in (page and page.close, ctx and ctx.close, browser and browser.close):
            if closer:
                try:
                    await asyncio.wait_for(closer(), timeout=10)
                except Exception:
                    pass
        try:
            await asyncio.wait_for(pw.stop(), timeout=10)
        except Exception:
            pass
        print(f"[browser] {state} done {time.time() - _t0:.1f}s", flush=True)
