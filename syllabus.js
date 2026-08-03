/* Syllabus reading: coursework skills, course codes, and due dates.
 *
 * Runs entirely in the browser -- a syllabus is a personal document and there is
 * no server here to send it to. Nothing leaves the phone. */

const Syllabus = (() => {

  /* --------------------------------------------------------------- skills */

  // Taxonomy labels arrive as plain words; rebuild the same boundary rules the
  // Python side uses so a match here means a match there.
  const skillRegex = (term) => {
    const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    return /^[a-z0-9 ]+$/.test(term)
      ? new RegExp(`\\b${escaped}\\b`, "i")
      : new RegExp(escaped, "i");
  };

  function extractSkills(text, vocabulary) {
    const found = vocabulary.filter((term) => skillRegex(term).test(text));
    // Longer terms are more informative: "machine learning" over "research".
    return found.sort((a, b) => b.length - a.length || a.localeCompare(b));
  }

  /* -------------------------------------------------------------- courses */

  // "CSC 300", "NURS-210", "BIOL 1010" -- 2-4 letters then 3-4 digits.
  const COURSE_CODE = /\b([A-Z]{2,4})\s?-?\s?(\d{3,4})\b/g;

  function extractCourses(text) {
    const codes = new Set();
    let m;
    COURSE_CODE.lastIndex = 0;
    while ((m = COURSE_CODE.exec(text)) !== null) {
      codes.add(`${m[1]} ${m[2]}`);
    }
    return [...codes].slice(0, 12);
  }

  /* ------------------------------------------------------------ due dates */

  const MONTHS = {
    jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5,
    jul: 6, aug: 7, sep: 8, oct: 9, nov: 10, dec: 11,
  };

  const NAMED_DATE = /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?\b/i;
  const SLASH_DATE = /\b(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?\b/;

  const WORK = /\b(exam|midterm|final|quiz|test|homework|\bhw\b|assignment|project|paper|essay|lab|report|presentation|discussion|deadline|due|submit|milestone|proposal|draft|portfolio|clinical|practicum)\b/i;

  /* Lines that mention a date but aren't deliverables. The "no assignment"
     case matters: syllabi routinely write "Sep 8 — intro, no assignment due",
     which otherwise reads as an assignment because the words are all there. */
  const NOT_WORK = /\b(office hours?|holiday|break|syllabus|instructor|email|phone|semester begins|last day to|no\s+(class|assignment|homework|quiz|exam|reading|lab|lecture)s?\b|nothing due|not graded)\b/i;

  /* A syllabus rarely writes the year. Assume the nearest sensible one: a date
     more than four months in the past almost certainly means next year. */
  function inferYear(month, day, explicit) {
    if (explicit) return explicit < 100 ? 2000 + explicit : explicit;
    const now = new Date();
    let year = now.getFullYear();
    const candidate = new Date(year, month, day);
    const fourMonths = 1000 * 60 * 60 * 24 * 120;
    if (candidate.getTime() < now.getTime() - fourMonths) year += 1;
    return year;
  }

  function parseDate(line) {
    let m = line.match(NAMED_DATE);
    if (m) {
      const month = MONTHS[m[1].toLowerCase().slice(0, 3)];
      const day = parseInt(m[2], 10);
      if (day >= 1 && day <= 31) {
        return { date: new Date(inferYear(month, day, m[3] && +m[3]), month, day), matched: m[0] };
      }
    }
    m = line.match(SLASH_DATE);
    if (m) {
      const month = parseInt(m[1], 10) - 1;
      const day = parseInt(m[2], 10);
      if (month >= 0 && month <= 11 && day >= 1 && day <= 31) {
        return { date: new Date(inferYear(month, day, m[3] && +m[3]), month, day), matched: m[0] };
      }
    }
    return null;
  }

  function cleanTitle(line, matched) {
    return line
      .replace(matched, " ")
      .replace(/^[\s\-–—•*|:.)\]]+/, "")
      .replace(/[\s\-–—•*|:.(\[]+$/, "")
      .replace(/\s{2,}/g, " ")
      .trim()
      .slice(0, 90);
  }

  function extractDueDates(text) {
    const items = [];
    const seen = new Set();

    for (const rawLine of text.split(/\r?\n/)) {
      const line = rawLine.trim();
      if (line.length < 4 || line.length > 220) continue;
      if (!WORK.test(line) || NOT_WORK.test(line)) continue;

      const hit = parseDate(line);
      if (!hit) continue;

      const title = cleanTitle(line, hit.matched);
      if (!title) continue;

      const key = `${title.toLowerCase()}|${hit.date.toDateString()}`;
      if (seen.has(key)) continue;
      seen.add(key);

      items.push({
        title,
        due: hit.date.toISOString(),
        kind: (line.match(WORK) || [""])[0].toLowerCase(),
      });
    }

    return items.sort((a, b) => new Date(a.due) - new Date(b.due)).slice(0, 40);
  }

  /* ---------------------------------------------------------------- parse */

  function parse(text, vocabulary) {
    return {
      skills: extractSkills(text, vocabulary),
      courses: extractCourses(text),
      due: extractDueDates(text),
      chars: text.length,
      parsedAt: new Date().toISOString(),
    };
  }

  /* Score a job against parsed coursework: how many of its listed skills the
     student has already covered. Returned with the overlap so the UI can show
     *why* something ranked, rather than an unexplained number. */
  function scoreJob(job, skillSet) {
    if (!skillSet.size || !job.skills || !job.skills.length) {
      return { score: 0, overlap: [] };
    }
    const overlap = job.skills.filter((s) => skillSet.has(s));
    // Normalised by the job's own skill count so a posting that lists 3 skills
    // and matches all 3 beats one that lists 14 and matches 4.
    return { score: overlap.length / Math.sqrt(job.skills.length), overlap };
  }

  return { parse, extractSkills, extractCourses, extractDueDates, scoreJob };
})();
