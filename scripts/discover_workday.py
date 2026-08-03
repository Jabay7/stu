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

HOSTS = ["wd1", "wd5", "wd3", "wd12", "wd101", "wd103"]
SITES = [
    "External", "external", "Careers", "careers", "Search", "search",
    "Jobs", "jobs", "ExternalCareerSite", "External_Career_Site",
    "CareerSite", "{t}careers", "{t}jobs", "{T}Careers", "{T}_Careers",
    "{t}Careers", "{t}Jobs", "{T}jobs", "{T}Jobs", "{t}_careers",
    "careersite", "CareerHome", "Career", "ExternalSite", "Recruiting",
]

# Verified by hand; site names like "OhioHealthJobs" and "targetcareers" don't
# follow any pattern worth guessing at.
KNOWN = [
    {"tenant": "target", "wd": "wd5", "site": "targetcareers", "name": "Target", "nationwide": True},
    {"tenant": "ohiohealth", "wd": "wd5", "site": "OhioHealthJobs", "name": "OhioHealth"},
    {"tenant": "bannerhealth", "wd": "wd5", "site": "Careers", "name": "Banner Health"},
]

# Grouped by the gap each one fills. Health systems and universities are the
# employers that actually exist in every state.
CANDIDATES = {
    "nationwide": ["target", "walgreens", "bestbuy", "nordstrom", "lowes", "publix", "aramark"],
    "FL": ["adventhealth", "orlandohealth", "leehealth", "moffitt", "jacksonhealth", "usf", "fiu"],
    "OH": ["ohiohealth", "nationwidechildrens", "trihealth", "premierhealth", "kent", "ohiostate"],
    "PA": ["upmc", "geisinger", "jefferson", "wellspan", "towerhealth", "temple", "psu"],
    "TN": ["vanderbilt", "balladhealth", "methodist", "utk"],
    "AZ": ["bannerhealth", "honorhealth", "asu", "arizona"],
    "MN": ["fairview", "allina", "hennepin", "umn", "mayoclinic"],
    "NC": ["novanthealth", "atriumhealth", "unchealth", "duke", "ncsu"],
    "MO": ["bjc", "mercy", "ssmhealth", "umsystem"],
    "LA": ["ochsner", "lsu", "tulane"],
    "OK": ["ouhealth", "saintfrancis", "okstate"],
    "IA": ["unitypoint", "mercyone", "uiowa"],
    "MS": ["umc", "msstate"],
    "AL": ["uab", "auburn", "usahealth"],
    "SC": ["prismahealth", "musc", "clemson", "sc"],
    "ID": ["stlukes", "boisestate"],
    "MT": ["billingsclinic", "benefis", "montana"],
    "ND": ["sanfordhealth", "ndus", "und"],
    "SD": ["avera", "sdstate"],
    "NE": ["nebraskamed", "chihealth", "unl"],
    "WV": ["wvumedicine", "wvu"],
    "VT": ["uvmhealth", "uvm"],
    "NH": ["dartmouth", "unh"],
    "RI": ["lifespan", "brownhealth", "uri"],
    "HI": ["queens", "hawaiipacifichealth", "hawaii"],
    "AK": ["southcentralfoundation", "alaska"],
    "NV": ["renown", "unlv", "nevada"],
    "NM": ["presbyterian", "unm"],
    "DE": ["christianacare", "udel"],
    "ME": ["mainehealth", "maine"],
    "DC": ["medstar", "childrensnational", "georgetown", "gwu"],
    "WY": ["cheyenneregional", "uwyo"],
    "IN": ["iuhealth", "indiana", "purdue"],
    "GA": ["wellstar", "piedmont", "emory", "gatech"],
    "VA": ["sentara", "vcu", "virginia"],
    "CO": ["uchealth", "centura", "colorado"],
    "UT": ["intermountain", "utah"],
    "OR": ["ohsu", "providence", "oregonstate"],
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
            site = template.format(t=tenant, T=tenant.capitalize())
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
