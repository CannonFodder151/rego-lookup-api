import os
import re
import time

import setuptools  # noqa: F401  (distutils shim for undetected-chromedriver on py3.12)

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from providers import (NotFound, UpstreamBlocked, UpstreamError, _extract_result,
                       _looks_like_not_found)

VIC_URL = ("https://www.vicroads.vic.gov.au/registration/buy-sell-or-transfer-a-vehicle/"
           "check-vehicle-registration/vehicle-registration-enquiry/")

RESULT_TIMEOUT = 60


def _ensure_display():
    # Xvfb is started once by the container entrypoint on :99
    os.environ.setdefault("DISPLAY", ":99")


def _driver():
    import undetected_chromedriver as uc
    _ensure_display()
    opts = uc.ChromeOptions()
    for arg in ("--no-sandbox", "--disable-dev-shm-usage", "--window-size=1280,900",
                "--disable-blink-features=AutomationControlled"):
        opts.add_argument(arg)
    return uc.Chrome(options=opts, headless=False)


def _is_challenge(text):
    t = text.lower()
    for p in ("just a moment", "security verification", "you are not a bot",
              "checking your browser", "cloudflare", "enable javascript"):
        if p in t:
            return True
    return False


def _dismiss_banners(driver):
    try:
        for b in driver.find_elements(By.CSS_SELECTOR, "button"):
            if (b.text or "").strip().lower() == "ok":
                b.click()
                break
    except Exception:
        pass


def _find_search_button(driver):
    for sel in ("input[type=submit][value='Search']", "input[type=submit]",
                "button[type=submit]", "button"):
        for cand in driver.find_elements(By.CSS_SELECTOR, sel):
            label = ((cand.get_attribute("value") or "") + " " + (cand.text or "")).strip()
            try:
                if cand.is_displayed() and ("search" in label.lower() or sel == "input[type=submit]"):
                    return cand
            except Exception:
                continue
    return None


def uc_lookup(plate, state):
    driver = _driver()
    try:
        driver.get(VIC_URL)
        time.sleep(4)
        _dismiss_banners(driver)
        wait = WebDriverWait(driver, 25)
        try:
            field = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#RegistrationNumbercar")))
            field.click()
            field.send_keys(plate)
        except Exception:
            raise UpstreamError("VIC: registration number field could not be filled")
        btn = _find_search_button(driver)
        if btn is None:
            try:
                btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(normalize-space(.), 'Search')]")))
            except Exception:
                raise UpstreamError("VIC: search button could not be found")
        try:
            btn.click()
        except Exception:
            raise UpstreamError("VIC: search button could not be clicked")
        deadline = time.time() + RESULT_TIMEOUT
        while time.time() < deadline:
            time.sleep(2)
            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")
            text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
            if _is_challenge(text):
                raise UpstreamBlocked("VIC: bot security verification did not resolve")
            if _looks_like_not_found(text):
                raise NotFound(plate)
            result = _extract_result(text, html)
            if any(result.values()):
                return result
        raise UpstreamError("VIC: vehicle details could not be retrieved")
    except (NotFound, UpstreamBlocked, UpstreamError):
        raise
    except Exception as e:
        raise UpstreamError(f"VIC: browser automation failed: {e}")
    finally:
        try:
            driver.quit()
        except Exception:
            pass
