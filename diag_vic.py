import sys, time, json
sys.path.insert(0, ".")
from undetected import _driver, _dismiss_banners, STATE_URLS
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

driver = _driver()
try:
    driver.get(STATE_URLS["VIC"])
    time.sleep(5)
    _dismiss_banners(driver)
    vt = driver.find_elements(By.CSS_SELECTOR, "#VehicleType")
    print("VehicleType found:", bool(vt))
    if vt:
        sel = Select(vt[0])
        print("VehicleType current:", sel.first_selected_option.get_attribute("value"))
        print("VehicleType options:", [o.get_attribute("value") for o in sel.options])
        sel.select_by_value("motorcycle")
        time.sleep(3)
        print("after select, VehicleType value:", sel.first_selected_option.get_attribute("value"))
    for fid in ("RegistrationNumbercar", "Registration-Number-motorcycle", "Registration-Number-caravan"):
        els = driver.find_elements(By.CSS_SELECTOR, "#" + fid)
        if els:
            e = els[0]
            print(f"{fid}: exists, displayed={e.is_displayed()}, size={e.size}, enabled={e.is_enabled()}")
        else:
            print(f"{fid}: NOT FOUND")
    html = driver.execute_script("return document.documentElement ? document.documentElement.outerHTML : ''")
    open("diag_vic.html", "w").write(html)
    driver.save_screenshot("diag_vic.png")
    print("saved diag_vic.html + diag_vic.png")
except Exception as e:
    print("DIAG ERROR:", type(e).__name__, str(e)[:300])
finally:
    try:
        driver.quit()
    except Exception:
        pass
