# STU

Entry-level tech jobs — internships, new-grad roles, and 0–3 YOE positions —
pulled straight from company job boards and refreshed every night.

Installable to a phone home screen, works offline, no accounts, no backend.

---

## Why this exists

Every big job site buries entry-level roles under thousands of senior postings,
and the "0 years experience" filter on LinkedIn is famously wrong. The
open-source alternatives are giant unfiltered README tables.

STU answers the three questions a graduating student actually has:

1. Is this really entry-level, or is it "entry-level, 5 years required"?
2. Will they sponsor a visa — or have they explicitly ruled it out?
3. Was this posted recently enough to be worth applying to?

## How it works

```
159 company job boards          Greenhouse / Ashby / Lever public JSON APIs
          │
          ▼
scripts/fetch_jobs.py           filter to entry-level, classify, dedupe
          │
          ▼
data/jobs.json                  ~60 roles, committed to the repo
          │
          ▼
static PWA (index.html)         filters, search, saved/applied, offline
```

There is no server and no database. The whole app is static files, so it hosts
free on GitHub Pages and cannot go down under load.

### No scraping

Greenhouse, Ashby and Lever each publish a documented public JSON endpoint per
company board. That's the entire data source. Nothing here parses HTML, so
nothing breaks when a careers page gets restyled, and there's no bot-blocking to
fight — unlike scraping LinkedIn or Indeed, which is both fragile and against
their terms.

### What the classifier does

Raw postings don't say "this is entry-level" in a machine-readable field, so
`fetch_jobs.py` derives it:

| Signal | How |
|---|---|
| Entry-level | Strong title markers (intern, new grad, campus, apprentice) beat seniority words, so *Associate Product Manager, New Grad* survives while *Senior Engineer II* is dropped |
| Years required | Smallest year-count mentioned near the word "experience"; anything ≥ 4 is rejected as a mislabelled senior role |
| Sponsorship | Explicit refusal ("unable to sponsor") vs explicit offer, with the many false uses of the word — "executive sponsorship", "sponsorship marketing" — deliberately ignored |
| Location | US state resolved from state names, `, XX` suffixes, or a major-city lookup |
| Clearance | Flags roles requiring a US security clearance |

Everything is transparent regex in one file — you can read exactly why any job
was included or excluded, which matters more than a black box getting it right
90% of the time.

**On sponsorship, one honest note:** almost no company advertises that it *will*
sponsor, while plenty state that they won't. So the useful filter is
"Sponsor-friendly", which hides only roles that have explicitly ruled sponsorship
out. It is not a promise that the rest will sponsor.

## The nightly refresh

`.github/workflows/refresh.yml` runs at 07:10 UTC (2:10am Chicago) every day:

1. Re-fetches all 159 boards
2. Rewrites `data/jobs.json`
3. Commits and pushes only if something actually changed
4. GitHub Pages redeploys automatically

If every board fails on a given night, the script exits without overwriting —
the app keeps yesterday's listings rather than publishing an empty page.

You can also trigger it by hand from the Actions tab ("Run workflow"), which is
the useful button during a demo.

## Adding companies

One line in `scripts/companies.json`, under whichever platform the company uses.
The nightly job picks it up with no other changes.

To find new ones automatically:

```bash
uv run scripts/discover_companies.py
```

That probes a candidate list against all three APIs and merges whatever responds
with real postings. The current roster of 159 was built this way.

## Running locally

```bash
uv run scripts/fetch_jobs.py     # refresh data/jobs.json
python -m http.server 8765       # then open http://127.0.0.1:8765
```

Images are generated, not hand-made:

```bash
uv run scripts/make_icons.py   # app icons, writes PNG bytes directly, no deps
uv run scripts/make_og.py      # social preview card (needs Pillow, build-time only)
```

## Install on a phone

Open the site in Chrome (Android) or Safari (iOS) and choose **Add to Home
Screen**. It launches full-screen with its own icon, and cached listings stay
readable with no signal.

## Limitations

- **Coverage is 159 companies, not the whole market.** It is deep on tech
  startups and scale-ups, thin on banks, defense, and non-US employers.
- **Volume is seasonal.** New-grad and internship postings for the following
  summer land between August and November; a count in the dozens during spring
  is expected, not a bug.
- **The classifier is heuristic.** It will occasionally miss an oddly-titled
  entry role or admit one that's really mid-level.
- **Sponsorship reflects what the posting says**, which is sometimes nothing.

## Layout

```
index.html  styles.css  app.js     the app
sw.js  manifest.webmanifest        offline + installability
data/jobs.json  data/meta.json     generated; committed so Pages can serve it
scripts/fetch_jobs.py              fetch + classify
scripts/discover_companies.py      find new company boards
scripts/companies.json             the roster
scripts/make_icons.py              PNG icons, no dependencies
scripts/make_og.py                 og-image.png social card
.github/workflows/refresh.yml      the nightly job
```

## Note on the nightly job

Pushing `.github/workflows/` requires a GitHub token with the `workflow` scope.
If a push is rejected with *"refusing to allow an OAuth App to create or update
workflow"*, run:

```bash
gh auth refresh -s workflow
```

That's a browser authorization step, so it has to be done by hand once.
