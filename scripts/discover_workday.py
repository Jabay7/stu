# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Find Workday career sites for candidate employers and merge them into the roster.

A Workday board is addressed by three unknowns -- tenant, datacentre host (wd1,
wd5, ...) and site name -- and only the tenant is guessable from the company
name. This probes the combinations cheaply:

  1. one request per host to see whether the tenant exists there at all
     (a wrong site returns 422, a wrong tenant fails outright)
  2. only then try the ~14 site names employers actually use

Run:  uv run scripts/discover_workday.py
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "scripts" / "companies.json"
UA = {"User-Agent": "stu-jobboard/2.0 (student project)", "Content-Type": "application/json"}
BODY = json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}).encode()

HOSTS = ["wd1", "wd5", "wd3", "wd12", "wd108", "wd101", "wd103", "wd102"]
SITES = [
    "External", "external", "Careers", "careers", "Search", "search",
    "Jobs", "jobs", "ExternalCareerSite", "External_Career_Site",
    "CareerSite", "{t}careers", "{t}jobs", "{T}Careers", "{T}_Careers",
    "{t}Careers", "{t}Jobs", "{T}jobs", "{T}Jobs", "{t}_careers",
    "careersite", "CareerHome", "Career", "ExternalSite", "Recruiting",
    "{U}_Careers", "{U}_External", "{U}Careers", "External_Careers",
    "ExternalCareers", "External_Career_Site",
]

# Verified by hand. Site names like "OhioHealthJobs", "targetcareers" and
# "NC_Careers" follow no pattern worth guessing at, and `state` is what rescues
# employers that label postings by facility rather than by city.
KNOWN = [
    {"tenant": "target", "wd": "wd5", "site": "targetcareers", "name": "Target", "nationwide": True},
    {"tenant": "ohiohealth", "wd": "wd5", "site": "OhioHealthJobs", "name": "OhioHealth", "state": "OH"},
    {"tenant": "bannerhealth", "wd": "wd5", "site": "Careers", "name": "Banner Health", "state": "AZ"},
    # Filling specific state gaps.
    {"tenant": "searhc", "wd": "wd5", "site": "SEARHC", "name": "SEARHC", "state": "AK"},
    {"tenant": "bozemanhealth", "wd": "wd1", "site": "BozemanHealthCareers", "name": "Bozeman Health", "state": "MT"},
    {"tenant": "brownhealth", "wd": "wd12", "site": "External_Careers", "name": "Brown University Health", "state": "RI"},
    {"tenant": "crhc", "wd": "wd1", "site": "Concord_Careers", "name": "Concord Hospital", "state": "NH"},
    {"tenant": "nebraskamed", "wd": "wd5", "site": "NM", "name": "Nebraska Medicine", "state": "NE"},
    {"tenant": "stph", "wd": "wd5", "site": "STPH", "name": "St. Tammany Health System", "state": "LA"},
    {"tenant": "wvumedicine", "wd": "wd1", "site": "WVUH", "name": "WVU Medicine", "state": "WV"},
    {"tenant": "vumc", "wd": "wd1", "site": "vumccareers", "name": "Vanderbilt University Medical Center", "state": "TN"},
    {"tenant": "vcuhealth", "wd": "wd1", "site": "VCUHealth_careers", "name": "VCU Health", "state": "VA"},
    {"tenant": "nc", "wd": "wd108", "site": "NC_Careers", "name": "State of North Carolina", "state": "NC"},
    {"tenant": "wustl", "wd": "wd1", "site": "External", "name": "Washington University in St. Louis", "state": "MO"},
    # Multi-state chains -- swept state by state instead of given a home state.
    {"tenant": "imh", "wd": "wd108", "site": "IntermountainCareers", "name": "Intermountain Health", "nationwide": True},
    {"tenant": "mckesson", "wd": "wd3", "site": "External_Careers", "name": "McKesson", "nationwide": True},
]

# Grouped by the gap each one fills. Health systems and universities are the
# employers that actually exist in every state.
# Aimed at the states that still show zero. State governments are included
# because they hire in every state and several run public Workday boards --
# North Carolina's nc.wd108/NC_Careers is the model.
# Workday is where the roster skews medical, because health systems are the
# biggest employers in small states. These are deliberately non-medical: retail,
# banking, insurance, manufacturing, hospitality, media and universities, which
# is where marketing, finance, HR, design and education roles actually live.
CANDIDATES = {
    "retail": ["bestbuy", "nordstrom", "gap", "williamssonoma", "dickssportinggoods",
               "tractorsupply", "petco", "ulta", "sephora", "aldi", "wegmans", "meijer"],
    "finance": ["regions", "keybank", "huntington", "citizensbank", "discover",
                "synchrony", "usaa", "fifththird", "comerica", "zionsbancorp"],
    "insurance": ["progressive", "allstate", "statefarm", "libertymutual",
                  "nationwide", "thehartford", "travelers", "erieinsurance"],
    "industrial": ["cummins", "deere", "caterpillar", "honeywell", "emerson",
                   "rockwellautomation", "parker", "dover", "textron", "leidos"],
    "hospitality": ["marriott", "hilton", "hyatt", "united", "delta", "southwest",
                    "alaskaair", "choicehotels", "wyndham"],
    "media": ["comcast", "charter", "paramount", "warnerbros", "sonymusic", "nielsen"],
    "consulting": ["protiviti", "rsm", "bdo", "grantthornton", "crowe", "kforce"],
    "university": ["nyu", "bu", "gwu", "syr", "drexel", "depaul", "loyola", "fordham",
                   "pepperdine", "baylor", "smu", "tcu", "villanova", "marquette"],
    "state-gov": ["va", "wa", "or", "co", "az", "tn", "sc", "md", "mn", "wi", "in", "ky",
                  "mo", "ga", "al", "ok", "ut", "nj", "ct", "nm", "nv", "hi", "id",
                  "mt", "nd", "wy", "ms", "ia"],
}


def probe(url: str) -> tuple[str, int] | None:
    """('ok', count) on a live board, ('http', status) if the HOST answered at
    all, None only when the host itself doesn't resolve.

    The distinction matters: a wrong site name returns 404 on some tenants and
    422 on others, and treating 404 as "no such tenant" skips every host before
    the real site names are ever tried."""
    try:
        req = urllib.request.Request(url, data=BODY, headers=UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        return ("ok", data.get("total", 0))
    except urllib.error.HTTPError as exc:
        return ("http", exc.code)          # host is real, this site isn't
    except Exception:
        return None                        # DNS / connection failure


def find(tenant: str) -> dict | None:
    for host in HOSTS:
        api = f"https://{tenant}.{host}.myworkdayjobs.com/wday/cxs/{tenant}"
        # Any HTTP response means the tenant exists on this host.
        if probe(f"{api}/__probe__/jobs") is None:
            continue
        for template in SITES:
            site = template.format(t=tenant, T=tenant.capitalize(), U=tenant.upper())
            result = probe(f"{api}/{site}/jobs")
            if result and result[0] == "ok" and result[1] > 0:
                return {"tenant": tenant, "wd": host, "site": site, "total": result[1]}
    return None


def main() -> None:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    known = {(w["tenant"], w["site"]) for w in cfg.get("workday", [])}

    tasks = [(group, t) for group, tenants in CANDIDATES.items() for t in tenants]
    print(f"probing {len(tasks)} candidate employers across {len(HOSTS)} Workday hosts...\n")

    found = []
    for entry in KNOWN:
        if (entry["tenant"], entry["site"]) not in known:
            cfg.setdefault("workday", []).append(entry)
            known.add((entry["tenant"], entry["site"]))
            print(f"  + [verified] {entry['name']}")

    with ThreadPoolExecutor(max_workers=12) as pool:
        for (group, tenant), hit in zip(tasks, pool.map(lambda x: find(x[1]), tasks)):
            if not hit or (hit["tenant"], hit["site"]) in known:
                continue
            hit["name"] = tenant
            hit["group"] = group
            if group == "nationwide":
                hit["nationwide"] = True
            found.append(hit)
            print(f"  + [{group}] {tenant:<22} {hit['wd']}/{hit['site']:<22} {hit['total']:>6} postings")

    for hit in found:
        total, group = hit.pop("total"), hit.pop("group")
        cfg.setdefault("workday", []).append(hit)

    CFG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"\n{len(found)} new Workday boards added. "
          f"workday roster is now {len(cfg.get('workday', []))}.")


if __name__ == "__main__":
    main()
