import sys, time, re, json
sys.path.insert(0, ".")
from undetected import _driver, _dismiss_banners, _flow_vic, STATE_URLS
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup

driver = _driver()
try:
    driver.get(STATE_URLS["VIC"])
    time.sleep(5)
    _dismiss_banners(driver)
    _flow_vic(driver, "FZR60", WebDriverWait(driver, 25), "motorcycle")
    print("=== flow done, polling ===", flush=True)
    for i in range(15):
        time.sleep(3)
        try:
            html = driver.execute_script(
                "return document.documentElement ? document.documentElement.outerHTML : ''")
        except Exception as e:
            print(f"poll {i} exec err: {e}", flush=True)
            continue
        text = re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ", strip=True))
        print(f"--- poll {i} ({len(text)} chars) ---", flush=True)
        print(text[:1200], flush=True)
        j = text.find("Vehicle type")
        if j >= 0:
            print("FORM:", text[j:j+500], flush=True)
        for kw in ("error", "required", "valid", "not found", "not registered"):
            k = text.lower().find(kw)
            if k >= 0:
                print(f"HIT[{kw}]:", text[max(0,k-120):k+180], flush=True)
        driver.save_screenshot(f"poll{i}.png")
except Exception as e:
    print("ERR:", type(e).__name__, str(e)[:400], flush=True)
finally:
    try:
        driver.quit()
    except Exception:
        pass
