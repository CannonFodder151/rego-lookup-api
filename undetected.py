import os
import re
import sys
import time

import setuptools  # noqa: F401  (distutils shim for undetected-chromedriver on py3.12)

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from providers import (NotFound, UpstreamBlocked, UpstreamError, _extract_result,
                       _looks_like_not_found)

RESULT_TIMEOUT = 60

STATE_URLS = {
    "VIC": ("https://www.vicroads.vic.gov.au/registration/buy-sell-or-transfer-a-vehicle/"
            "check-vehicle-registration/vehicle-registration-enquiry/"),
    "NSW": "https://check-registration.service.nsw.gov.au/frc",
    "SA": "https://account.ezyreg.sa.gov.au/account/check-registration.htm",
    "TAS": "https://transport.stgro-2780.saas.squiz.cloud/rego-status/search",
    "ACT": "https://rego.act.gov.au/regosoawicket/public/reg/FindRegistrationPage?0",
}


def _ensure_display():
    # Xvfb is started once by the container entrypoint on :99
    os.environ.setdefault("DISPLAY", ":99")


def _driver():
    import undetected_chromedriver as uc
    _ensure_display()
    opts = uc.ChromeOptions()
    for arg in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1280,900",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu", "--disable-software-rasterizer"):
        opts.add_argument(arg)
    print("uc: launching Chrome", file=sys.stderr, flush=True)
    return uc.Chrome(options=opts, headless=False)


def _is_challenge(text):
    t = text.lower()
    for p in ("just a moment", "performing security verification", "you are not a bot",
              "enable javascript and cookies"):
        if p in t:
            return True
    return False


def _displayed(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def _dismiss_banners(driver):
    for _ in range(3):
        clicked = False
        try:
            for b in driver.find_elements(By.CSS_SELECTOR, "button"):
                t = (b.text or "").strip().lower()
                if any(w in t for w in ("ok", "accept", "agree", "consent", "allow")) and _displayed(b):
                    try:
                        b.click()
                    except Exception:
                        driver.execute_script("arguments[0].click()", b)
                    clicked = True
        except Exception:
            pass
        if not clicked:
            break
        time.sleep(1)


def _click(driver, el):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.3)
    except Exception:
        pass
    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click()", el)


def _fill_plate(driver, plate, selector=None):
    if selector:
        el = driver.find_element(By.CSS_SELECTOR, selector)
        _click(driver, el)
        el.send_keys(plate)
        return
    for inp in driver.find_elements(By.CSS_SELECTOR,
                                    "input[type=text], input:not([type]), input[type=number]"):
        if not _displayed(inp):
            continue
        ctx = " ".join((inp.get_attribute(a) or "") for a in
                       ("placeholder", "title", "name", "id")).lower()
        if any(h in ctx for h in ("plate", "rego", "registration", "vehicle number", "number")):
            _click(driver, inp)
            inp.send_keys(plate)
            return
    raise UpstreamError("no plate input found on page")


def _find_submit(driver, labels=()):
    for sel in ("button", "input[type=submit]", "input[type=button]"):
        for el in driver.find_elements(By.CSS_SELECTOR, sel):
            if not _displayed(el):
                continue
            t = ((el.get_attribute("value") or "") + " " + (el.text or "")).lower()
            if not labels or any(l in t for l in labels):
                return el
    return None


def _click_visible(driver, text_substr):
    for el in driver.find_elements(By.XPATH, "//button | //a"):
        if text_substr in (el.text or "").lower() and _displayed(el):
            _click(driver, el)
            return True
    return False


def _solve_recaptcha_v2(driver):
    for fr in driver.find_elements(By.CSS_SELECTOR, "iframe[src*='recaptcha']"):
        try:
            driver.switch_to.frame(fr)
            anchor = driver.find_element(By.CSS_SELECTOR, "#recaptcha-anchor")
            if "recaptcha-checkbox-checked" not in (anchor.get_attribute("class") or ""):
                _click(driver, anchor)
                time.sleep(3)
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()


def _flow_vic(driver, plate, wait, vehicle_type="car"):
    # Vicroads has separate registration fields for car vs motorcycle.
    selector = ("#RegistrationNumbermotorcycle" if vehicle_type == "motorcycle"
                else "#RegistrationNumbercar")
    field = None
    try:
        field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
    except Exception:
        field = None
    if field is None:
        # The type input may be hidden until its radio/label is selected.
        for el in driver.find_elements(By.CSS_SELECTOR, "label, button, a, span, input[type=radio]"):
            t = ((el.get_attribute("value") or "") + " " + (el.text or "")).strip().lower()
            if t and vehicle_type in t and _displayed(el):
                try:
                    _click(driver, el)
                except Exception:
                    pass
        try:
            field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
        except Exception:
            field = None
    if field is None:
        _fill_plate(driver, plate)
        field = None
        for inp in driver.find_elements(By.CSS_SELECTOR,
                                        "input[type=text], input:not([type]), input[type=number]"):
            if _displayed(inp):
                field = inp
                break
        if field is not None:
            _click(driver, field)
            field.send_keys(plate)
    else:
        _click(driver, field)
        field.send_keys(plate)
    btn = _find_submit(driver, labels=("search",))
    if btn is None:
        raise UpstreamError("VIC: search button not found")
    _click(driver, btn)


def _flow_nsw(driver, plate, wait, vehicle_type='car'):
    try:
        field = driver.find_element(By.CSS_SELECTOR, "#plateNumberInput")
        _click(driver, field)
        field.send_keys(plate)
    except Exception:
        _fill_plate(driver, plate)
    for _ in range(5):
        for cb in driver.find_elements(By.CSS_SELECTOR, "input[type=checkbox]"):
            try:
                if not cb.is_selected():
                    _click(driver, cb)
            except Exception:
                pass
        _solve_recaptcha_v2(driver)
        btn = _find_submit(driver, labels=("check registration", "check", "search", "submit", "continue", "look up"))
        if btn is None:
            break
        _click(driver, btn)
        time.sleep(3)
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])


def _flow_sa(driver, plate, wait, vehicle_type='car'):
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#plateNumber")))
    field = driver.find_element(By.CSS_SELECTOR, "#plateNumber")
    _click(driver, field)
    field.send_keys(plate)
    _click(driver, driver.find_element(By.CSS_SELECTOR, "#step-1-2-submit"))


def _flow_tas(driver, plate, wait, vehicle_type='car'):
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name=plate]")))
    field = driver.find_element(By.CSS_SELECTOR, "input[name=plate]")
    _click(driver, field)
    field.send_keys(plate)
    btn = _find_submit(driver, labels=("search", "check", "submit"))
    if btn is None:
        raise UpstreamError("TAS: submit button not found")
    _click(driver, btn)


def _flow_act(driver, plate, wait, vehicle_type='car'):
    try:
        field = driver.find_element(By.CSS_SELECTOR, "#plateNumber")
        _click(driver, field)
        field.send_keys(plate)
    except Exception:
        _fill_plate(driver, plate)
    for cb in driver.find_elements(By.CSS_SELECTOR, "input[type=checkbox]"):
        try:
            if not cb.is_selected():
                _click(driver, cb)
        except Exception:
            pass
    btn = _find_submit(driver, labels=("next", "search", "check", "submit", "continue", "look up"))
    if btn is None:
        raise UpstreamError("ACT: submit button not found")
    _click(driver, btn)


FLOWS = {"VIC": _flow_vic, "NSW": _flow_nsw, "SA": _flow_sa, "TAS": _flow_tas, "ACT": _flow_act}


def uc_lookup(plate, state, vehicle_type="car"):
    driver = _driver()
    try:
        print("uc: driver created, navigating", file=sys.stderr, flush=True)
        driver.get(STATE_URLS[state])
        print("uc: navigated, waiting", file=sys.stderr, flush=True)
        time.sleep(4)
        _dismiss_banners(driver)
        wait = WebDriverWait(driver, 25)
        FLOWS[state](driver, plate, wait, vehicle_type)
        deadline = time.time() + RESULT_TIMEOUT
        while time.time() < deadline:
            time.sleep(2)
            html = driver.execute_script(
                "return document.documentElement ? document.documentElement.outerHTML : ''")
            soup = BeautifulSoup(html, "html.parser")
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            if _is_challenge(text):
                raise UpstreamBlocked(f"{state}: bot security verification did not resolve")
            if _looks_like_not_found(text):
                raise NotFound(plate)
            result = _extract_result(text, html)
            if any(result.values()):
                return result
        raise UpstreamError(f"{state}: vehicle details could not be retrieved")
    except (NotFound, UpstreamBlocked, UpstreamError):
        raise
    except Exception as e:
        raise UpstreamError(f"{state}: browser automation failed: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
