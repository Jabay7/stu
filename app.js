/* STU -- all client-side. jobs.json is a static file the nightly job rewrites. */

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];

const store = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(`stu.${key}`)) ?? fallback; }
    catch { return fallback; }
  },
  set(key, value) { localStorage.setItem(`stu.${key}`, JSON.stringify(value)); },
};

const state = {
  jobs: [],
  meta: null,
  taxonomy: { majors: [], skills: [] },
  query: "",
  filters: new Set(),
  tab: "jobs",
  majors: new Set(store.get("majors", [])),
  syllabus: store.get("syllabus", null),
  saved: new Set(store.get("saved", [])),
  applied: new Set(store.get("applied", [])),
};

const persist = () => {
  store.set("saved", [...state.saved]);
  store.set("applied", [...state.applied]);
  store.set("majors", [...state.majors]);
  store.set("syllabus", state.syllabus);
};

/* ------------------------------------------------------------------ format */

const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

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

const dueLabel = (iso) => {
  const days = Math.round((new Date(iso) - Date.now()) / 86400000);
  if (days < 0) return { text: "past", tone: "past" };
  if (days === 0) return { text: "today", tone: "hot" };
  if (days === 1) return { text: "tomorrow", tone: "hot" };
  if (days <= 7) return { text: `in ${days} days`, tone: "soon" };
  return { text: new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" }), tone: "" };
};

const ROLE_LABEL = { internship: "Internship", new_grad: "New grad", entry: "Entry level" };
const majorLabel = (id) => (state.taxonomy.majors.find((m) => m.id === id) || {}).label || id;

/* ----------------------------------------------------------------- filters */

const skillSet = () => new Set(state.syllabus ? state.syllabus.skills : []);

function visibleJobs() {
  const q = state.query.trim().toLowerCase();
  const f = state.filters;
  const chosen = state.majors;
  const skills = skillSet();

  let rows = state.jobs.filter((j) => {
    if (chosen.size && !j.majors.some((m) => chosen.has(m))) return false;

    if (q) {
      const hay = `${j.title} ${j.company} ${j.location}`.toLowerCase();
      if (!q.split(/\s+/).every((w) => hay.includes(w))) return false;
    }

    if (f.has("internship") && j.role !== "internship") return false;
    if (f.has("new_grad") && j.role !== "new_grad") return false;
    if (f.has("sponsor") && j.sponsor === "no") return false;
    if (f.has("remote") && !j.remote) return false;
    if (f.has("nolicense") && j.license) return false;
    if (f.has("fresh") && !(j.days !== null && j.days <= 7)) return false;
    return true;
  });

  rows = rows.map((j) => ({ ...j, ...Syllabus.scoreJob(j, skills) }));

  if (f.has("match") && skills.size) {
    rows.sort((a, b) => b.score - a.score || (a.days ?? 999) - (b.days ?? 999));
  }
  return rows;
}

/* ------------------------------------------------------------------ render */

function cardHTML(j) {
  const badges = [];
  if (j.days !== null && j.days <= 3) badges.push(`<span class="badge new">New</span>`);
  if (j.role) badges.push(`<span class="badge role">${ROLE_LABEL[j.role]}</span>`);
  if (j.remote) badges.push(`<span class="badge remote">${j.hybrid ? "Hybrid" : "Remote"}</span>`);
  if (j.sponsor === "no") badges.push(`<span class="badge nospon">No sponsorship</span>`);
  if (j.sponsor === "yes") badges.push(`<span class="badge spon">Sponsors visa</span>`);
  if (j.license) badges.push(`<span class="badge lic">Licence required</span>`);
  if (j.clearance) badges.push(`<span class="badge clear">Clearance</span>`);

  const majors = j.majors.slice(0, 2).map((m) =>
    `<span class="badge major">${esc(majorLabel(m))}</span>`).join("");

  const when = postedLabel(j.days);
  const meta = [`<span class="co">${esc(j.company)}</span>`, esc(j.location)];
  if (when) meta.push(when);

  const match = j.overlap && j.overlap.length
    ? `<p class="match"><span class="dot"></span>Matches your coursework:
         ${j.overlap.slice(0, 4).map((s) => esc(s)).join(", ")}</p>`
    : "";

  return `
    <article class="card${state.applied.has(j.id) ? " is-applied" : ""}" data-id="${j.id}" data-url="${esc(j.url)}">
      <div class="logo" aria-hidden="true">${esc(j.company.slice(0, 1))}</div>
      <div class="cardbody">
        <h2><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a></h2>
        <p class="meta">${meta.join('<span aria-hidden="true">·</span>')}</p>
        <div class="badges">${majors}${badges.join("")}</div>
        ${match}
      </div>
      <div class="actions">
        <button class="act" data-act="save" aria-pressed="${state.saved.has(j.id)}" aria-label="Save">
          <svg viewBox="0 0 24 24"><path d="M6 4h12v16l-6-4-6 4z" fill="${state.saved.has(j.id) ? "currentColor" : "none"}" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>
        </button>
        <button class="act" data-act="applied" aria-pressed="${state.applied.has(j.id)}" aria-label="Mark applied">
          <svg viewBox="0 0 24 24"><path d="M4 12.5 9 17.5 20 6.5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
      </div>
    </article>`;
}

function render() {
  const rows = visibleJobs();
  $("#list").innerHTML = rows.map(cardHTML).join("");
  $("#empty").hidden = rows.length > 0;
  $("#list").hidden = rows.length === 0;

  const savedRows = state.jobs.filter((j) => state.saved.has(j.id));
  $("#savedList").innerHTML = savedRows.map(cardHTML).join("");
  $("#savedEmpty").hidden = savedRows.length > 0;

  $("#savedCount").textContent = state.saved.size || "";
  $("#jobCount").textContent = rows.length || "";
  $("#sylBadge").textContent = state.syllabus ? state.syllabus.skills.length : "";
  $("#matchChip").hidden = !state.syllabus;

  if (state.meta) {
    const scope = state.majors.size
      ? [...state.majors].map(majorLabel).slice(0, 2).join(" + ") +
        (state.majors.size > 2 ? ` +${state.majors.size - 2}` : "")
      : "all majors";
    $("#subtitle").textContent =
      `${rows.length} of ${state.meta.total} · ${scope} · updated ${ago(state.meta.generated_at)}`;
  }
}

/* -------------------------------------------------------------- major sheet */

function renderMajorSheet() {
  const groups = {};
  for (const m of state.taxonomy.majors) (groups[m.group] ||= []).push(m);

  const counts = Object.fromEntries(
    (state.meta?.majors || []).map((m) => [m.id, m.count]));

  $("#majorGrid").innerHTML = Object.entries(groups).map(([group, majors]) => `
    <div class="mgroup">
      <h3>${esc(group)}</h3>
      <div class="mopts">
        ${majors.map((m) => `
          <button class="mopt" data-major="${m.id}" aria-pressed="${state.majors.has(m.id)}">
            <span>${esc(m.label)}</span>
            <em>${counts[m.id] ?? 0}</em>
          </button>`).join("")}
      </div>
    </div>`).join("");
}

const openSheet = () => {
  renderMajorSheet();
  $("#majorSheet").hidden = false;
  $("#sheetBackdrop").hidden = false;
};
const closeSheet = () => {
  $("#majorSheet").hidden = true;
  $("#sheetBackdrop").hidden = true;
};

/* --------------------------------------------------------------- reminders */

const Reminders = {
  native() {
    return window.Capacitor?.Plugins?.LocalNotifications || null;
  },

  async enable(items) {
    const plugin = this.native();
    if (plugin) {
      const perm = await plugin.requestPermissions();
      if (perm.display !== "granted") return { ok: false, why: "Permission denied." };
      await this.schedule(items);
      return { ok: true, why: `Scheduled ${items.length} reminders.` };
    }

    if (!("Notification" in window)) return { ok: false, why: "This browser can't show notifications." };
    const perm = await Notification.requestPermission();
    if (perm !== "granted") return { ok: false, why: "Permission denied." };
    store.set("remind", true);
    this.checkOnOpen(items);
    return {
      ok: true,
      // Say what it actually does rather than implying background alarms.
      why: "On the web STU can only alert you while it's open. The installed app fires reminders on its own.",
    };
  },

  async schedule(items) {
    const plugin = this.native();
    if (!plugin) return;
    const pending = (await plugin.getPending()).notifications || [];
    if (pending.length) await plugin.cancel({ notifications: pending });

    const upcoming = items
      .filter((i) => new Date(i.due) > Date.now())
      .slice(0, 60)
      .map((i, idx) => {
        const at = new Date(i.due);
        at.setDate(at.getDate() - 1);   // the day before
        at.setHours(9, 0, 0, 0);
        return {
          id: idx + 1,
          title: "Due tomorrow",
          body: i.title,
          schedule: { at: at > new Date() ? at : new Date(Date.now() + 60000) },
        };
      });
    if (upcoming.length) await plugin.schedule({ notifications: upcoming });
  },

  checkOnOpen(items) {
    if (!store.get("remind", false)) return;
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const soon = items.filter((i) => {
      const h = (new Date(i.due) - Date.now()) / 3600000;
      return h > 0 && h < 36;
    });
    const alerted = new Set(store.get("alerted", []));
    for (const i of soon) {
      const key = `${i.title}|${i.due}`;
      if (alerted.has(key)) continue;
      alerted.add(key);
      new Notification("Due soon", { body: i.title, icon: "icons/icon-192.png" });
    }
    store.set("alerted", [...alerted]);
  },
};

/* ---------------------------------------------------------------- syllabus */

function renderSyllabus() {
  const s = state.syllabus;
  $("#syllabusResult").hidden = !s;
  $("#clearSyl").hidden = !s;
  $("#remindBox").hidden = !s || !s.due.length;
  if (!s) return;

  $("#courseCount").textContent = s.courses.length;
  $("#courseList").innerHTML = s.courses.length
    ? s.courses.map((c) => `<span class="tag">${esc(c)}</span>`).join("")
    : `<p class="note">No course codes spotted — that's fine, skills still matched.</p>`;

  $("#skillCount").textContent = s.skills.length;
  $("#skillList").innerHTML = s.skills.length
    ? s.skills.slice(0, 40).map((k) => `<span class="tag on">${esc(k)}</span>`).join("")
    : `<p class="note">No known skills found. Paste more of the syllabus — the topics list and weekly schedule help most.</p>`;

  const upcoming = s.due.filter((i) => new Date(i.due) >= Date.now() - 86400000);
  $("#dueCount").textContent = upcoming.length;
  $("#dueList").innerHTML = upcoming.length
    ? upcoming.map((i) => {
        const d = dueLabel(i.due);
        return `<div class="due">
          <span class="duekind">${esc(i.kind)}</span>
          <span class="duetitle">${esc(i.title)}</span>
          <span class="duewhen ${d.tone}">${esc(d.text)}</span>
        </div>`;
      }).join("")
    : `<p class="note">No dated assignments found. Paste the weekly schedule — lines like “Oct 14 — Midterm exam”.</p>`;

  $("#remindNote").textContent = Reminders.native()
    ? "Get a notification the day before each due date."
    : "Installed as an app, STU can notify you the day before each due date.";
}

function readSyllabus(text) {
  const note = $("#parseNote");
  note.hidden = false;

  if (text.startsWith("%PDF")) {
    note.textContent = "That's a raw PDF — STU can't read PDF text yet. Open it, select all, and paste the text instead.";
    return;
  }
  if (text.trim().length < 40) {
    note.textContent = "That's too short to read. Paste the full syllabus.";
    return;
  }

  state.syllabus = Syllabus.parse(text, state.taxonomy.skills);
  if (state.syllabus.skills.length) state.filters.add("match");
  persist();

  renderSyllabus();
  $$(".chip").forEach((c) => c.setAttribute("aria-pressed", state.filters.has(c.dataset.filter)));
  render();

  const s = state.syllabus;
  note.textContent = `Read ${s.chars.toLocaleString()} characters — ${s.skills.length} skills, ${s.due.length} dated items.`;
}

/* ------------------------------------------------------------------- data */

async function load() {
  try {
    const bust = `?v=${Date.now()}`;
    const [jobs, meta, taxonomy] = await Promise.all([
      fetch(`data/jobs.json${bust}`).then((r) => r.json()),
      fetch(`data/meta.json${bust}`).then((r) => r.json()),
      fetch(`data/taxonomy.json${bust}`).then((r) => r.json()),
    ]);
    state.jobs = jobs;
    state.meta = meta;
    state.taxonomy = taxonomy;

    renderSyllabus();
    render();

    if (!store.get("onboarded", false)) {
      openSheet();
      store.set("onboarded", true);
    }
    if (state.syllabus) Reminders.checkOnOpen(state.syllabus.due);
  } catch (err) {
    $("#subtitle").textContent = "Offline — showing what was cached";
    console.error(err);
  }
}

/* ----------------------------------------------------------------- events */

$("#search").addEventListener("input", (e) => { state.query = e.target.value; render(); });

$("#chips").addEventListener("click", (e) => {
  const chip = e.target.closest(".chip");
  if (!chip) return;
  const key = chip.dataset.filter;
  state.filters.has(key) ? state.filters.delete(key) : state.filters.add(key);
  chip.setAttribute("aria-pressed", state.filters.has(key));
  render();
});

function cardClick(e) {
  const card = e.target.closest(".card");
  if (!card) return;
  const act = e.target.closest(".act");
  if (act) {
    e.preventDefault();
    const set = act.dataset.act === "save" ? state.saved : state.applied;
    set.has(card.dataset.id) ? set.delete(card.dataset.id) : set.add(card.dataset.id);
    persist();
    render();
    return;
  }
  if (!e.target.closest("a")) window.open(card.dataset.url, "_blank", "noopener");
}
$("#list").addEventListener("click", cardClick);
$("#savedList").addEventListener("click", cardClick);

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    state.tab = tab.dataset.tab;
    $$(".tab").forEach((t) => {
      const on = t === tab;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", on);
    });
    $("#jobsPane").hidden = state.tab !== "jobs";
    $("#syllabusPane").hidden = state.tab !== "syllabus";
    $("#savedPane").hidden = state.tab !== "saved";
    $$("[data-pane='jobs']").forEach((el) => { el.hidden = state.tab !== "jobs"; });
    window.scrollTo({ top: 0 });
    render();
  });
});

$("#clearAll").addEventListener("click", () => {
  state.filters.clear();
  state.query = "";
  $("#search").value = "";
  $$(".chip").forEach((c) => c.setAttribute("aria-pressed", "false"));
  render();
});

/* major sheet */
$("#majorBtn").addEventListener("click", openSheet);
$("#sheetClose").addEventListener("click", closeSheet);
$("#sheetBackdrop").addEventListener("click", closeSheet);
$("#majorDone").addEventListener("click", closeSheet);
$("#majorAll").addEventListener("click", () => {
  state.majors.clear();
  persist();
  renderMajorSheet();
  render();
});
$("#majorGrid").addEventListener("click", (e) => {
  const opt = e.target.closest(".mopt");
  if (!opt) return;
  const id = opt.dataset.major;
  state.majors.has(id) ? state.majors.delete(id) : state.majors.add(id);
  opt.setAttribute("aria-pressed", state.majors.has(id));
  persist();
  render();
});

/* syllabus */
$("#parseBtn").addEventListener("click", () => readSyllabus($("#syllabusText").value));
$("#syllabusFile").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  const text = await file.text();
  $("#syllabusText").value = text.slice(0, 200000);
  readSyllabus(text);
});
$("#clearSyl").addEventListener("click", () => {
  state.syllabus = null;
  state.filters.delete("match");
  $("#syllabusText").value = "";
  $("#parseNote").hidden = true;
  persist();
  renderSyllabus();
  render();
});
$("#remindBtn").addEventListener("click", async () => {
  const btn = $("#remindBtn");
  btn.disabled = true;
  const result = await Reminders.enable(state.syllabus.due);
  $("#remindNote").textContent = result.why;
  btn.textContent = result.ok ? "On" : "Turn on";
  btn.disabled = false;
});

/* install + offline */
let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  deferredPrompt = e;
  if (!store.get("installDismissed", false)) $("#install").hidden = false;
});
$("#installBtn").addEventListener("click", () => {
  $("#install").hidden = true;
  if (deferredPrompt) { deferredPrompt.prompt(); deferredPrompt = null; }
});
$("#installClose").addEventListener("click", () => {
  $("#install").hidden = true;
  store.set("installDismissed", true);
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}

load();
