/* STU -- all client-side. The data is a static JSON file the nightly job rewrites. */

const $ = (sel) => document.querySelector(sel);

const state = {
  jobs: [],
  meta: null,
  query: "",
  filters: new Set(),
  tab: "browse",
  saved: new Set(JSON.parse(localStorage.getItem("stu.saved") || "[]")),
  applied: new Set(JSON.parse(localStorage.getItem("stu.applied") || "[]")),
};

const persist = () => {
  localStorage.setItem("stu.saved", JSON.stringify([...state.saved]));
  localStorage.setItem("stu.applied", JSON.stringify([...state.applied]));
};

/* ------------------------------------------------------------------ format */

const ago = (iso) => {
  if (!iso) return "";
  const mins = Math.floor((Date.now() - new Date(iso)) / 60000);
  if (mins < 60) return `${Math.max(1, mins)}m ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
};

const postedLabel = (d) => {
  if (d === null || d === undefined) return null;
  if (d <= 1) return "today";
  if (d < 7) return `${d}d ago`;
  if (d < 30) return `${Math.floor(d / 7)}w ago`;
  return `${Math.floor(d / 30)}mo ago`;
};

const ROLE_LABEL = { internship: "Internship", new_grad: "New grad", entry: "Entry level" };

const esc = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

/* ----------------------------------------------------------------- filters */

function visible() {
  const q = state.query.trim().toLowerCase();
  const f = state.filters;

  return state.jobs.filter((j) => {
    if (state.tab === "saved" && !state.saved.has(j.id)) return false;
    if (state.tab === "applied" && !state.applied.has(j.id)) return false;

    if (q) {
      const hay = `${j.title} ${j.company} ${j.location} ${j.category}`.toLowerCase();
      if (!q.split(/\s+/).every((word) => hay.includes(word))) return false;
    }

    if (f.has("internship") && j.role !== "internship") return false;
    if (f.has("new_grad") && j.role !== "new_grad") return false;
    // "Sponsor-friendly" means: has not explicitly ruled sponsorship out.
    if (f.has("sponsor") && j.sponsor === "no") return false;
    if (f.has("remote") && !j.remote) return false;
    if (f.has("chicago") && j.state !== "IL") return false;
    if (f.has("fresh") && !(j.days !== null && j.days <= 7)) return false;
    if (f.has("noclearance") && j.clearance) return false;

    return true;
  });
}

/* ------------------------------------------------------------------ render */

function cardHTML(j) {
  const badges = [];
  if (j.days !== null && j.days <= 3) badges.push(`<span class="badge new">New</span>`);
  if (j.role) badges.push(`<span class="badge role">${ROLE_LABEL[j.role]}</span>`);
  if (j.remote) badges.push(`<span class="badge remote">${j.hybrid ? "Hybrid" : "Remote"}</span>`);
  if (j.sponsor === "no") badges.push(`<span class="badge nospon">No sponsorship</span>`);
  if (j.sponsor === "yes") badges.push(`<span class="badge spon">Sponsors visa</span>`);
  if (j.clearance) badges.push(`<span class="badge clear">Clearance</span>`);
  if (j.yoe !== null && j.yoe !== undefined) badges.push(`<span class="badge">${j.yoe}+ yrs</span>`);

  const when = postedLabel(j.days);
  const meta = [`<span class="co">${esc(j.company)}</span>`, esc(j.location)];
  if (when) meta.push(when);

  return `
    <article class="card${state.applied.has(j.id) ? " is-applied" : ""}" data-id="${j.id}" data-url="${esc(j.url)}">
      <div class="logo" aria-hidden="true">${esc(j.company.slice(0, 1))}</div>
      <div>
        <h2><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a></h2>
        <p class="meta">${meta.join("<span aria-hidden=\"true\">·</span>")}</p>
        <div class="badges">${badges.join("")}</div>
      </div>
      <div class="actions">
        <button class="act" data-act="save" aria-pressed="${state.saved.has(j.id)}" aria-label="Save" title="Save">
          <svg viewBox="0 0 24 24"><path d="M6 4h12v16l-6-4-6 4z" fill="${state.saved.has(j.id) ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>
        </button>
        <button class="act" data-act="applied" aria-pressed="${state.applied.has(j.id)}" aria-label="Mark applied" title="Mark applied">
          <svg viewBox="0 0 24 24"><path d="M4 12.5 9 17.5 20 6.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>
    </article>`;
}

function render() {
  const rows = visible();
  const list = $("#list");
  const empty = $("#empty");

  list.innerHTML = rows.map(cardHTML).join("");
  empty.hidden = rows.length > 0;
  list.hidden = rows.length === 0;

  $("#savedCount").textContent = state.saved.size ? state.saved.size : "";
  $("#appliedCount").textContent = state.applied.size ? state.applied.size : "";

  if (state.meta) {
    const n = rows.length;
    const total = state.jobs.length;
    const shown = n === total ? `${total} roles` : `${n} of ${total} roles`;
    $("#subtitle").textContent =
      `${shown} · ${state.meta.companies_ok} companies · updated ${ago(state.meta.generated_at)}`;
  }
}

/* ------------------------------------------------------------------- data */

async function load() {
  const btn = $("#refreshBtn");
  btn.classList.add("spin");
  try {
    const bust = `?v=${Date.now()}`;
    const [jobs, meta] = await Promise.all([
      fetch(`data/jobs.json${bust}`).then((r) => r.json()),
      fetch(`data/meta.json${bust}`).then((r) => r.json()),
    ]);
    state.jobs = jobs;
    state.meta = meta;
    render();
  } catch (err) {
    $("#subtitle").textContent = "Offline — showing what was cached";
    console.error(err);
  } finally {
    btn.classList.remove("spin");
  }
}

/* ------------------------------------------------------------------ events */

$("#search").addEventListener("input", (e) => {
  state.query = e.target.value;
  render();
});

$("#chips").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  const key = chip.dataset.filter;
  if (state.filters.has(key)) state.filters.delete(key);
  else state.filters.add(key);
  chip.setAttribute("aria-pressed", state.filters.has(key));
  render();
});

$("#list").addEventListener("click", (e) => {
  const card = e.target.closest(".card");
  if (!card) return;
  const act = e.target.closest(".act");

  if (act) {
    e.preventDefault();
    const set = act.dataset.act === "save" ? state.saved : state.applied;
    if (set.has(card.dataset.id)) set.delete(card.dataset.id);
    else set.add(card.dataset.id);
    persist();
    render();
    return;
  }

  // Anywhere else on the card opens the posting -- but let a real link click through.
  if (!e.target.closest("a")) {
    window.open(card.dataset.url, "_blank", "noopener");
  }
});

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    state.tab = tab.dataset.tab;
    document.querySelectorAll(".tab").forEach((t) => {
      const on = t === tab;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", on);
    });
    window.scrollTo({ top: 0 });
    render();
  });
});

$("#clearAll").addEventListener("click", () => {
  state.filters.clear();
  state.query = "";
  $("#search").value = "";
  document.querySelectorAll(".chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
  render();
});

$("#refreshBtn").addEventListener("click", load);

/* -------------------------------------------------------- install + offline */

let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  if (!localStorage.getItem("stu.installDismissed")) $("#install").hidden = false;
});

$("#installBtn").addEventListener("click", async () => {
  $("#install").hidden = true;
  if (deferredPrompt) {
    deferredPrompt.prompt();
    deferredPrompt = null;
  }
});

$("#installClose").addEventListener("click", () => {
  $("#install").hidden = true;
  localStorage.setItem("stu.installDismissed", "1");
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}

load();
