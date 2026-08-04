# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Turn a raw job posting into the fields STU filters on.

Everything here is transparent pattern matching -- you can always answer "why did
this job show up for a nursing student" by reading one regex. The majors and
skills themselves live in taxonomy.json so widening coverage is a data edit.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = json.loads((ROOT / "scripts" / "taxonomy.json").read_text(encoding="utf-8"))

# ------------------------------------------------------------------ seniority

# Strong signals are unambiguous and outrank any seniority word in the same title
# -- without this, "Associate Product Manager, New Grad" dies on the word "manager".
STRONG_ENTRY = re.compile(
    r"\b(interns?|internships?|new\s?grads?|new\s+graduates?|university\s+grad\w*|"
    r"campus|early\s+career|entry[\s-]?level|apprentice\w*|co[\s-]?ops?|trainee|"
    r"rotational|graduate\s+(?:program|scheme|rotation|nurse|nurses)|nurse\s+resident\w*|"
    r"residency|student\s+(?:nurse|worker|assistant)|practicum|fellowship)\b",
    re.I,
)
SOFT_ENTRY = re.compile(
    r"\b(junior|jr\.?|graduate\s+(?:engineer|analyst|developer|scientist|assistant)|"
    r"associate\s+(?:software|engineer|data|product|analyst|scientist|developer|consultant|nurse)|"
    r"\bi\b|level\s+1|tier\s+1)\b",
    re.I,
)
ENTRY_TITLE = re.compile(f"{STRONG_ENTRY.pattern}|{SOFT_ENTRY.pattern}", re.I)

# Only unambiguous seniority. "manager", "lead" and "executive" are deliberately
# absent -- they wrongly rejected real new-grad postings. Non-relevant roles get
# filtered by major instead.
SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|distinguished|director|head\s+of|vp|"
    r"vice\s+president|chief|architect|ii|iii|iv|supervisor|"
    r"(?:engineering|product|program|general|senior|nurse)\s+manager)\b",
    re.I,
)

# ---------------------------------------------------------------- sponsorship

NO_SPONSOR = re.compile(
    r"(not?\s+(?:be\s+)?(?:able|eligible)\s+to\s+sponsor|unable\s+to\s+sponsor|"
    r"cannot\s+sponsor|can\s?not\s+sponsor|will\s+not\s+sponsor|"
    r"do(?:es)?\s+not\s+(?:currently\s+)?(?:offer|provide|support)?\s*(?:visa\s+)?sponsor|"
    r"no\s+(?:visa\s+)?sponsorship|without\s+(?:the\s+need\s+for\s+)?(?:visa\s+|employer\s+)?sponsorship|"
    r"ineligible\s+for\s+(?:visa\s+)?sponsorship|sponsorship\s+is\s+not\s+(?:available|offered|provided))",
    re.I,
)
YES_SPONSOR = re.compile(
    r"((?:visa\s+)?sponsorship\s+(?:is\s+)?(?:available|offered|provided)|"
    r"we\s+(?:do\s+)?sponsor|will\s+sponsor|willing\s+to\s+sponsor|"
    r"offer\s+(?:visa\s+)?sponsorship|eligible\s+for\s+(?:visa\s+)?sponsorship|"
    r"support\s+(?:visa\s+)?sponsorship|h-?1b\s+(?:visa\s+)?sponsor)",
    re.I,
)
CLEARANCE = re.compile(r"\b(security\s+clearance|ts/sci|top\s+secret|\bpolygraph\b)\b", re.I)
YEARS = re.compile(r"(\d{1,2})\s*(?:\+|-|–|\s+to\s+)?\s*(?:\d{1,2})?\s*\+?\s*years?", re.I)

# Who is actually allowed to apply. An internship that demands current enrolment
# is useless to someone who already graduated, and a role that says "no experience
# necessary, we train" is open to anyone -- neither fact is in the job title.
ENROLLED_ONLY = re.compile(
    r"(currently\s+enrolled|must\s+be\s+enrolled|enrolled\s+in\s+(?:an?\s+)?"
    r"(?:accredited\s+)?(?:degree|bachelor|master|nursing|graduate)\s*\w*\s*program|"
    r"rising\s+(?:junior|senior|sophomore)|pursuing\s+(?:a|an|your)\s+"
    r"(?:bachelor|master|associate|degree)|current(?:ly)?\s+a?\s*student|"
    r"actively\s+enrolled)",
    re.I,
)
OPEN_TO_ALL = re.compile(
    r"(no\s+(?:prior\s+|previous\s+)?experience\s+(?:is\s+)?(?:required|necessary|needed)|"
    r"we(?:'ll| will)\s+train|will\s+train|training\s+(?:is\s+)?provided|paid\s+training|"
    r"high\s+school\s+diploma|\bged\b|no\s+degree\s+required|"
    r"entry[\s-]level\s+(?:role|position|opportunity))",
    re.I,
)

# A professional licence is the clinical equivalent of "5 years experience" -- it
# quietly disqualifies most students, so it's surfaced rather than filtered out.
# The earlier pattern was far too narrow: it caught only 23 of 127 nursing roles,
# which made the "No licence needed" filter look like it did nothing.
LICENSE = re.compile(
    r"(licen[cs]ure|"
    r"licen[cs]ed\s+(?:as\s+)?(?:an?\s+)?(?:registered\s+nurse|practical\s+nurse|"
    r"\brn\b|\blpn\b|\bnp\b|pharmacist|therapist|clinical\s+social\s+worker|"
    r"professional|clinician)|"
    r"(?:current|active|valid|unencumbered|unrestricted)\s+(?:\w+\s+){0,3}licen[cs]e|"
    r"\b(?:rn|lpn|np|pa|md|do|pharm\.?d|lcsw|lmsw|bcba)\b[^.]{0,40}licen[cs]e|"
    r"licen[cs]e\s+(?:is\s+)?required|"
    r"must\s+(?:have|possess|hold)\s+[^.]{0,40}licen[cs]e)",
    re.I,
)
# A driving licence is not a professional credential and must not gate students.
DRIVER_LICENSE = re.compile(r"driver'?s?\s+licen[cs]e|\bcdl\b|driving\s+licen[cs]e", re.I)


def requires_license(text: str) -> bool:
    """True only for professional licensure, ignoring 'valid driver's license'."""
    for m in LICENSE.finditer(text or ""):
        window = text[max(0, m.start() - 40): m.end() + 40]
        if not DRIVER_LICENSE.search(window):
            return True
    return False

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = TAG_RE.sub(" ", text)
    return WS_RE.sub(" ", html.unescape(text)).strip()


# ---------------------------------------------------------------------- majors


def _compile_skill(term: str) -> re.Pattern:
    """Taxonomy skills may be plain words or pre-escaped regex like '\\br\\b'."""
    if "\\" in term:
        return re.compile(term, re.I)
    if re.fullmatch(r"[a-z0-9 ]+", term):
        return re.compile(rf"\b{re.escape(term)}\b", re.I)
    return re.compile(re.escape(term), re.I)  # "c++", "fp&a" -- boundaries don't apply


def _label(term: str) -> str:
    return term.replace("\\b", "").replace("\\", "")


MAJORS = []
for m in TAXONOMY["majors"]:
    MAJORS.append({
        "id": m["id"],
        "label": m["label"],
        "group": m["group"],
        "title": re.compile(m["title"], re.I),
        "skills": [(_label(s), _compile_skill(s)) for s in m["skills"]],
    })

GENERIC_SKILLS = [(_label(s), _compile_skill(s)) for s in TAXONOMY["generic_skills"]]

# Skill -> canonical label, deduped across majors so a match reports once.
ALL_SKILLS: dict[str, re.Pattern] = {}
for m in MAJORS:
    for label, rx in m["skills"]:
        ALL_SKILLS.setdefault(label, rx)
for label, rx in GENERIC_SKILLS:
    ALL_SKILLS.setdefault(label, rx)


def majors_for(title: str, dept: str = "") -> list[str]:
    """Every major whose title pattern matches. A job can serve several."""
    blob = f"{title} {dept}"
    return [m["id"] for m in MAJORS if m["title"].search(blob)]


def skills_in(text: str, limit: int = 14) -> list[str]:
    """Coursework-relevant terms present in the text, most specific first."""
    if not text:
        return []
    found = [label for label, rx in ALL_SKILLS.items() if rx.search(text)]
    # Longer terms are more informative than "excel" or "research".
    found.sort(key=lambda s: (-len(s), s))
    return found[:limit]


# ------------------------------------------------------------------- specifics


def min_years(text: str) -> int | None:
    """Smallest year-count requirement mentioned near the word 'experience'."""
    found = []
    for m in YEARS.finditer(text):
        window = text[max(0, m.start() - 60): m.end() + 60].lower()
        if "experience" not in window:
            continue
        try:
            n = int(m.group(1))
        except ValueError:
            continue
        if 0 <= n <= 15:
            found.append(n)
    return min(found) if found else None


def sponsorship(text: str) -> str:
    if NO_SPONSOR.search(text):
        return "no"
    if YES_SPONSOR.search(text):
        return "yes"
    return "unknown"


US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "district of columbia": "DC",
}
US_CITIES = {
    "san francisco": "CA", "mountain view": "CA", "palo alto": "CA", "sunnyvale": "CA",
    "san jose": "CA", "los angeles": "CA", "san diego": "CA", "oakland": "CA",
    "santa monica": "CA", "irvine": "CA", "culver city": "CA", "sacramento": "CA",
    "new york": "NY", "nyc": "NY", "brooklyn": "NY", "bronx": "NY", "buffalo": "NY",
    "seattle": "WA", "bellevue": "WA", "redmond": "WA", "austin": "TX", "dallas": "TX",
    "houston": "TX", "san antonio": "TX", "boston": "MA", "cambridge": "MA",
    "chicago": "IL", "evanston": "IL", "springfield": "IL", "denver": "CO", "boulder": "CO",
    "atlanta": "GA", "miami": "FL", "orlando": "FL", "tampa": "FL", "phoenix": "AZ",
    "tempe": "AZ", "pittsburgh": "PA", "philadelphia": "PA", "portland": "OR",
    "detroit": "MI", "ann arbor": "MI", "kalamazoo": "MI", "minneapolis": "MN",
    "st paul": "MN", "nashville": "TN", "salt lake city": "UT", "raleigh": "NC",
    "durham": "NC", "charlotte": "NC", "arlington": "VA", "reston": "VA", "mclean": "VA",
    "richmond": "VA", "bethesda": "MD", "baltimore": "MD", "washington": "DC",
    "kansas city": "KS", "wichita": "KS", "louisville": "KY", "bend": "OR",
    "woonsocket": "RI", "boise": "ID", "madison": "WI", "milwaukee": "WI",
    "columbus": "OH", "cleveland": "OH", "cincinnati": "OH", "indianapolis": "IN",
    "st louis": "MO", "omaha": "NE", "des moines": "IA", "little rock": "AR",
    "fayetteville": "AR", "newark": "NJ", "montclair": "NJ", "winston-salem": "NC",
}


def parse_location(raw: str, remote_hint: bool = False) -> dict:
    loc = WS_RE.sub(" ", (raw or "")).strip() or "Unspecified"
    low = loc.lower()
    remote = bool(remote_hint or re.search(r"\bremote\b|\bwork from home\b|\banywhere\b", low))
    hybrid = bool(re.search(r"\bhybrid\b", low))

    state = None
    for name, abbr in US_STATES.items():
        if re.search(rf"\b{re.escape(name)}\b", low):
            state = abbr
            break
    if not state:
        # "Chicago, IL" but also the shapes big employers actually use:
        # "FL - Ft. Myers", "OH-West Chester", "TX-Dallas-Main".
        for pattern in (r",\s*([A-Z]{2})\b", r"\b([A-Z]{2})\s*[-–]\s*\w", r"^([A-Z]{2})\b"):
            m = re.search(pattern, loc)
            if m and m.group(1) in US_STATES.values():
                state = m.group(1)
                break
    if not state:
        for city, abbr in US_CITIES.items():
            if re.search(rf"\b{re.escape(city)}\b", low):
                state = abbr
                break

    us = bool(state or re.search(r"\b(united states|usa|u\.s\.a?\.?)\b", low))
    return {"location": loc[:80], "state": state, "us": us,
            "remote": remote, "hybrid": hybrid}


def is_entry_level(title: str, text: str = "") -> str | None:
    """Returns internship / new_grad / entry, or None when it isn't junior."""
    if SENIOR_TITLE.search(title) and not STRONG_ENTRY.search(title):
        return None

    t = title.lower()
    if re.search(r"\b(interns?|internships?|co[\s-]?ops?|practicum|student\s+\w+)\b", t):
        return "internship"
    if re.search(r"\b(new\s?grads?|new\s+graduates?|university\s+grad\w*|campus|"
                 r"graduate\s+(?:program|scheme|nurse|nurses)|nurse\s+resident\w*|"
                 r"residency|rotational|fellowship)\b", t):
        return "new_grad"
    if ENTRY_TITLE.search(t):
        return "entry"
    if re.search(r"\b(new\s+grad|recent\s+graduate|graduating\s+in|0-2\s+years|"
                 r"entry[\s-]level)\b", text, re.I):
        return "entry"
    # Nothing in the title says "junior", but the posting says anyone can do it.
    # This is what makes STU useful to career changers and the general public,
    # not only to people currently enrolled somewhere.
    if OPEN_TO_ALL.search(text):
        return "entry"
    return None


def audience(role: str, text: str) -> str:
    """students (needs enrolment) / grads (needs a recent degree) / open (anyone)."""
    if ENROLLED_ONLY.search(text):
        return "students"
    if OPEN_TO_ALL.search(text):
        return "open"
    if role == "internship":
        return "students"
    if role == "new_grad":
        return "grads"
    return "open"
