# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Probe candidate company tokens against all three ATS APIs, keep the live ones.

Most companies use their own name as the board token, so guessing and verifying
is cheaper than hand-maintaining a list. Anything that answers with real postings
gets merged into scripts/companies.json; everything else is silently dropped.

Run:  uv run scripts/discover_companies.py
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / "scripts" / "companies.json"
UA = {"User-Agent": "stu-jobboard/1.0 (student project)"}

# Deliberately spread across industries, not just software. STU covers every
# major, so the roster has to include the employers that hire marketers,
# accountants, designers, teachers, HR and legal -- not only engineers.
CANDIDATES = """
1password 8x8 abnormal addepar adobe affinity affirm airbnb airtable airwallex alchemy
alloy alma altruist amplitude anaplan angi anthropic applovin arcadia articulate assembled
attentive aurora automattic axon benchling betterment bevy bill bitgo blend block bolt
box braze brex bungie calm carta cedar chainalysis chime circle clari clickup cloudflare
coalition cockroachlabs cohere coinbase collectivehealth color confluent coursera crusoeenergy
databricks datadog dbtlabs deepgram discord discordapp doximity drata dropbox duolingo
earnin elastic envoy equipmentshare everlaw evolveip faire fanatics fastly figma figment
fivetran flexport forter foursquare gemini gitlab gong grafanalabs grammarly greenhouse
gusto handshake harvey headway hims hinge hopper huggingface iterable imprint instabase
instacart intercom invisible jerry jumpcloud justworks kandji khanacademy klaviyo kong
komodohealth kraken lattice launchdarkly leetcode lithic lucid lyft mercury mixpanel
modernhealth moloco mongodb motive narvar netlify newfront niantic nuro nylas oaknorth
observeai okta olo openphone opendoor oscarhealth outreach pachama pagerduty
panther patreon peloton pendo persona philo pilot pinterest planet plusai pocketgems
postman primer quora ramp rarible recharge reddit remitly replit retool rippling
roblox robinhood rockset roku rubrik samsara scaleai scribd seatgeek semgrep sendbird
sentry shieldai sigmacomputing skydio smartsheet snyk sofi sonder sourcegraph spothero
sprig starburst strava stripe stubhub superhuman tala tecton temporal thumbtack tinder
tonal tripadvisor twilio udemy unity upstart upwork verkada via viam vimeo warbyparker
wealthfront webflow whatnot whoop wiz workato yelp zapier zip zipline zocdoc zoox

allbirds glossier away casper chewy wayfair etsy poshmark thredup renttherunway
stitchfix gopuff doordash grubhub sweetgreen cava shakeshack toasttab resy opentable
marqeta stash acorns current varo brigit plaid adyen wise klarna figure angellist
forge public betterment titan alpaca

netflix hulu vimeo substack medium buzzfeed vox theathletic nytimes condenast hearst
paramount a24 blizzard riotgames epicgames ea zynga scopely niantic twitch dropout

convoy project44 shipbob flocksafety joby archer rivian nikola proterra
redwoodmaterials formenergy boomsupersonic relativityspace firefly astranis

chegg quizlet outschool guild commonapp teachforamerica donorschoose charitywater
kiva newsela nearpod paper varsitytutors

hubspot mailchimp sproutsocial later hootsuite semrush similarweb vidyard
wistia sprinklr yext

compass zillow redfin vacasa latch procore buildertrend cushmanwakefield

lemonade root hippo nextinsurance coalition kin branch newfront

ironclad evisort checkr deel remote oyster cultureamp 15five bamboohr

palmetto aurorasolar watershed persefoni sila crusoe electrichydrogen
"""

SOURCES = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{t}",
    "lever": "https://api.lever.co/v0/postings/{t}?mode=json",
}


def count_jobs(source: str, token: str) -> int:
    url = SOURCES[source].format(t=token)
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return 0
    if source == "lever":
        return len(data) if isinstance(data, list) else 0
    return len(data.get("jobs", []) or [])


def probe(token: str) -> tuple[str, str, int] | None:
    """First source that returns postings wins -- companies rarely use two."""
    for source in SOURCES:
        n = count_jobs(source, token)
        if n > 0:
            return source, token, n
    return None


def main() -> None:
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    known = {t for src in SOURCES for t in cfg.get(src, [])}
    candidates = sorted({w.strip() for w in CANDIDATES.split() if w.strip()} - known)
    print(f"probing {len(candidates)} candidate tokens across 3 ATS platforms...\n")

    hits: list[tuple[str, str, int]] = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        for result in pool.map(probe, candidates):
            if result:
                source, token, n = result
                hits.append(result)
                print(f"  + {source:<11} {token:<20} {n:>4} postings")

    for source, token, _ in hits:
        cfg.setdefault(source, [])
        if token not in cfg[source]:
            cfg[source].append(token)
    for source in SOURCES:
        cfg[source] = sorted(set(cfg.get(source, [])))

    CFG.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    total = sum(len(cfg[s]) for s in SOURCES)
    print(f"\n{len(hits)} new boards found. companies.json now tracks {total}:")
    for s in SOURCES:
        print(f"  {s}: {len(cfg[s])}")


if __name__ == "__main__":
    main()
