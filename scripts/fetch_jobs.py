# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Build data/jobs.json from every configured employer board.

Orchestration only -- the API adapters live in sources.py and the classification
rules in classify.py + taxonomy.json.

Run:  uv run scripts/fetch_jobs.py
Out:  data/jobs.json, data/meta.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import classify
from classify import (CLEARANCE, audience, is_entry_level, majors_for, min_years,
                      parse_location, requires_license, skills_in, sponsorship)
from sources import FETCHERS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# No single employer may dominate the board. One delivery company posting 800
# near-identical warehouse roles would otherwise bury every other field -- the
# same failure as letting health systems crowd out everything else, just with a
# different employer. Newest kept, rest dropped.
#
# Set against the size of the board: too low and a large employer's genuinely
# varied openings get thrown away, which is its own kind of waste.
PER_EMPLOYER_CAP = 60


# Where postings are lost. Printed at the end of every run so a sudden drop in
# yield points at the stage responsible instead of being a mystery.
REJECTED: Counter = Counter()


def build(raw: dict) -> dict | None:
    REJECTED["seen"] += 1
    title = " ".join((raw.get("title") or "").split())
    url = raw.get("url") or ""
    if not title or not url:
        REJECTED["no title/url"] += 1
        return None

    desc = raw.get("description") or ""
    role = is_entry_level(title, desc)
    if not role:
        REJECTED["not entry level"] += 1
        return None

    majors = majors_for(title, raw.get("dept", ""))
    if not majors:
        REJECTED["no major matched"] += 1
        return None

    yoe = min_years(desc)
    if yoe is not None and yoe >= 4:
        REJECTED["asks 4+ years"] += 1
        return None

    loc = parse_location(raw.get("location_raw", ""), raw.get("remote_hint", False))
    if not loc["state"] and raw.get("default_state") and not loc["remote"]:
        loc["state"] = raw["default_state"]
        loc["us"] = True
    company = (raw.get("company") or "").strip() or raw.get("source", "")

    return {
        "id": f"{raw['source']}:{abs(hash((company, title, loc['location'], url))) % 10**10}",
        "company": company,
        "title": title[:120],
        "url": url,
        "majors": majors,
        "role": role,
        "audience": audience(role, desc),
        "yoe": yoe,
        "sponsor": sponsorship(desc),
        "clearance": bool(CLEARANCE.search(desc)),
        "license": requires_license(desc),
        "skills": skills_in(f"{title} {desc}"),
        "posted": raw.get("posted"),
        "days": raw.get("days"),
        "source": raw["source"],
        **loc,
    }


def targets(cfg: dict) -> list[tuple[str, object, str]]:
    """(source, spec, display) for everything configured."""
    out = []
    for source in FETCHERS:
        for spec in cfg.get(source, []):
            label = spec if isinstance(spec, str) else spec.get("name") or spec.get("tenant")
            out.append((source, spec, f"{source}/{label}"))
    return out


def main() -> int:
    cfg = json.loads((ROOT / "scripts" / "companies.json").read_text(encoding="utf-8"))
    jobs: list[dict] = []
    ok, failed = [], []

    def run(t):
        source, spec, label = t
        try:
            return label, FETCHERS[source](spec), None
        except Exception as exc:  # one dead board must never sink the run
            return label, [], f"{type(exc).__name__}: {str(exc)[:90]}"

    all_targets = targets(cfg)
    print(f"fetching {len(all_targets)} employer boards across {len(FETCHERS)} platforms...\n")

    with ThreadPoolExecutor(max_workers=10) as pool:
        for label, rows, err in pool.map(run, all_targets):
            if err:
                failed.append(f"{label}: {err}")
                print(f"  !! {label}: {err}", file=sys.stderr)
                continue
            ok.append(label)
            kept = [j for j in (build(r) for r in rows) if j]
            jobs.extend(kept)
            if kept:
                print(f"  {label}: {len(kept)} entry-level")

    # Dedup. The same role is often posted once per facility -- one health system
    # had the same nurse residency listed seven times. Collapse to a single entry
    # and record how many other locations it covers, rather than showing seven
    # near-identical cards.
    by_role: dict[tuple, dict] = {}
    for j in sorted(jobs, key=lambda x: (x["days"] is None, x["days"] or 0)):
        key = (j["company"].lower(), j["title"].lower())
        if key in by_role:
            existing = by_role[key]
            if j["location"].lower() != existing["location"].lower():
                existing["other_locations"] = existing.get("other_locations", 0) + 1
                if not existing["state"] and j["state"]:
                    existing["state"] = j["state"]     # keep the first resolvable state
            continue
        j["other_locations"] = 0
        by_role[key] = j
    unique = list(by_role.values())

    per_employer: dict[str, int] = {}
    capped, dropped = [], 0
    for j in unique:                       # already sorted newest-first
        key = j["company"].lower()
        per_employer[key] = per_employer.get(key, 0) + 1
        if per_employer[key] > PER_EMPLOYER_CAP:
            dropped += 1
            continue
        capped.append(j)
    if dropped:
        over = sorted((c for c, n in per_employer.items() if n > PER_EMPLOYER_CAP),
                      key=lambda c: -per_employer[c])
        print(f"\ncapped {dropped} listing(s) at {PER_EMPLOYER_CAP}/employer: "
              + ", ".join(f"{c} ({per_employer[c]})" for c in over[:6]))
    unique = capped

    existing = DATA / "jobs.json"
    if not unique and existing.exists() and json.loads(existing.read_text(encoding="utf-8")):
        print("\n!! 0 jobs scraped but data already published -- keeping existing data")
        return 1

    DATA.mkdir(parents=True, exist_ok=True)
    existing.write_text(json.dumps(unique, separators=(",", ":"), ensure_ascii=False),
                        encoding="utf-8")

    by_major = {m["id"]: sum(1 for j in unique if m["id"] in j["majors"]) for m in classify.MAJORS}
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total": len(unique),
        "employers_ok": len(ok),
        "employers_failed": failed,
        "majors": [{"id": m["id"], "label": m["label"], "group": m["group"],
                    "count": by_major[m["id"]]} for m in classify.MAJORS],
        "by_role": {r: sum(1 for j in unique if j["role"] == r)
                    for r in ("internship", "new_grad", "entry")},
        "by_audience": {a: sum(1 for j in unique if j["audience"] == a)
                        for a in ("students", "grads", "open")},
        "by_state": dict(sorted(
            ((s, sum(1 for j in unique if j["state"] == s))
             for s in {j["state"] for j in unique if j["state"]}),
            key=lambda kv: -kv[1])),
        "by_source": {s: sum(1 for j in unique if j["source"] == s) for s in FETCHERS},
    }
    (DATA / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # The browser needs the same vocabulary to read a syllabus, so ship it rather
    # than duplicating the list in JS where the two would drift apart.
    (DATA / "taxonomy.json").write_text(json.dumps({
        "majors": [{"id": m["id"], "label": m["label"], "group": m["group"],
                    "skills": [lbl for lbl, _ in m["skills"]]} for m in classify.MAJORS],
        "skills": sorted(classify.ALL_SKILLS.keys()),
    }, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    seen = REJECTED.pop("seen", 0)
    print(f"\nfunnel: {seen} postings fetched")
    for reason, n in REJECTED.most_common():
        print(f"   -{n:>6}  {reason}  ({n * 100 // max(1, seen)}%)")
    print(f"   ={seen - sum(REJECTED.values()):>6}  passed filters")

    print(f"\n{len(unique)} unique entry-level roles from {len(ok)}/{len(all_targets)} boards")
    print(f"  by role:   {meta['by_role']}")
    print(f"  by source: {meta['by_source']}")
    print("  by major:  " + ", ".join(f"{m['label']}={m['count']}"
                                      for m in meta["majors"] if m["count"]))
    if failed:
        print(f"  {len(failed)} board(s) failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
