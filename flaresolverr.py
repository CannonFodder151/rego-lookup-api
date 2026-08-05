import os
import re
import urllib.parse
import uuid

import requests
from bs4 import BeautifulSoup

from providers import (NotFound, UpstreamBlocked, UpstreamError, _extract_text,
                       _looks_like_not_found)

HINTS = ("plate", "rego", "registration", "vehicle number", "number plate")

FSR_TIMEOUT_MS = 45000


def _fsr_base():
    return (os.getenv("FLARESOLVERR_URL") or "").strip().rstrip("/") or None


def _request(url, *, post=None, sid=None, headers=None, timeout_ms=FSR_TIMEOUT_MS):
    base = _fsr_base()
    if not base:
        raise UpstreamError("FlareSolverr is not configured")
    payload = {
        "cmd": "request.post" if post is not None else "request.get",
        "url": url,
        "maxTimeout": timeout_ms,
    }
    if sid:
        payload["session"] = sid
    if post is not None:
        payload["postData"] = post
        payload["headers"] = {"Content-Type": "application/x-www-form-urlencoded"}
        if headers:
            payload["headers"].update(headers)
    r = requests.post(base + "/v1", json=payload, timeout=timeout_ms // 1000 + 30)
    r.raise_for_status()
    data = r.json()
    if data.get("status") != "ok":
        raise UpstreamError("FlareSolverr: " + str(data.get("message", data.get("error", "failed"))))
    sol = data["solution"]
    return sol.get("response", ""), sol


def _is_plate_input(inp):
    ctx = " ".join(inp.get(a, "") for a in ("placeholder", "title", "name", "id", "aria-label")).lower()
    return any(h in ctx for h in HINTS)


def _find_form(soup):
    for form in soup.find_all("form"):
        inputs = form.find_all("input")
        has_plate = any(_is_plate_input(i) for i in inputs)
        has_submit = bool(form.find("button", attrs={"type": ["submit", None]})
                          or form.find("input", {"type": "submit"}))
        if has_plate and has_submit:
            return form
    return None


def _form_post(form, url, plate):
    data = {}
    for inp in form.find_all("input"):
        n = inp.get("name")
        if not n:
            continue
        t = (inp.get("type") or "text").lower()
        v = inp.get("value", "")
        if t in ("checkbox", "radio"):
            if inp.has_attr("checked"):
                data[n] = v or "on"
        elif t not in ("submit", "button", "image", "reset"):
            data[n] = plate if _is_plate_input(inp) else v
    for btn in form.find_all("button", attrs={"type": ["submit", None]}):
        n = btn.get("name")
        if n:
            data[n] = btn.get("value") or btn.get_text(strip=True) or ""
    for btn in form.find_all("input", {"type": "submit"}):
        n = btn.get("name")
        if n:
            data[n] = btn.get("value", "")
    action = form.get("action", "")
    if action.startswith("#"):
        action = url
    else:
        action = urllib.parse.urljoin(url, action)
    return action, urllib.parse.urlencode(data)


def _parse_result(html, state, plate):
    soup = BeautifulSoup(html, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    low = text.lower()
    if _looks_like_not_found(text):
        raise NotFound(plate)
    if "just a moment" in low or "security verification" in low or "not a bot" in low:
        raise UpstreamBlocked(f"{state}: bot security verification did not resolve")
    result = _extract_text(text)
    if not any(result.values()):
        raise UpstreamError(f"{state}: vehicle details could not be retrieved")
    return result


def _vic(plate):
    sid = "rego-" + uuid.uuid4().hex[:12]
    url = "https://www.vicroads.vic.gov.au/registration/buy-sell-or-transfer-a-vehicle/check-vehicle-registration"
    html, sol = _request(url, sid=sid)
    soup = BeautifulSoup(html, "html.parser")
    form = _find_form(soup)
    if not form:
        raise UpstreamBlocked("VIC: lookup form not found on page")
    action, data = _form_post(form, sol.get("url") or url, plate)
    html2, _ = _request(action, post=data, sid=sid)
    return _parse_result(html2, "VIC", plate)


def _nt(plate):
    sid = "rego-" + uuid.uuid4().hex[:12]
    url = "https://nt.gov.au/driving/rego/existing-nt-registration/rego-check"
    html, sol = _request(url, sid=sid)
    soup = BeautifulSoup(html, "html.parser")
    form = _find_form(soup)
    if not form:
        raise UpstreamBlocked("NT: lookup form not found on page")
    action, data = _form_post(form, sol.get("url") or url, plate)
    html2, _ = _request(action, post=data, sid=sid)
    return _parse_result(html2, "NT", plate)


def _nsw(plate):
    sid = "rego-" + uuid.uuid4().hex[:12]
    url = "https://www.service.nsw.gov.au/transaction/check-a-vehicle-registration"
    html, sol = _request(url, sid=sid)
    soup = BeautifulSoup(html, "html.parser")
    form = _find_form(soup)
    if not form:
        link = None
        for a in soup.find_all("a"):
            if a.get_text() and re.search(r"check\s+online", a.get_text(), re.I):
                link = a
                break
        if link and link.get("href"):
            html, sol = _request(urllib.parse.urljoin(url, link["href"]), sid=sid)
            soup = BeautifulSoup(html, "html.parser")
            form = _find_form(soup)
    if not form:
        raise UpstreamBlocked("NSW: lookup form could not be reached")
    action, data = _form_post(form, sol.get("url") or url, plate)
    html2, _ = _request(action, post=data, sid=sid)
    return _parse_result(html2, "NSW", plate)


def _wa(plate):
    sid = "rego-" + uuid.uuid4().hex[:12]
    url = "https://online.transport.wa.gov.au/webExternal/registration"
    html, sol = _request(url, sid=sid)
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", {"name": "registrationRequestForm"})
    if not form:
        raise UpstreamBlocked("WA: registration form could not be reached")
    base = sol.get("url") or url
    m = re.search(r"\?(\d+)-", form.get("action", ""))
    ver = m.group(1) if m else "1"
    fields = {i.get("name"): i.get("value", "") for i in form.find_all("input", {"type": "hidden"})}
    fields.update({"plateField": plate, "searchButton": ""})
    headers = {"Wicket-Ajax": "true", "X-Requested-With": "XMLHttpRequest",
               "Wicket-Ajax-BaseURL": "/webExternal/registration"}
    ajax = urllib.parse.urljoin(base, f"./?{ver}.IBehaviorListener.1-layout-layout_body-registrationRequestForm-searchButton")
    html2, _ = _request(ajax, post=urllib.parse.urlencode(fields), sid=sid, headers=headers)
    m2 = re.search(r"<redirect><!\[CDATA\[([^\]]+)\]\]></redirect>", html2)
    if not m2:
        raise UpstreamError("WA: unexpected response from search")
    html3, _ = _request(urllib.parse.urljoin(base, m2.group(1)), sid=sid, headers=headers)
    return _parse_result(html3, "WA", plate)


def _act(plate):
    sid = "rego-" + uuid.uuid4().hex[:12]
    url = "https://www.accesscanberra.act.gov.au/app/answers/detail/a_id/1594/~/check-vehicle-registration"
    html, sol = _request(url, sid=sid)
    soup = BeautifulSoup(html, "html.parser")
    form = _find_form(soup)
    if not form:
        raise UpstreamBlocked("ACT: lookup form not found on page")
    action, data = _form_post(form, sol.get("url") or url, plate)
    html2, _ = _request(action, post=data, sid=sid)
    return _parse_result(html2, "ACT", plate)


def _blocked(state, why):
    def _f(plate):
        raise UpstreamBlocked(f"{state}: {why}")
    return _f


FUNCS = {
    "VIC": _vic,
    "NT": _nt,
    "NSW": _nsw,
    "WA": _wa,
    "ACT": _act,
    "SA": _blocked("SA", "JS single-page app requires click interaction (unsupported by FlareSolverr)"),
    "TAS": _blocked("TAS", "reCAPTCHA v3 token required at submit time"),
}


def fsr_lookup(plate, state):
    return FUNCS[state](plate)
