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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import classify
from classify import (LICENSE, CLEARANCE, is_entry_level, majors_for, min_years,
                      parse_location, skills_in, sponsorship)
from sources import FETCHERS

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def build(raw: dict) -> dict | None:
    title = " ".join((raw.get("title") or "").split())
    url = raw.get("url") or ""
    if not title or not url:
        return None

    desc = raw.get("description") or ""
    role = is_entry_level(title, desc)
    if not role:
        return None

    majors = majors_for(title, raw.get("dept", ""))
    if not majors:
        return None  # nothing a student could major in -- not useful here

    yoe = min_years(desc)
    if yoe is not None and yoe >= 4:
        return None  # "entry-level" asking 4+ years is a mislabelled senior role

    loc = parse_location(raw.get("location_raw", ""), raw.get("remote_hint", False))
    company = (raw.get("company") or "").strip() or raw.get("source", "")

    return {
        "id": f"{raw['source']}:{abs(hash((company, title, loc['location'], url))) % 10**10}",
        "company": company,
        "title": title[:120],
        "url": url,
        "majors": majors,
        "role": role,
        "yoe": yoe,
        "sponsor": sponsorship(desc),
        "clearance": bool(CLEARANCE.search(desc)),
        "license": bool(LICENSE.search(desc)),
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

    # Dedup -- the same role is often posted to several offices.
    seen, unique = set(), []
    for j in sorted(jobs, key=lambda x: (x["days"] is None, x["days"] or 0)):
        key = (j["company"].lower(), j["title"].lower(), j["location"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(j)

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
