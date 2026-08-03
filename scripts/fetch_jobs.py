# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Pull entry-level tech jobs from public applicant-tracking-system APIs.

No scraping. Greenhouse, Ashby and Lever each publish a documented public JSON
endpoint for every company's job board, so there is nothing to block and nothing
to break when a careers page gets restyled.

Run:  uv run scripts/fetch_jobs.py
Out:  data/jobs.json, data/meta.json
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = {"User-Agent": "stu-jobboard/1.0 (student project; +https://github.com/)"}
TIMEOUT = 25

# ---------------------------------------------------------------- classifiers

# Word-boundary anchored so "Internal Audit" never reads as an internship.
# STRONG signals are unambiguous and outrank any seniority word in the same title
# -- without this, "Associate Product Manager, New Grad" dies on the word "manager".
STRONG_ENTRY = re.compile(
    r"\b(intern|interns|internship|new\s?grad|new\s+graduate|university\s+grad\w*|"
    r"campus|early\s+career|entry[\s-]?level|apprentice\w*|co[\s-]?op|trainee|"
    r"rotational|graduate\s+(?:program|scheme|rotation))\b",
    re.I,
)
# SOFT signals mean entry-level only when nothing senior contradicts them.
SOFT_ENTRY = re.compile(
    r"\b(junior|jr\.?|graduate\s+(?:engineer|analyst|developer|scientist)|"
    r"associate\s+(?:software|engineer|data|product|analyst|scientist|developer|consultant))\b",
    re.I,
)
ENTRY_TITLE = re.compile(f"{STRONG_ENTRY.pattern}|{SOFT_ENTRY.pattern}", re.I)

# Only unambiguous seniority belongs here. "manager", "lead", "executive" and
# "expert" were removed after they wrongly rejected real new-grad postings --
# non-technical roles get filtered by category instead.
SENIOR_TITLE = re.compile(
    r"\b(senior|sr\.?|staff|principal|distinguished|director|head\s+of|vp|"
    r"vice\s+president|chief|architect|ii|iii|iv|"
    r"(?:engineering|product|program|general|senior)\s+manager)\b",
    re.I,
)
GRAD_YEAR = re.compile(r"\b20(2[5-9]|3[0-2])\b")

CATEGORIES = [
    ("Data / ML", r"\b(machine\s?learning|\bml\b|\bai\b|data\s+(scien|engineer|analy)|"
                  r"deep\s+learning|research\s+scien|quantitative|analytics)\b"),
    ("Security",  r"\b(security|appsec|infosec|cryptograph|trust\s*&?\s*safety|privacy)\b"),
    ("Infra / DevOps", r"\b(infrastructure|devops|\bsre\b|site\s+reliability|platform\s+engineer|cloud\s+engineer)\b"),
    ("Engineering", r"\b(software|engineer|developer|programmer|full\s?stack|front\s?end|"
                    r"back\s?end|mobile|ios|android|web\s+dev|qa|test\s+engineer)\b"),
    ("Product", r"\b(product\s+manag|product\s+owner|technical\s+program|\btpm\b|program\s+manag)\b"),
    ("Design", r"\b(design|\bux\b|\bui\b|research(?:er)?\s+design)\b"),
    ("IT / Support", r"\b(it\s+support|help\s?desk|systems\s+admin|technical\s+support|solutions\s+engineer)\b"),
]

# Checked in order -- a "we cannot sponsor" line beats a generic "sponsorship" mention.
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

# "3+ years", "3-5 years", "minimum of 2 years"
YEARS = re.compile(r"(\d{1,2})\s*(?:\+|-|–|\s+to\s+)?\s*(?:\d{1,2})?\s*\+?\s*years?", re.I)

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
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC", "washington dc": "DC",
}
US_CITIES = {
    "san francisco": "CA", "sf": "CA", "mountain view": "CA", "palo alto": "CA",
    "sunnyvale": "CA", "san jose": "CA", "los angeles": "CA", "san diego": "CA",
    "oakland": "CA", "santa monica": "CA", "irvine": "CA", "culver city": "CA",
    "new york": "NY", "nyc": "NY", "brooklyn": "NY", "seattle": "WA", "bellevue": "WA",
    "redmond": "WA", "austin": "TX", "dallas": "TX", "houston": "TX", "boston": "MA",
    "cambridge": "MA", "chicago": "IL", "evanston": "IL", "denver": "CO", "boulder": "CO",
    "atlanta": "GA", "miami": "FL", "phoenix": "AZ", "tempe": "AZ", "pittsburgh": "PA",
    "philadelphia": "PA", "portland": "OR", "detroit": "MI", "ann arbor": "MI",
    "minneapolis": "MN", "nashville": "TN", "salt lake city": "UT", "raleigh": "NC",
    "durham": "NC", "charlotte": "NC", "arlington": "VA", "reston": "VA", "mclean": "VA",
    "bethesda": "MD", "washington": "DC",
}

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def strip_html(raw: str) -> str:
    if not raw:
        return ""
    # Greenhouse double-encodes: unescape, drop tags, unescape entities left behind.
    text = html.unescape(raw)
    text = TAG_RE.sub(" ", text)
    return WS_RE.sub(" ", html.unescape(text)).strip()


def get_json(url: str):
    req = urllib.request.Request(url, headers=UA)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            if attempt == 2:
                raise
    return None


def classify_category(title: str, dept: str) -> str | None:
    blob = f"{title} {dept}"
    for name, pattern in CATEGORIES:
        if re.search(pattern, blob, re.I):
            return name
    return None


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


def parse_location(raw: str, is_remote_hint: bool = False) -> dict:
    loc = WS_RE.sub(" ", (raw or "")).strip() or "Unspecified"
    low = loc.lower()
    remote = bool(is_remote_hint or re.search(r"\bremote\b|\bwork from home\b|\banywhere\b", low))
    hybrid = bool(re.search(r"\bhybrid\b", low))

    state = None
    for name, abbr in US_STATES.items():
        if re.search(rf"\b{re.escape(name)}\b", low):
            state = abbr
            break
    if not state:
        m = re.search(r",\s*([A-Z]{2})\b", loc)
        if m and m.group(1) in US_STATES.values():
            state = m.group(1)
    if not state:
        for city, abbr in US_CITIES.items():
            if re.search(rf"\b{re.escape(city)}\b", low):
                state = abbr
                break

    us = bool(state or re.search(r"\b(united states|usa|u\.s\.a?\.?)\b", low))
    return {
        "location": loc[:80],
        "state": state,
        "us": us,
        "remote": remote,
        "hybrid": hybrid,
    }


def role_type(title: str, text: str) -> str | None:
    t = title.lower()
    # "Interns" (plural) and "Internships" must land here too, not fall through to entry.
    if re.search(r"\b(interns?|internships?|co[\s-]?ops?|coops?)\b", t):
        return "internship"
    if re.search(r"\b(new\s?grads?|new\s+graduates?|university\s+grad\w*|campus|graduate\s+program|rotational)\b", t):
        return "new_grad"
    if ENTRY_TITLE.search(t):
        return "entry"
    # Title is neutral ("Software Engineer") -- let the description decide.
    if re.search(r"\b(new\s+grad|recent\s+graduate|graduating\s+in|0-2\s+years|entry[\s-]level)\b", text, re.I):
        return "entry"
    return None


def build(company: str, source: str, title: str, url: str, loc_raw: str,
          desc: str, posted: str | None, dept: str, remote_hint: bool = False) -> dict | None:
    title = WS_RE.sub(" ", title or "").strip()
    if not title or not url:
        return None

    # Reject seniority -- unless the title also carries a strong entry signal,
    # which is how "Associate Product Manager, New Grad (2027)" survives.
    if SENIOR_TITLE.search(title) and not STRONG_ENTRY.search(title):
        return None

    rtype = role_type(title, desc)
    if not rtype:
        return None

    category = classify_category(title, dept)
    if not category:
        return None  # non-tech role; this board is for CS students

    yoe = min_years(desc)
    # A "senior-in-disguise" guard: entry titles asking for 4+ years are miscategorised.
    if yoe is not None and yoe >= 4:
        return None

    loc = parse_location(loc_raw, remote_hint)
    days = None
    if posted:
        try:
            dt = datetime.fromisoformat(posted.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = max(0, (datetime.now(timezone.utc) - dt).days)
        except ValueError:
            pass

    return {
        "id": f"{source}:{company}:{abs(hash((title, loc['location'], url))) % 10**10}",
        "company": company,
        "title": title[:120],
        "url": url,
        "category": category,
        "role": rtype,
        "yoe": yoe,
        "sponsor": sponsorship(desc),
        "clearance": bool(CLEARANCE.search(desc)),
        "posted": posted,
        "days": days,
        "source": source,
        **loc,
    }


# ------------------------------------------------------------------- sources

def from_greenhouse(token: str) -> list[dict]:
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    out = []
    for j in (data or {}).get("jobs", []):
        desc = strip_html(j.get("content", ""))
        dept = " ".join(d.get("name", "") for d in (j.get("departments") or []))
        job = build(
            company=(j.get("company_name") or token).strip(),
            source="greenhouse",
            title=j.get("title", ""),
            url=j.get("absolute_url", ""),
            loc_raw=(j.get("location") or {}).get("name", ""),
            desc=desc,
            posted=j.get("first_published") or j.get("updated_at"),
            dept=dept,
        )
        if job:
            out.append(job)
    return out


def from_ashby(token: str) -> list[dict]:
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    out = []
    for j in (data or {}).get("jobs", []):
        if j.get("isListed") is False:
            continue
        job = build(
            company=token,
            source="ashby",
            title=j.get("title", ""),
            url=j.get("jobUrl") or j.get("applyUrl", ""),
            loc_raw=j.get("location", ""),
            desc=j.get("descriptionPlain", "") or "",
            posted=j.get("publishedAt"),
            dept=f"{j.get('department', '')} {j.get('team', '')}",
            remote_hint=bool(j.get("isRemote")),
        )
        if job:
            out.append(job)
    return out


def from_lever(token: str) -> list[dict]:
    data = get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    out = []
    for j in data or []:
        cats = j.get("categories") or {}
        posted = None
        if j.get("createdAt"):
            posted = datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc).isoformat()
        desc = " ".join(filter(None, [j.get("descriptionPlain", ""), j.get("additionalPlain", "")]))
        job = build(
            company=token,
            source="lever",
            title=j.get("text", ""),
            url=j.get("hostedUrl") or j.get("applyUrl", ""),
            loc_raw=cats.get("location", ""),
            desc=desc,
            posted=posted,
            dept=f"{cats.get('team', '')} {cats.get('department', '')}",
            remote_hint=(j.get("workplaceType") == "remote"),
        )
        if job:
            out.append(job)
    return out


FETCHERS = {"greenhouse": from_greenhouse, "ashby": from_ashby, "lever": from_lever}


def main() -> int:
    cfg = json.loads((ROOT / "scripts" / "companies.json").read_text(encoding="utf-8"))
    targets = [(src, tok) for src in FETCHERS for tok in cfg.get(src, [])]

    jobs: list[dict] = []
    ok, failed = [], []

    def run(pair):
        src, tok = pair
        try:
            return pair, FETCHERS[src](tok), None
        except Exception as exc:  # one dead board must never sink the run
            return pair, [], str(exc)[:120]

    with ThreadPoolExecutor(max_workers=8) as pool:
        for (src, tok), found, err in pool.map(run, targets):
            if err:
                failed.append(f"{src}/{tok}: {err}")
                print(f"  !! {src}/{tok} failed: {err}", file=sys.stderr)
            else:
                ok.append(f"{src}/{tok}")
                jobs.extend(found)
                print(f"  ok {src}/{tok}: {len(found)} entry-level")

    # Dedup -- the same role is often posted to several offices.
    seen, unique = set(), []
    for j in sorted(jobs, key=lambda x: (x["days"] is None, x["days"] or 0)):
        key = (j["company"].lower(), j["title"].lower(), j["location"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(j)

    # Safety valve: if every board rate-limited us tonight, keep yesterday's board
    # rather than publishing an empty app.
    existing = DATA / "jobs.json"
    if not unique and existing.exists():
        previous = json.loads(existing.read_text(encoding="utf-8"))
        if previous:
            print(f"\n!! 0 jobs scraped but {len(previous)} already published -- keeping existing data")
            return 1

    DATA.mkdir(parents=True, exist_ok=True)
    existing.write_text(
        json.dumps(unique, separators=(",", ":"), ensure_ascii=False), encoding="utf-8"
    )

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(unique),
        "companies_ok": len(ok),
        "companies_failed": failed,
        "by_role": {r: sum(1 for j in unique if j["role"] == r) for r in ("internship", "new_grad", "entry")},
        "sponsors": sum(1 for j in unique if j["sponsor"] == "yes"),
        "remote": sum(1 for j in unique if j["remote"]),
    }
    (DATA / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\n{len(unique)} unique entry-level roles from {len(ok)}/{len(targets)} boards")
    print(f"  by role: {meta['by_role']}")
    print(f"  sponsors visas: {meta['sponsors']}   remote: {meta['remote']}")
    if failed:
        print(f"  {len(failed)} board(s) failed (kept last good data for them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
