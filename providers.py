import re

import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)

STATES = {"VIC", "NSW", "QLD", "WA", "SA", "NT", "TAS"}

_FIELDS = {
    "vin": r"\bVIN\b[:\s]*([A-Z0-9]{6,17})",
    "make": r"\bMake\b[:\s]*([A-Za-z][A-Za-z .'\-]{1,30})",
    "model": r"\bModel\b[:\s]*([A-Za-z0-9][A-Za-z0-9 .\-/]{1,40})",
    "year": r"\b(?:Year\s*(?:of|by)?\s*(?:manufacture|built|first|model)?|Date of manufacture)\b[:\s]*([0-9]{4})",
    "colour": r"\bColou?r\b[:\s]*([A-Za-z][A-Za-z \-]{1,25})",
    "body_type": r"\bBody\s*(?:type|shape)?\b[:\s]*([A-Za-z][A-Za-z0-9 .\-/]{1,25})",
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


def _extract(soup, scope=None):
    node = soup
    if scope is not None:
        node = scope
    text = node.get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    out = {"vin": None, "make": None, "model": None, "year": None, "colour": None, "body_type": None}
    for key, pat in _FIELDS.items():
        m = re.search(pat, text, re.I)
        if m:
            val = m.group(1).strip()
            if key == "year":
                out[key] = int(val)
            elif len(val) >= 2:
                out[key] = val
    return out


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
    result = _extract(soup)
    result["vin"] = None  # QLD does not expose the VIN in public results
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
}


def lookup(plate, state):
    provider = PROVIDERS[state]
    result = provider(plate)
    result.update({"plate": plate, "state": state})
    return result
