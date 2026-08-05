import asyncio
import sys
import time

from playwright.async_api import async_playwright, TimeoutError as PWTimeout

from providers import (NotFound, UpstreamBlocked, UpstreamError, _extract_result,
                       _looks_like_not_found)

BROWSER_TIMEOUT = 45000
RESULT_TIMEOUT = 30000

_PLATE_HINTS = ("plate", "rego", "registration", "vehicle number", "number plate")

ENTRY = {
    "VIC": "https://www.vicroads.vic.gov.au/registration/buy-sell-or-transfer-a-vehicle/check-vehicle-registration",
    "NSW": "https://check-registration.service.nsw.gov.au/frc",
    "SA": "https://account.ezyreg.sa.gov.au/account/check-registration.htm",
    "NT": "https://nt.gov.au/driving/rego/existing-nt-registration/rego-check",
    "TAS": "https://transport.stgro-2780.saas.squiz.cloud/rego-status/search",
    "WA": "https://online.transport.wa.gov.au/webExternal/registration",
    "ACT": "https://rego.act.gov.au/regosoawicket/public/reg/FindRegistrationPage?0",
}


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
    for p in ("just a moment", "performing security verification", "you are not a bot",
              "enable javascript and cookies"):
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


async def _has_result(page, plate):
    try:
        txt = await asyncio.wait_for(
            page.evaluate("document.body ? document.body.innerText : ''"), timeout=8)
        html = await asyncio.wait_for(
            page.evaluate(
                "document.documentElement ? document.documentElement.outerHTML : ''"), timeout=8)
    except Exception:
        return False, ""
    if _looks_like_not_found(txt):
        return True, txt
    if plate.lower() not in txt.lower():
        return False, txt
    res = _extract_result(txt, html)
    if any(res.values()):
        return True, txt
    return False, txt


async def _nsw(page, plate, first, last):
    await page.goto(ENTRY["NSW"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    await asyncio.sleep(2)
    try:
        await page.fill("#plateNumberInput", plate)
    except Exception:
        await _fill_plate(page, plate, state="NSW")
    try:
        await page.locator("#termsAndConditions").check(force=True)
    except Exception:
        pass
    for _ in range(3):
        try:
            await page.locator("input[value='Check registration'], button:has-text('Check registration')").first.click(timeout=8000)
        except Exception:
            break
        await asyncio.sleep(3)
        done, _ = await _has_result(page, plate)
        if done:
            break


async def _sa(page, plate, first, last):
    await page.goto(ENTRY["SA"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    await page.locator("#plateNumber").wait_for(state="visible", timeout=BROWSER_TIMEOUT)
    await page.fill("#plateNumber", plate)
    for _ in range(3):
        try:
            await page.click("#step-1-2-submit", timeout=8000)
        except Exception:
            break
        await asyncio.sleep(3)


async def _nt(page, plate, first, last):
    # first/last name fields on the NT form are hidden honeypots; do not fill them
    await page.goto(ENTRY["NT"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    await page.locator("#rego").wait_for(state="visible", timeout=15000)
    await page.fill("#rego", plate)
    await page.click("#search", timeout=8000)


async def _tas(page, plate, first, last):
    await page.goto(ENTRY["TAS"], wait_until="domcontentloaded", timeout=BROWSER_TIMEOUT)
    await asyncio.sleep(2)
    try:
        await page.fill("input[name=plate]", plate)
    except Exception:
        await _fill_plate(page, plate, state="TAS")
    for _ in range(3):
        try:
            await page.locator("button[type=submit], input[type=submit]").first.click(timeout=8000)
        except Exception:
            break
        await asyncio.sleep(3)
        done, _ = await _has_result(page, plate)
        if done:
            break


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
    await asyncio.sleep(2)
    try:
        await page.fill("#plateNumber", plate)
    except Exception:
        await _fill_plate(page, plate, state="ACT")
    try:
        await page.locator("#privacyCheck").check(force=True)
    except Exception:
        pass
    for _ in range(3):
        try:
            await page.locator("input[value*='Next']").first.click(timeout=8000)
        except Exception:
            break
        await asyncio.sleep(3)
        done, _ = await _has_result(page, plate)
        if done:
            break
    try:
        tab = page.get_by_text("Display Details", exact=False).first
        await tab.click(timeout=4000)
        await asyncio.sleep(3)
    except Exception:
        pass


FUNCS = {"VIC": _vic, "NSW": _nsw, "SA": _sa, "NT": _nt, "TAS": _tas, "WA": _wa, "ACT": _act}


async def browser_lookup(plate, state, first_name=None, last_name=None):
    try:
        return await asyncio.wait_for(
            _browser_impl(plate, state, first_name, last_name), timeout=120)
    except asyncio.TimeoutError:
        raise UpstreamError(f"{state}: lookup timed out")


async def _browser_impl(plate, state, first_name=None, last_name=None):
    _t0 = time.time()
    pw = await async_playwright().start()
    browser = None
    ctx = None
    page = None
    try:
        browser = await pw.firefox.launch(args=["--no-sandbox", "--disable-dev-shm-usage",
                                                "--disable-blink-features=AutomationControlled"])
        print(f"[browser] {state} launch {time.time() - _t0:.1f}s", file=sys.stderr, flush=True)
        ctx = await browser.new_context(locale="en-AU",
                                        viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        await FUNCS[state](page, plate, first_name, last_name)
        print(f"[browser] {state} flow done {time.time() - _t0:.1f}s", file=sys.stderr, flush=True)
        deadline = time.time() + RESULT_TIMEOUT / 1000
        challenge_seen = False
        while time.time() < deadline:
            await asyncio.sleep(2)
            try:
                text = await asyncio.wait_for(
                    page.evaluate("document.body ? document.body.innerText : ''"), timeout=10)
            except Exception:
                continue
            if _is_challenge(text):
                challenge_seen = True
                continue
            _check_blocked(state, text)
            if _looks_like_not_found(text):
                raise NotFound(plate)
            try:
                html = await asyncio.wait_for(
                    page.evaluate(
                        "document.documentElement ? document.documentElement.outerHTML : ''"),
                    timeout=10)
            except Exception:
                html = None
            result = _extract_result(text, html)
            if any(result.values()):
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
        print(f"[browser] {state} done {time.time() - _t0:.1f}s", file=sys.stderr, flush=True)
