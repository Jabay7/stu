# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Adapters for the five applicant-tracking systems STU reads.

Each returns a list of raw dicts with the same keys, so fetch_jobs.py can
classify everything identically no matter where it came from.

None of this scrapes HTML -- every endpoint here is the JSON API that the
company's own careers page calls.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from classify import is_entry_level, strip_html

UA = {
    "User-Agent": "stu-jobboard/2.0 (student project)",
    "Accept": "application/json",
    "Content-Type": "application/json",
}
TIMEOUT = 25


def get_json(url: str, payload: dict | None = None, retries: int = 3):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=UA)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, ConnectionError):
            if attempt == retries - 1:
                raise
    return None


def _row(**kw) -> dict:
    row = {"company": "", "source": "", "title": "", "url": "", "location_raw": "",
           "description": "", "posted": None, "days": None, "dept": "",
           "remote_hint": False, "default_state": None}
    row.update(kw)
    return row


def _days_from_iso(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except ValueError:
        return None


# ------------------------------------------------------------------ greenhouse


def greenhouse(token: str) -> list[dict]:
    data = get_json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true")
    out = []
    for j in (data or {}).get("jobs", []):
        posted = j.get("first_published") or j.get("updated_at")
        out.append(_row(
            company=(j.get("company_name") or token).strip(),
            source="greenhouse",
            title=j.get("title", ""),
            url=j.get("absolute_url", ""),
            location_raw=(j.get("location") or {}).get("name", ""),
            description=strip_html(j.get("content", "")),
            posted=posted,
            days=_days_from_iso(posted),
            dept=" ".join(d.get("name", "") for d in (j.get("departments") or [])),
        ))
    return out


# ----------------------------------------------------------------------- ashby


def ashby(token: str) -> list[dict]:
    data = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{token}")
    out = []
    for j in (data or {}).get("jobs", []):
        if j.get("isListed") is False:
            continue
        posted = j.get("publishedAt")
        out.append(_row(
            company=token,
            source="ashby",
            title=j.get("title", ""),
            url=j.get("jobUrl") or j.get("applyUrl", ""),
            location_raw=j.get("location", ""),
            description=j.get("descriptionPlain", "") or "",
            posted=posted,
            days=_days_from_iso(posted),
            dept=f"{j.get('department', '')} {j.get('team', '')}",
            remote_hint=bool(j.get("isRemote")),
        ))
    return out


# ----------------------------------------------------------------------- lever


def lever(token: str) -> list[dict]:
    data = get_json(f"https://api.lever.co/v0/postings/{token}?mode=json")
    out = []
    for j in data or []:
        cats = j.get("categories") or {}
        posted = None
        if j.get("createdAt"):
            posted = datetime.fromtimestamp(j["createdAt"] / 1000, timezone.utc).isoformat()
        out.append(_row(
            company=token,
            source="lever",
            title=j.get("text", ""),
            url=j.get("hostedUrl") or j.get("applyUrl", ""),
            location_raw=cats.get("location", ""),
            description=" ".join(filter(None, [j.get("descriptionPlain", ""),
                                               j.get("additionalPlain", "")])),
            posted=posted,
            days=_days_from_iso(posted),
            dept=f"{cats.get('team', '')} {cats.get('department', '')}",
            remote_hint=(j.get("workplaceType") == "remote"),
        ))
    return out


# --------------------------------------------------------------- smartrecruiters


def smartrecruiters(token: str) -> list[dict]:
    out = []
    for offset in (0, 100, 200):
        data = get_json(
            f"https://api.smartrecruiters.com/v1/companies/{token}/postings"
            f"?limit=100&offset={offset}"
        )
        postings = (data or {}).get("content", [])
        if not postings:
            break
        for j in postings:
            loc = j.get("location") or {}
            city = ", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")]))
            posted = j.get("releasedDate")
            out.append(_row(
                company=(j.get("company") or {}).get("name") or token,
                source="smartrecruiters",
                title=j.get("name", ""),
                url=f"https://jobs.smartrecruiters.com/{token}/{j.get('id')}",
                location_raw=city,
                # The list endpoint has no description; the title carries enough
                # signal for seniority, and a per-job fetch here would be 100s of
                # extra requests for marginal gain.
                description="",
                posted=posted,
                days=_days_from_iso(posted),
                dept=(j.get("department") or {}).get("label", "") or (j.get("function") or {}).get("label", ""),
                remote_hint=bool(loc.get("remote")),
            ))
    return out


# --------------------------------------------------------------------- workday

# Workday is how hospitals, universities and government actually post jobs, which
# is what makes non-CS majors possible. Three quirks drive the design below:
#   1. `limit` is capped at 20, so paging the whole board is out of the question
#      (CVS Health alone has 18,000 postings). We query by entry-level keyword.
#   2. `postedOn` is prose -- "Posted Today", "Posted 30+ Days Ago" -- not a date.
#   3. Descriptions need a second request per job, so we only fetch them for
#      postings whose title already looks entry-level.

WORKDAY_QUERIES = [
    "intern", "internship", "new grad", "graduate nurse", "nurse residency",
    "entry level", "apprentice", "trainee", "student", "associate",
]
WORKDAY_PAGES = 3  # 3 x 20 = up to 60 hits per query per employer

# Workday's search covers the location text as well as the title, so appending a
# state name genuinely narrows results to that state -- verified against CVS,
# where "pharmacy intern Ohio" returns Ohio postings. Employers flagged
# "nationwide" in companies.json get swept state by state, which is the only way
# a chain with 18,000 postings yields anything outside its biggest metros.
STATE_NAMES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
    "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia",
    "Washington", "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
]
NATIONWIDE_QUERIES = ["intern", "new grad", "entry level"]

POSTED_RE = re.compile(r"(\d+)\+?\s*days?", re.I)


def _workday_days(posted_on: str | None) -> int | None:
    if not posted_on:
        return None
    low = posted_on.lower()
    if "today" in low:
        return 0
    if "yesterday" in low:
        return 1
    m = POSTED_RE.search(low)
    return int(m.group(1)) if m else None


def workday(entry: dict) -> list[dict]:
    """entry: {"tenant","wd","site","name"} from companies.json."""
    tenant, wd, site = entry["tenant"], entry["wd"], entry["site"]
    name = entry.get("name") or tenant
    base = f"https://{tenant}.{wd}.myworkdayjobs.com"
    api = f"{base}/wday/cxs/{tenant}/{site}"

    # (query, pages) -- the broad sweep goes deep, the per-state sweep goes wide.
    plan = [(q, WORKDAY_PAGES) for q in WORKDAY_QUERIES]
    if entry.get("nationwide"):
        plan += [(f"{q} {state}", 1)
                 for state in STATE_NAMES for q in NATIONWIDE_QUERIES]

    seen: dict[str, dict] = {}

    def sweep(job):
        query, pages = job
        found = []
        for page in range(pages):
            try:
                data = get_json(f"{api}/jobs", {
                    "appliedFacets": {}, "limit": 20,
                    "offset": page * 20, "searchText": query,
                })
            except Exception:
                break
            postings = (data or {}).get("jobPostings", [])
            if not postings:
                break
            found.extend(postings)
        return found

    # A nationwide sweep is 150+ queries, so they run concurrently.
    with ThreadPoolExecutor(max_workers=8) as pool:
        for postings in pool.map(sweep, plan):
            for p in postings:
                path = p.get("externalPath", "")
                if path and path not in seen:
                    seen[path] = p

    # Only postings that already read as entry-level earn a description fetch.
    candidates = [(path, p) for path, p in seen.items()
                  if is_entry_level(p.get("title", ""))]

    def detail(item):
        path, p = item
        desc, loc = "", p.get("locationsText", "")
        try:
            d = get_json(f"{api}{path}")
            info = (d or {}).get("jobPostingInfo", {})
            desc = strip_html(info.get("jobDescription", ""))
            loc = info.get("location") or loc
        except Exception:
            pass
        return _row(
            company=name,
            source="workday",
            title=p.get("title", ""),
            url=f"{base}/{site}{path}",
            location_raw=loc,
            description=desc,
            posted=None,
            days=_workday_days(p.get("postedOn")),
            dept="",
            # Health systems label postings by facility ("Cobb Hospital"), which
            # no string parsing resolves -- but a single-state employer's own
            # state is the right answer for all of them.
            default_state=entry.get("state"),
        )

    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(detail, candidates))


FETCHERS = {
    "greenhouse": greenhouse,
    "ashby": ashby,
    "lever": lever,
    "smartrecruiters": smartrecruiters,
    "workday": workday,
}
