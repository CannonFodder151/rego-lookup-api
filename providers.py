import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import textwrap

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

STATES = {"VIC", "NSW", "QLD", "WA", "SA", "NT", "TAS", "ACT"}

BROWSER_STATES = {"VIC", "NSW", "WA", "SA", "NT", "TAS", "ACT"}

UC_STATES = {"VIC"}

_FIELDS = {
    "vin": r"\b(?:VIN|Vehicle Identification Number|Chassis\s*(?:number)?)\b[:\s]*([A-Z0-9]{4,17})",
    "make": r"\bMake\b[:\s]*([A-Za-z][A-Za-z .'\-]*?)(?=\s+(?:Model|Year|Colour|Color|Body|VIN|Vin|Status|Expiry|Odometer|Serial|Registration|Variant)\b|\s*$)",
    "model": r"\bModel\b[:\s]*([A-Za-z0-9][A-Za-z0-9 .\-/]*?)(?=\s+(?:Year|Make|Colour|Color|Body|VIN|Vin|Status|Expiry|Odometer)\b|\s*$)",
    "year": r"\b(?:Year\s*(?:of|by)?\s*(?:manufacture|built|first|model)?|Date of manufacture)\b[:\s]*([0-9]{4})",
    "colour": r"\bColou?r\b[:\s]*([A-Za-z][A-Za-z \-]*?)(?=\s+(?:CTP|Insurer|Model|Make|Body|Year|VIN|Vin|Status|Expiry|Odometer|Compliance)\b|\s*$)",
    "body_type": r"\bBody\s*(?:type|shape)?\b(?!type\b|shape\b)[:\s]*([A-Za-z][A-Za-z0-9 .\-/]*?)(?=\s+(?:State|Status|Model|Make|Year|Colour|Color|VIN|Vin|Expiry)\b|\s*$)",
}


class UpstreamError(Exception):
    pass


class UpstreamBlocked(UpstreamError):
    pass


class NotFound(UpstreamError):
    pass


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "en-AU,en;q=0.9"})
    return s


_LABEL_WORDS = {"number", "chassis", "vin", "make", "model", "colour", "color", "body",
                "year", "type", "vehicle", "registration", "search", "searching", "value",
                "field", "required", "vehicle identification number"}

_LABELS = {
    "vin": ("vin", "vehicle identification number", "chassis", "chassis number", "vin number"),
    "make": ("make", "vehicle make", "description"),
    "model": ("model", "vehicle model"),
    "year": ("year", "year of manufacture", "year first registered", "date of manufacture",
             "model year", "first registered", "year first registered"),
    "colour": ("colour", "color", "vehicle colour", "vehicle color"),
    "body_type": ("body type", "body shape", "body", "body style"),
}

_BODY_WORDS = {"wagon", "sedan", "hatchback", "hatch", "coupe", "ute", "utility", "truck",
               "suv", "van", "bus", "motorcycle", "scooter", "caravan", "trailer", "roadster",
               "convertible", "limousine", "pickup", "stationwagon", "mpv", "vanlight"}

# Known vehicle makes registered in Australia. VIC's rego report shows Make and
# Model combined in a single "Make" row (e.g. "YAMAHA FZ6S"), so we match the
# longest make name as a prefix and treat the remainder as the model.
_VEHICLE_MAKES = frozenset(textwrap.dedent("""
    ABARTH
    AC
    ACURA
    ADLY
    AERO
    AIYING
    AJP
    ALFA ROMEO
    ALPINA
    AM GENERAL
    AMERICAN MOTORS
    APRILIA
    ARIEL
    ASHOK LEYLAND
    ASIA
    ASTON MARTIN
    ATC
    ATLAS
    AUDI
    AUSTIN
    AUSTIN HEALEY
    AUVERLAND
    AVANTI
    BAJAJ
    BAIC
    BAJA
    BEACH BUGGY
    BEDFORD
    BEIJING
    BENELLI
    BENTLEY
    BERGER
    BESTA
    BIMOTA
    BLAZE
    BLUEBIRD
    BMW
    BOXER
    BRABUS
    BRILLIANCE
    BUICK
    BUFFALO
    BUGATTI
    BULTACO
    BYD
    CADILLAC
    CALF
    CAN-AM
    CAPRI
    CCM
    CHANA
    CHANGAN
    CHERY
    CHEVROLET
    CHRYSLER
    CITROEN
    CLARK
    CLASSIC
    COACH
    CODY
    CORVETTE
    CUB
    CUSTOM
    DAF
    DAIHATSU
    DAIQU
    DODGE
    DONGFENG
    DUCATI
    EAGLE
    EGO
    ELECTRIC
    EXCALIBUR
    FAW
    FERRARI
    FIAT
    FISKER
    FLYBO
    FORD
    FORD TRUCKS
    FOTON
    FRASER
    FUJI
    GAS GAS
    GEELY
    GENERAL MOTORS
    GENESIS
    GILERA
    GINETTA
    GLAS
    GMC
    GREAT WALL
    GRINNALL
    HAFEI
    HANOMAG
    HARLEY-DAVIDSON
    HAWK
    HEARTLAND
    HERO
    HILLMAN
    HINDUSTAN
    HOLDEN
    HONDA
    HUMMER
    HYOSUNG
    HYUNDAI
    INFINITI
    INNOCENTI
    INTERNATIONAL
    ISUZU
    IVECO
    JAC
    JAGUAR
    JEEP
    JENSEN
    JINCHENG
    JIANGSU
    JOHNSON
    KAIYI
    KAMA
    KARMA
    KAWASAKI
    KIA
    KINGWAY
    KOENIGSEGG
    LADA
    LAMBRETTA
    LAMBORGHINI
    LANCIA
    LAND ROVER
    LEYLAND
    LIFAN
    LINCOLN
    LINGBEN
    LLOYD
    LOTEC
    LOTUS
    MACK
    MADAMO
    MAGIRUS
    MAHINDRA
    MALAGUTI
    MAN
    MASERATI
    MASTERS
    MAXUS
    MAYBACH
    MAZDA
    MCLAREN
    MEGELLI
    MERCEDES-BENZ
    MERCEDES BENZ
    MERCURY
    MG
    MIDAS
    MINI
    MITSUBISHI
    MONTESA
    MORGAN
    MOTOBECANE
    MOTO-GUZZI
    MOTOR
    MOWAG
    MZ
    NISSAN
    NSU
    OLDSMOBILE
    OPEL
    OSCA
    OSSA
    PANHARD
    PEERLESS
    PEGASO
    PEUGEOT
    PIAGGIO
    PLYMOUTH
    PONTIAC
    PORSCHE
    PRESTIGE
    PROTON
    PUMA
    QIJIANG
    RANGE ROVER
    RELIANT
    RENAULT
    RIDLEY
    RIEJU
    RIVA
    ROLLS-ROYCE
    ROVER
    ROYAL ENFIELD
    SAAB
    SANTANA
    SEAT
    SETRA
    SHANGHAI
    SHINERAY
    SIMCA
    SINGER
    SKODA
    SKYGO
    SMART
    SSANGYONG
    STEYR
    SUBARU
    SUZUKI
    SYM
    TATA
    TESLA
    TIGER
    TOYOTA
    TRIUMPH
    TVS
    URAL
    VAUXHALL
    VELOCETTE
    VESPA
    VOLKSWAGEN
    VOLVO
    WARTBURG
    WESTFIELD
    WILLYS
    XINLING
    YAMAHA
    ZENN
    ZIL
    ZONGSHEN
    ZX AUTO
""").strip().splitlines())


def _split_make_model(val):
    """Split a combined 'MAKE MODEL' string; returns (make, model)."""
    tokens = val.split()
    if len(tokens) < 2:
        return val, None
    for i in range(len(tokens), 0, -1):
        if " ".join(tokens[:i]).upper() in _VEHICLE_MAKES:
            return " ".join(tokens[:i]), " ".join(tokens[i:]) or None
    return " ".join(tokens[:-1]), tokens[-1]


def _parse_description(out):
    val = out["make"]
    m = re.match(r"(\d{4})\s+(.+)", val)
    if m:
        out["year"] = int(m.group(1))
        val = m.group(2)
    parts = val.rsplit(None, 1)
    if len(parts) == 2 and parts[1].lower().replace(" ", "") in _BODY_WORDS:
        out["body_type"] = parts[1]
        val = parts[0]
    parts = val.rsplit(None, 1)
    if len(parts) == 2:
        out["make"] = parts[0]
        out["model"] = parts[1]
    else:
        out["make"] = val


def _value_after(el):
    parent = el.parent
    if parent is None:
        return None
    kids = [c for c in parent.children if getattr(c, "name", None)]
    try:
        idx = kids.index(el)
    except ValueError:
        return None
    for nxt in kids[idx + 1:]:
        txt = re.sub(r"\s+", " ", nxt.get_text(" ", strip=True)).strip()
        if txt:
            return txt
    return None


def _table_value(el):
    parent = el.parent
    if parent is not None and parent.name == "tr":
        cells = parent.find_all(["td", "th"])
        try:
            idx = cells.index(el)
        except ValueError:
            idx = None
        if idx is not None:
            nxt_tr = parent.find_next_sibling("tr")
            if nxt_tr is None:
                tbl = parent.find_parent("table")
                if tbl is not None:
                    tbody = tbl.find("tbody")
                    if tbody is not None:
                        nxt_tr = tbody.find("tr")
            if nxt_tr is not None:
                nxt_cells = nxt_tr.find_all(["td", "th"])
                if len(nxt_cells) > len(cells):
                    nxt_cells = nxt_cells[len(nxt_cells) - len(cells):]
                if idx < len(nxt_cells):
                    txt = re.sub(r"\s+", " ", nxt_cells[idx].get_text(" ", strip=True)).strip()
                    if txt:
                        return txt
    return _value_after(el)


def _extract_dom(soup):
    out = {"vin": None, "make": None, "model": None, "year": None, "colour": None, "body_type": None}
    make_label = None
    for field, names in _LABELS.items():
        for el in soup.find_all(True):
            t = re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip().lower()
            t = re.sub(r"\(.*?\)", " ", t)
            t = re.sub(r"\s+", " ", t).strip().rstrip(":").rstrip(".")
            if t in names:
                val = _table_value(el)
                if val and val.lower() not in _LABEL_WORDS:
                    if field == "year":
                        m = re.search(r"\d{4}", val)
                        if m:
                            out[field] = int(m.group(0))
                    else:
                        out[field] = val
                        if field == "make":
                            make_label = t
                break
    if out["make"]:
        if make_label == "description":
            _parse_description(out)
        elif not out["year"]:
            m = re.match(r"(\d{4})\s+(.+)", out["make"])
            if m:
                out["year"] = int(m.group(1))
                out["make"] = m.group(2)
    if not out["make"]:
        for cell in soup.find_all(["th", "td"]):
            if re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip().lower() == "vehicle":
                val = _table_value(cell)
                if val and val.lower() not in _LABEL_WORDS:
                    out["make"] = val
                    if not out["year"]:
                        m = re.match(r"(\d{4})\s+(.+)", val)
                        if m:
                            out["year"] = int(m.group(1))
                            out["make"] = m.group(2)
                break
    return out


def _extract_result(text, html=None):
    result = _extract_text(text)
    if html:
        dom = _extract_dom(BeautifulSoup(html, "html.parser"))
        for k in result:
            if dom.get(k):
                result[k] = dom[k]
    # Some states (notably VIC) report Make and Model combined in the Make
    # field, e.g. "YAMAHA FZ6S". Split it into the two fields when no separate
    # model was found.
    if result["make"] and not result["model"]:
        result["make"], result["model"] = _split_make_model(result["make"])
    return result


def _extract_text(text):
    text = re.sub(r"\s+", " ", text)
    out = {"vin": None, "make": None, "model": None, "year": None, "colour": None, "body_type": None}
    for key, pat in _FIELDS.items():
        m = re.search(pat, text, re.I)
        if m:
            val = m.group(1).strip()
            if key == "year":
                out[key] = int(val)
            elif val.lower() not in _LABEL_WORDS and len(val) >= 2:
                out[key] = val
    return out


_NOT_FOUND_PHRASES = ("registration not found", "no registration details", "no vehicle registration",
                      "not currently registered", "registration number not found", "no record of this",
                      "cannot be found", "is not registered", "no registration found", "not registered",
                      "no vehicles match", "must enter a valid registration", "no matches found",
                      "no results found", "does not exist", "not recognised", "not recognized",
                      "no vehicle found", "no vehicles found", "not currently assigned",
                      "no matching registration", "no matching", "no results")


def _looks_like_not_found(text):
    t = text.lower()
    return any(p in t for p in _NOT_FOUND_PHRASES)


def _extract(soup, scope=None):
    node = soup
    if scope is not None:
        node = scope
    return _extract_text(node.get_text(" ", strip=True))


# ---------------------------------------------------------------- QLD

QLD_BASE = "https://www.service.transport.qld.gov.au"
QLD_ENTRY = QLD_BASE + "/checkrego/public/Welcome.xhtml"


def _qld_form(soup, form_id):
    form = soup.find("form", {"id": form_id})
    if form is None:
        raise UpstreamError(f"QLD: form {form_id} not found on page")
    return form


def _qld_button_value(soup, button_id):
    btn = soup.find("button", {"id": button_id})
    return btn.get_text(strip=True) if btn else "Continue"


def _qld_post(s, form, button_id, extra=None):
    action = form.get("action", "")
    if not action.startswith("http"):
        action = QLD_BASE + action
    data = {}
    for inp in form.select("input[type=hidden]"):
        n, v = inp.get("name"), inp.get("value", "")
        if n:
            data[n] = v
    data["javax.faces.source"] = button_id
    data[button_id] = _qld_button_value(form, button_id)
    if extra:
        data.update(extra)
    r = s.post(action, data=data, timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def qld_lookup(plate):
    s = _session()
    soup = BeautifulSoup(s.get(QLD_ENTRY, timeout=30).text, "html.parser")
    soup = _qld_post(s, _qld_form(soup, "checkRegoAboutThisService:aboutThisServiceForm"),
                     "checkRegoAboutThisService:aboutThisServiceForm:continueButton")
    soup = _qld_post(s, _qld_form(soup, "tAndCForm"), "tAndCForm:confirmButton")
    form = _qld_form(soup, "vehicleSearchForm")
    soup = _qld_post(s, form, "vehicleSearchForm:confirmButton",
                     {"vehicleSearchForm:plateNumber": plate})
    text = soup.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    if re.search(r"registration\s+number:\s*registration\s+not\s+found", text, re.I):
        raise NotFound(plate)
    result = _extract_result(text, str(soup))
    return result


# ---------------------------------------------------------------- WA

WA_ENTRY = "https://online.transport.wa.gov.au/webExternal/registration"


def wa_lookup(plate):
    s = _session()
    r = s.get(WA_ENTRY, allow_redirects=True, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form", {"name": "registrationRequestForm"})
    if form is None:
        raise UpstreamBlocked("WA: registration form could not be reached")
    m = re.search(r"\?(\d+)-", form.get("action", ""))
    ver = m.group(1) if m else "1"
    hf = {}
    for inp in form.select("input[type=hidden]"):
        n = inp.get("name")
        if n and re.match(r"^id\d+_hf_\d+$", n):
            hf[n] = inp.get("value", "")
    ajax = f"./?{ver}.IBehaviorListener.1-layout-layout_body-registrationRequestForm-searchButton"
    data = dict(hf)
    data["plateField"] = plate
    data["searchButton"] = ""
    data["wicket-ajax"] = "true"
    data["wicket-ajax-baseurl"] = "/webExternal/registration"
    headers = {"Wicket-Ajax": "true", "X-Requested-With": "XMLHttpRequest"}
    r = s.post(requests.compat.urljoin(r.url, ajax), data=data, headers=headers, timeout=30)
    m = re.search(r"<redirect><!\[CDATA\[([^\]]+)\]\]></redirect>", r.text)
    if not m:
        raise UpstreamError("WA: unexpected response from search")
    r = s.get(requests.compat.urljoin(WA_ENTRY, m.group(1)), timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")
    scope = soup.find("div", class_="section-body")
    if scope is None:
        raise UpstreamError("WA: vehicle details could not be retrieved")
    text = re.sub(r"\s+", " ", scope.get_text(" ", strip=True))
    if re.search(r"no registration details", text, re.I):
        raise NotFound(plate)
    result = _extract(soup, scope)
    if not any(result.values()):
        raise UpstreamError("WA: vehicle details could not be retrieved")
    return result


# ---------------------------------------------------------------- blocked states

def _blocked(state, why):
    def _f(plate):
        raise UpstreamBlocked(f"{state}: lookup requires browser automation ({why}). "
                              "Plain HTTP is blocked by the state site.")
    return _f


PROVIDERS = {
    "QLD": qld_lookup,
    "WA": wa_lookup,
    "VIC": _blocked("VIC", "Cloudflare managed challenge on vicroads.vic.gov.au"),
    "NSW": _blocked("NSW", "check form is injected client-side on service.nsw.gov.au"),
    "SA": _blocked("SA", "JS single-page app + AU-IP geo-block on ezyreg.sa.gov.au"),
    "NT": _blocked("NT", "Cloudflare managed challenge on nt.gov.au"),
    "TAS": _blocked("TAS", "reCAPTCHA v3 + Cloudflare on transport.stgro-2780.saas.squiz.cloud"),
    "ACT": _blocked("ACT", "JS-rendered check on accesscanberra.act.gov.au"),
}


def _fsr_configured():
    return bool((os.getenv("FLARESOLVERR_URL") or "").strip())


def _browser_enabled():
    return os.getenv("PLAYWRIGHT", "0") == "1" or _fsr_configured()


_BROWSER_MAX_CONCURRENCY = max(1, int(os.getenv("BROWSER_MAX_CONCURRENCY", "2")))
_BROWSER_SEM = asyncio.Semaphore(_BROWSER_MAX_CONCURRENCY)


async def _run_browser(plate, state, first_name, last_name):
    # Playwright work runs in a subprocess: fresh process = reliable timeouts,
    # whereas in-process Playwright inside uvicorn's event loop hangs on native timeouts.
    # The semaphore caps how many browser subprocesses can run at once (each
    # takes tens of seconds and hits an upstream state site).
    async with _BROWSER_SEM:
        return await _run_browser_inner(plate, state, first_name, last_name)


async def _run_browser_inner(plate, state, first_name, last_name):
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "runner.py"), plate, state]
    if first_name:
        cmd.append(first_name)
    if last_name:
        cmd.append(last_name)
    try:
        cp = await asyncio.to_thread(
            subprocess.run, cmd, stdout=subprocess.PIPE, stderr=None, text=True, timeout=140)
    except subprocess.TimeoutExpired as e:
        partial = (e.stdout or "")[-300:] if isinstance(e.stdout, str) else \
            (e.stdout or b"").decode(errors="replace")[-300:]
        raise UpstreamError(f"{state}: lookup timed out (worker: {partial})")
    stdout = (cp.stdout or "").strip()
    try:
        data = json.loads(stdout.splitlines()[-1])
    except Exception:
        raise UpstreamError(f"{state}: browser worker failed: {(cp.stderr or stdout)[:200]}")
    if data.get("ok"):
        return data["result"]
    kind = data.get("kind")
    if kind == "notfound":
        raise NotFound(plate)
    if kind == "blocked":
        raise UpstreamBlocked(data.get("message") or f"{state}: blocked")
    raise UpstreamError(data.get("message") or f"{state}: failed")


async def _run_uc(plate, state, vehicle_type="car"):
    """undetected_chromedriver work runs in a killable subprocess (own process
    group) so a hung Chrome/chromedriver is reaped instead of leaking."""
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "uc_worker.py"),
           plate, state, vehicle_type]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, start_new_session=True)
    try:
        stdout, _ = await asyncio.to_thread(proc.communicate, timeout=90)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        await asyncio.to_thread(proc.wait)
        raise UpstreamError(f"{state}: lookup timed out")
    stdout = (stdout or "").strip()
    try:
        data = json.loads(stdout.splitlines()[-1])
    except Exception:
        raise UpstreamError(f"{state}: uc worker failed: {stdout[:200]}")
    if data.get("ok"):
        return data["result"]
    kind = data.get("kind")
    if kind == "notfound":
        raise NotFound(plate)
    if kind == "blocked":
        raise UpstreamBlocked(data.get("message") or f"{state}: blocked")
    raise UpstreamError(data.get("message") or f"{state}: failed")


_UC_LOCK = asyncio.Lock()


def _uc_enabled():
    return os.getenv("UNDETECTED", "0") == "1"


async def lookup(plate, state, first_name=None, last_name=None, vehicle_type="car"):
    if state in UC_STATES and _uc_enabled():
        async with _UC_LOCK:
            try:
                result = await _run_uc(plate, state, vehicle_type)
            except ImportError:
                result = None
            except UpstreamError as exc:
                if isinstance(exc, (NotFound, UpstreamBlocked)):
                    raise
                # Transient Chrome/session hang — retry once before giving up.
                result = await _run_uc(plate, state, vehicle_type)
        if result is not None:
            result.update({"plate": plate, "state": state})
            return result
    if state in BROWSER_STATES and _browser_enabled():
        result = await _run_browser(plate, state, first_name, last_name)
        result.update({"plate": plate, "state": state})
        return result
    provider = PROVIDERS[state]
    result = await asyncio.to_thread(provider, plate)
    result.update({"plate": plate, "state": state})
    return result
