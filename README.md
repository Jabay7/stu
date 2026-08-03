# STU

Entry-level jobs — internships, new-grad roles and 0–3 YOE positions — for
**every major**, pulled straight from employer job boards and refreshed nightly.
Paste your syllabus and it ranks postings by the skills your classes actually
taught, and reminds you what's due.

Live: **https://jabay7.github.io/stu/**

---

## Why this exists

Every big job site buries entry-level roles under thousands of senior postings,
the "0 years experience" filter is famously wrong, and the open-source
alternatives are giant unfiltered README tables that only ever cover software.

STU answers what someone looking for a first job actually asks:

1. Is this really entry-level, or is it "entry-level, 5 years required"?
2. Is it anywhere near me?
3. Can *I* apply — or does it require being enrolled somewhere right now?
4. Will they sponsor a visa — or have they explicitly ruled it out?
5. Am I actually qualified, given the classes I've taken?

## Who it's for

Not only current students. Every posting is tagged with who can actually apply,
because that fact is almost never in the job title:

| Audience | Meaning |
|---|---|
| **Current students** | Requires active enrolment — internships, co-ops, practicums |
| **New grads** | Requires a recent degree — new-grad programs, nurse residencies |
| **Open to the public** | Anyone. "No experience necessary", "we'll train", "high school diploma" |

That last category is what makes STU useful to career changers and people who
aren't in school at all. A *Pharmacy Technician* posting saying "no prior
experience required, paid training provided" has no junior-sounding word in its
title, and every keyword-based board misses it.

## Nationwide

All 50 states and DC are selectable, and states with no current postings are
shown with a zero rather than hidden — an empty Wyoming is a true answer, and
hiding it would look like the filter is broken.

Coverage comes from two directions: regional employers (a health system or state
university in a given state) and nationwide chains swept state by state.
Workday's search covers location text as well as titles, so an employer flagged
`"nationwide"` in the roster gets queried once per state — the only way a chain
with 18,000 postings yields anything outside its biggest metros.

## How it works

```
181 employer boards        Greenhouse · Ashby · Lever · SmartRecruiters · Workday
        │
        ▼
scripts/fetch_jobs.py      entry-level filter, major tagging, skill extraction
        │
        ▼
data/jobs.json             ~300 roles, committed to the repo
        │
        ▼
static PWA + Capacitor     filters, coursework matching, reminders, offline
```

No server, no database. The web app is static files hosted free on GitHub Pages;
the phone app is the same code wrapped natively.

### No scraping

All five platforms publish documented public JSON APIs per employer — the same
endpoints their own careers pages call. Nothing parses HTML, so nothing breaks
when a careers page is restyled, and there's no bot-blocking to fight, unlike
scraping LinkedIn or Indeed.

Workday is what makes non-CS majors possible: hospitals, universities and
government post there, and tech ATSes simply don't carry those jobs. Three
quirks shaped the adapter — `limit` caps at 20, `postedOn` is prose
("Posted 30+ Days Ago") rather than a date, and descriptions need a second
request per job. So STU queries by entry-level keyword instead of paging
18,000 postings, and only fetches a description once a title already looks junior.

### Majors

Seventeen majors across STEM, Health, Business, Social and Creative, defined in
`scripts/taxonomy.json`. Adding one is a data edit — no code change. A job can
belong to several (a nurse practitioner fellowship is both Nursing and Pre-Med).

### What the classifier derives

| Signal | How |
|---|---|
| Entry-level | Strong title markers (intern, new grad, campus, nurse residency) beat seniority words, so *Associate Product Manager, New Grad* survives while *Senior Engineer II* is dropped |
| Years required | Smallest count mentioned near "experience"; ≥ 4 is rejected as a mislabelled senior role |
| Sponsorship | Explicit refusal vs explicit offer, ignoring the many false uses — "executive sponsorship", "sponsorship marketing" |
| Licence | Flags roles needing an active RN/NP/MD licence — the clinical equivalent of "5 years required" |
| Skills | Coursework vocabulary found in the posting, which is what syllabus matching compares against |

**On sponsorship, one honest note:** almost no employer advertises that it *will*
sponsor, while plenty state that they won't. So "Sponsor-friendly" hides only
roles that have explicitly ruled it out. It is not a promise that the rest will.

## Syllabus matching

Paste a syllabus on the Syllabus tab. Everything is parsed in the browser — a
syllabus is a personal document and there is no server here to send it to.

STU pulls out three things:

- **Course codes** — `NURS 310`, `BIOL 2010`
- **Skills** — matched against the same vocabulary used to tag jobs, so overlap
  is meaningful rather than fuzzy string similarity
- **Due dates** — assignment/exam lines with a date, with the year inferred
  (a date more than four months past means next year, not this one)

Turning on **Best match** ranks jobs by how much of their required skill set your
coursework already covers, normalised so a posting listing 3 skills and matching
all 3 beats one listing 14 and matching 4. Every match shows *why* it ranked.

### Reminders

Due dates become notifications the day before at 9am.

- **Installed app:** real scheduled OS notifications via Capacitor, which fire
  whether or not the app is open.
- **Web:** browsers can't reliably run background alarms, so STU alerts you about
  imminent work when you open it. The UI says so rather than implying otherwise.

## The nightly refresh

`.github/workflows/refresh.yml` runs at 07:10 UTC (2:10am Chicago):
re-fetch all 181 boards → rewrite `data/jobs.json` → commit and push only if
something changed → Pages redeploys itself. If every board fails, the script
exits without overwriting, so the app keeps yesterday's listings rather than
publishing an empty page.

You can also trigger it by hand from the Actions tab.

## Building the phone app

The project is developed on Windows without Node or the Android SDK, so the
native builds happen in CI.

**Android** — run the *Build Android app* workflow (or push a `v*` tag). It
collects `www/`, adds the Capacitor Android platform, builds, and uploads an
installable APK as an artifact. Tagged runs also attach it to a Release.

**iOS** — requires macOS and Xcode, which cannot be done from Windows. The
Capacitor config is ready; the remaining steps are yours:

1. Apple Developer Program — $99/year, and only you can create it
2. On a Mac: `npm install && npx cap add ios && npx cap sync ios`
3. Open `ios/App/App.xcworkspace`, set the signing team, archive, upload

**One thing to know before paying the fee:** App Review guideline 4.2 rejects
apps that are mainly aggregated web content. The syllabus reader and local
notifications are the native functionality that argues against that reading, but
approval is not guaranteed. The Android and web versions have no such gate.

## Adding employers

One entry in `scripts/companies.json`. Token-based platforms take a string;
Workday takes `{tenant, wd, site, name}` read off the careers URL
`https://TENANT.WD.myworkdayjobs.com/SITE`.

```bash
uv run scripts/discover_companies.py   # probes candidates, keeps what responds
```

## Running locally

```bash
uv run scripts/fetch_jobs.py     # refresh data/ (several minutes -- Workday is slow)
python -m http.server 8765       # then open http://127.0.0.1:8765
```

```bash
uv run scripts/make_icons.py     # app icons, writes PNG bytes directly, no deps
uv run scripts/make_og.py        # social card (Pillow, build-time only)
uv run scripts/build_www.py      # collect web assets for the native build
```

## Limitations

- **All 51 locations are selectable, but 34 currently have postings.** The rest
  show a zero. That's an employer-roster gap, not a filter bug — the fix is
  adding employers in those states (mostly AK, HI, MT, ND, NE, NM, NV, WY and
  a few New England states), which is one line each in `companies.json`.
- **Coverage is 191 employers, not the whole market.** Deep on tech, health
  systems and universities; thin on government, K-12, and non-US employers.
- **Facility-named locations rely on the employer's home state.** Health systems
  post to "Cobb Hospital" rather than a city, so single-state employers carry a
  `state` in the roster and multi-state chains are left unresolved rather than
  guessed at.
- **Volume is seasonal.** New-grad and internship postings land August–November.
- **Some majors are still thin.** Environmental Science and Public Health have
  very few postings — the honest fix is more employers, not looser matching.
- **The classifier is heuristic.** It will occasionally miss an oddly-titled role
  or admit one that's really mid-level.
- **PDF syllabi aren't parsed yet** — paste the text instead. The app says so
  rather than failing silently.

## Layout

```
index.html  styles.css  app.js  syllabus.js   the app
sw.js  manifest.webmanifest                   offline + installability
data/jobs.json  meta.json  taxonomy.json      generated; committed so Pages serves them
scripts/fetch_jobs.py                         orchestrator
scripts/sources.py                            the five ATS adapters
scripts/classify.py                           entry-level, majors, skills, sponsorship
scripts/taxonomy.json                         majors and coursework vocabulary
scripts/companies.json                        the employer roster
scripts/build_www.py  make_icons.py  make_og.py
capacitor.config.json  package.json           native wrapper
.github/workflows/refresh.yml                 nightly data job
.github/workflows/android.yml                 APK build
```
