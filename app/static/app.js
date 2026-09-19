const EMPTY = 0, FILL = 1, X = 2;

const load = (key) => { try { return JSON.parse(localStorage.getItem(key)) } catch { return null } };
const store = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)) } catch {} };
const forget = (key) => { try { localStorage.removeItem(key) } catch {} };

// Dates are local-time "YYYY-MM-DD" strings; parsing them with new Date(iso) would use UTC.
const todayISO = () => new Date().toLocaleDateString("en-CA");
const parseISO = (iso) => { const [y, m, d] = iso.split("-").map(Number); return new Date(y, m - 1, d) };
const toISO = (date) => date.toLocaleDateString("en-CA");
const gameKey = (iso) => `nono:${iso}`;

// Whether a saved game belongs to a day's puzzle ({ fp, solution }). A save that carries a
// fingerprint must match it. One without (saved by an older app.js, possibly on today's puzzle)
// is judged by its marks instead: every mark is checked against the solution when it's made,
// so a genuine save always agrees with it, while one from a different puzzle almost never does.
function saveMatches(saved, { fp, solution }) {
  if (!saved || (saved.fp !== undefined && saved.fp !== fp)) return false;
  const { cells, errors = [] } = saved;
  if (!Array.isArray(cells) || cells.length !== solution.length) return false;
  const marksAgree = cells.every((v, i) =>
    v === EMPTY || (v === FILL && solution[i] === "1") || (v === X && solution[i] === "0"));
  return marksAgree && Array.isArray(errors) && errors.every((i) => Number.isInteger(i) && cells[i] !== EMPTY);
}

// UI strings come from the server (index.html) in the picked language; see app/i18n.py.
const I18N = window.I18N ?? {};
const t = (key, vars = {}) => (I18N[key] ?? key).replace(/\{(\w+)\}/g, (_, name) => vars[name]);
// Dates follow the picked language. For English, keep the browser's own English variant
// (en-GB writes dd/mm/yyyy, en-US mm/dd/yyyy).
const LOCALE = document.documentElement.lang === "en"
  ? navigator.languages.find((l) => l.startsWith("en")) ?? "en-US"
  : document.documentElement.lang;

// Only called when the player picks a language, so detection keeps working until they do.
function setLanguage(lang) {
  if (lang === document.documentElement.lang) return;
  document.cookie = `nono_lang=${encodeURIComponent(lang)}; path=/; max-age=31536000; samesite=lax`;
  location.reload();
}

// Every URL gets the same page shell and the view is picked here:
// "/" is today's puzzle, "/2026-09-17" is that day's, "/calendar" is the past-puzzles page.
const CALENDAR = "/calendar";
const pathDate = () => location.pathname.match(/^\/(\d{4}-\d{2}-\d{2})$/)?.[1] ?? todayISO();
const dayURL = (iso) => (iso === todayISO() ? "/" : `/${iso}`);
const currentView = () => (location.pathname === CALENDAR ? "calendar" : "board");

function render() {
  const show = (view) => {
    Alpine.store("view", view);
    scrollTo(0, 0);
  };
  if (currentView() === "calendar") {
    document.title = `Nono · ${t("past_puzzles")}`;
    show("calendar");
  } else {
    // Switch views only once the new board is in, so the previous one never flashes.
    htmx.ajax("GET", `/board?date=${pathDate()}`, "#game").then(() => show("board"));
  }
}

function navigate(url) {
  if (location.pathname !== url) history.pushState(null, "", url);
  render();
}
const openDay = (iso) => navigate(dayURL(iso));

// Back/forward: the URL has already changed, so just render whatever it names.
addEventListener("popstate", render);
document.addEventListener("DOMContentLoaded", render);

if ("serviceWorker" in navigator) {
  addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}

// Phone/tablet vs desktop, by operating system rather than pointer type: stylus phones such as
// Samsung's S Pen models report a fine, hovering pointer, just like a mouse.
const isMobileOS = () =>
  navigator.userAgentData?.mobile ||
  /Android|iPhone|iPad|iPod/i.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1); // iPadOS identifies as a Mac

// Cuelume loads as an ES module and sets window.cuelume; until then this is a no-op.
const sfx = (name, volume = 1) => window.cuelume?.play(name, { volume });

// How many blocks are finished counting in from the start of a line: walk until the first
// undecided square; a block counts once an X or the edge closes it.
function sealedFromStart(line) {
  let sealed = 0, inBlock = false;
  for (const v of line) {
    if (v === EMPTY) return sealed;
    if (v === FILL) inBlock = true;
    else if (inBlock) { sealed++; inBlock = false }
  }
  return sealed + (inBlock ? 1 : 0);
}

document.addEventListener("alpine:init", () => {
  Alpine.store("view", currentView());

  Alpine.data("nono", (cfg) => ({
    ...cfg,
    key: "",
    total: 0,
    cells: [],
    errors: [],
    lives: cfg.maxLives,
    locks: { rows: [], cols: [] },
    tool: "fill",
    drag: null,
    copied: false,
    now: Date.now(),

    init() {
      this.key = gameKey(this.date);
      this.total = [...this.solution].filter((c) => c === "1").length;
      let saved = load(this.key);
      if (saved && !this.savedGameFits(saved)) {
        // The day's puzzle changed since this was saved; start it over rather than show a broken board.
        forget(this.key);
        saved = null;
        this.$dispatch("nono-update");
      }
      this.cells = saved?.cells ?? Array(this.size * this.size).fill(EMPTY);
      this.errors = saved?.errors ?? [];
      this.lives = saved?.lives ?? this.maxLives;
      if (saved && saved.fp !== this.fp) this.save(); // a valid save from an older app.js: stamp it
      this.updateLocks();
      this.clock = setInterval(() => (this.now = Date.now()), 1000);
      // A finished game (reload, or reopened from the calendar) shows its result right away;
      // one that ends during play pops it after a beat so the last move can land.
      if (this.over) this.$nextTick(() => this.showResult());
      this.$watch("over", (over) => over && setTimeout(() => this.showResult(), 700));
      document.title = `Nono #${this.number}`;
      this.$dispatch("nono-open", this.date);
    },

    destroy() { clearInterval(this.clock) },

    showResult() {
      const modal = this.$refs.modal;
      if (modal.isConnected && !modal.open) modal.showModal(); // the board may have been swapped out
    },

    save() {
      const status = this.won ? "won" : this.lost ? "lost" : "playing";
      store(this.key, { fp: this.fp, status, cells: this.cells, errors: this.errors, lives: this.lives });
      this.$dispatch("nono-update");
    },

    savedGameFits(saved) {
      const { lives = this.maxLives } = saved;
      return saveMatches(saved, this) && Number.isInteger(lives) && lives >= 0 && lives <= this.maxLives;
    },

    get filled() { return this.cells.filter((v) => v === FILL).length },
    get lost() { return this.lives <= 0 },
    get won() { return !this.lost && this.filled === this.total },
    get over() { return this.won || this.lost },

    get isToday() { return this.date === todayISO() },
    // dd/mm/yyyy, or whatever order and separator the browser's locale uses.
    get shortDate() {
      return parseISO(this.date).toLocaleDateString(LOCALE, { day: "2-digit", month: "2-digit", year: "numeric" });
    },
    get livesLabel() { return t("lives_left", { n: this.lives, max: this.maxLives }) },

    get countdown() {
      const midnight = new Date(this.now);
      midnight.setHours(24, 0, 0, 0);
      const s = Math.max(0, Math.floor((midnight - this.now) / 1000));
      return [s / 3600, (s % 3600) / 60, s % 60].map((v) => String(Math.floor(v)).padStart(2, "0")).join(":");
    },

    row(r) { return Array.from({ length: this.size }, (_, c) => r * this.size + c) },
    col(c) { return Array.from({ length: this.size }, (_, r) => r * this.size + c) },
    lineDone(idx) { return idx.every((i) => this.solution[i] !== "1" || this.cells[i] === FILL) },

    // A clue number greys out once nothing can be added on its side of the line: every square
    // from the nearer edge up to and including its block is decided (XXX■ greys, ___■ doesn't).
    // Every mark is verified, so the Nth finished block from an edge is the Nth number from that end.
    lineLocks(clue, idx) {
      if (clue[0] === 0) return [true]; // an empty line never gets anything added
      const line = idx.map((i) => this.cells[i]);
      const fromStart = sealedFromStart(line), fromEnd = sealedFromStart(line.reverse());
      return clue.map((_, k) => k < fromStart || k >= clue.length - fromEnd);
    },

    updateLocks() {
      this.locks = {
        rows: this.rows.map((clue, r) => this.lineLocks(clue, this.row(r))),
        cols: this.cols.map((clue, c) => this.lineLocks(clue, this.col(c))),
      };
    },

    cls(i) {
      const v = this.cells[i];
      return {
        fill: v === FILL,
        x: v === X,
        err: this.errors.includes(i),
        ghost: this.lost && v !== FILL && this.solution[i] === "1",
      };
    },

    cellAt(e) {
      const el = document.elementFromPoint(e.clientX, e.clientY)?.closest(".cell");
      return el && this.$el.contains(el) ? Number(el.dataset.i) : null;
    },

    down(e) {
      const i = this.cellAt(e);
      if (i === null || this.over || this.cells[i] !== EMPTY) return;
      e.preventDefault();
      const tool = e.button === 2 ? "x" : this.tool; // right-click always marks
      this.drag = { mode: tool, origin: i, axis: null };
      this.apply(i);
    },

    // Drags lock to the row or column they start moving along, like most nonogram apps.
    move(e) {
      if (!this.drag) return;
      const i = this.cellAt(e);
      if (i === null) return;
      const n = this.size, o = this.drag.origin;
      const [r0, c0, r, c] = [Math.floor(o / n), o % n, Math.floor(i / n), i % n];
      if (!this.drag.axis) {
        if (r === r0 && c === c0) return;
        this.drag.axis = Math.abs(c - c0) >= Math.abs(r - r0) ? "h" : "v";
      }
      const [from, to, step] = this.drag.axis === "h" ? [c0, c, 1] : [r0, r, n];
      const dir = Math.sign(to - from);
      for (let k = 0; k <= Math.abs(to - from) && this.drag; k++) {
        this.apply(o + dir * k * step);
      }
    },

    up() { this.drag = null },

    // Every mark is checked. A wrong one reveals the real tile, costs a life and ends the drag.
    apply(i) {
      if (this.cells[i] !== EMPTY) return;
      const truth = this.solution[i] === "1" ? FILL : X;
      const wrong = (this.drag.mode === "fill" ? FILL : X) !== truth;
      this.cells[i] = truth;
      const completedLine = truth === FILL && this.autoMark(i);
      if (wrong) {
        this.errors.push(i);
        this.lives--;
        this.drag = null;
      }
      this.updateLocks();
      this.save();

      if (this.lost) sfx("droplet");
      else if (this.won) sfx("success");
      else if (wrong) sfx("error");
      else if (completedLine) sfx("chime");
      else sfx(truth === FILL ? "press" : "tick");
    },

    // Once a line has all its fills, mark the rest of it. Returns whether any line got completed.
    autoMark(i) {
      const n = this.size;
      let completed = false;
      for (const line of [this.row(Math.floor(i / n)), this.col(i % n)]) {
        if (!this.lineDone(line)) continue;
        completed = true;
        line.forEach((j) => { if (this.cells[j] === EMPTY) this.cells[j] = X });
      }
      return completed;
    },

    async share() {
      const hearts = "❤️".repeat(this.lives) + "🖤".repeat(this.maxLives - this.lives);
      const text = `Nono #${this.number} · ${this.label} ${this.size}×${this.size}\n${this.won ? "✅" : "❌"} ${hearts}\n${location.origin}/${this.date}`;
      // Like term.ooo: native share sheet on phones and tablets, clipboard on desktop
      // (desktop browsers also have navigator.share, but it opens the OS share dialog).
      if (isMobileOS() && navigator.share) {
        try {
          return await navigator.share({ text });
        } catch (err) {
          if (err.name === "AbortError") return; // user closed the sheet
        }
      }
      if (await this.copy(text)) {
        sfx("success");
        this.copied = true;
        setTimeout(() => (this.copied = false), 2000);
      }
    },

    // navigator.clipboard and navigator.share only exist on HTTPS/localhost,
    // so fall back to execCommand for plain http (e.g. testing over the LAN).
    async copy(text) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch {}
      // A modal dialog makes everything outside it inert, so the textarea goes inside it.
      const host = this.$refs.modal.open ? this.$refs.modal : document.body;
      const ta = Object.assign(document.createElement("textarea"), { value: text, readOnly: true });
      ta.style.cssText = "position:fixed;opacity:0;pointer-events:none";
      host.append(ta);
      ta.select();
      ta.setSelectionRange(0, text.length); // iOS ignores select()
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    },
  }));

  // Language menu: opens on the current language, arrows move between options,
  // Escape or a click outside closes it.
  Alpine.data("langMenu", () => ({
    open: false,
    // $root, not $el: $el is whichever element fired the event (e.g. the button).
    items() { return [...this.$root.querySelectorAll('[role="menuitemradio"]')] },
    toggle() {
      this.open = !this.open;
      if (this.open) this.focusCurrent();
    },
    // x-show's transition unhides the menu a couple of frames later, and hidden items can't take focus.
    focusCurrent(tries = 6) {
      const current = this.items().find((el) => el.ariaChecked === "true");
      if (current?.offsetParent) current.focus();
      else if (tries && this.open) requestAnimationFrame(() => this.focusCurrent(tries - 1));
    },
    close(refocus) {
      if (!this.open) return;
      this.open = false;
      if (refocus) this.$refs.button.focus();
    },
    step(delta) {
      if (!this.open) return this.toggle();
      const items = this.items();
      const i = items.indexOf(document.activeElement);
      items[(i + delta + items.length) % items.length].focus();
    },
  }));

  // How-to-play dialog: opens by itself while there are no saved games on this device.
  Alpine.data("help", () => ({
    init() {
      let played = false;
      try { played = Object.keys(localStorage).some((k) => /^nono:\d{4}-\d{2}-\d{2}$/.test(k)) } catch {}
      if (!played) this.$nextTick(() => this.$refs.dialog.showModal());
    },
  }));

  // Month view of past puzzles. Every day up to today can be opened. Finished days open read-only
  // (the board locks when over), so a solved or failed day can be reviewed but not replayed.
  Alpine.data("calendar", (launch) => ({
    launch,
    today: todayISO(),
    current: todayISO(),
    month: null,
    version: 0, // bumped on every save so statuses re-read localStorage
    // Narrow weekday names in the browser's locale, Sunday first (2026-09-13 is a Sunday).
    weekdays: Array.from({ length: 7 }, (_, k) => new Date(2026, 8, 13 + k).toLocaleDateString(LOCALE, { weekday: "narrow" })),

    init() {
      const t = parseISO(this.today);
      this.month = new Date(t.getFullYear(), t.getMonth(), 1);
      this.refresh();
      this.pruneStaleSaves();
    },

    refresh() { this.version++ },

    // Runs on every page load: drop saved games whose puzzle has changed (new generator, fresh
    // database), so the calendar never shows a result that doesn't belong to the current board.
    async pruneStaleSaves() {
      let days;
      try {
        days = (await (await fetch("/api/days")).json()).days;
      } catch {
        return; // offline: nothing to compare against, try again next load
      }
      let keys = [];
      try { keys = Object.keys(localStorage) } catch {}
      for (const key of keys) {
        const date = key.match(/^nono:(\d{4}-\d{2}-\d{2})$/)?.[1];
        if (!date) continue;
        // Dates before launch never had a puzzle; open dates must match their puzzle. Dates that
        // haven't opened on the server yet (a device clock running ahead) are left alone.
        const saved = load(key);
        if (date < this.launch || (date in days && !saveMatches(saved, days[date]))) forget(key);
        else if (date in days && saved.fp === undefined) store(key, { ...saved, fp: days[date].fp }); // stamp it
      }
      this.refresh();
    },

    status(iso) {
      this.version;
      return load(gameKey(iso))?.status ?? null;
    },

    get monthLabel() {
      const label = this.month.toLocaleDateString(LOCALE, { month: "long", year: "numeric" });
      return label[0].toUpperCase() + label.slice(1);
    },
    get canPrev() { return toISO(this.month) > this.launch },
    get canNext() { return toISO(new Date(this.month.getFullYear(), this.month.getMonth() + 1, 1)) <= this.today },
    // Called whenever a board loads, so the calendar follows direct links and back/forward.
    show(iso) {
      this.current = iso;
      const d = parseISO(iso);
      this.month = new Date(d.getFullYear(), d.getMonth(), 1);
    },

    shift(delta) { this.month = new Date(this.month.getFullYear(), this.month.getMonth() + delta, 1) },

    get days() {
      const y = this.month.getFullYear(), m = this.month.getMonth();
      const blanks = Array.from({ length: this.month.getDay() }, (_, k) => ({ key: `b${k}` }));
      const count = new Date(y, m + 1, 0).getDate();
      const days = Array.from({ length: count }, (_, k) => {
        const iso = toISO(new Date(y, m, k + 1));
        const status = this.status(iso);
        return {
          key: iso,
          iso,
          day: k + 1,
          status,
          label: `${parseISO(iso).toLocaleDateString(LOCALE, { day: "numeric", month: "long" })}: ${t(status ?? "not_played")}`,
          disabled: iso < this.launch || iso > this.today,
          cls: { [status]: !!status, today: iso === this.today, current: iso === this.current },
        };
      });
      return [...blanks, ...days];
    },

    open(iso) { openDay(iso) },
  }));
});

// Visit with ?debug for a button that clears today's saved games.
if (new URLSearchParams(location.search).has("debug")) {
  const reset = Object.assign(document.createElement("button"), { id: "debug-reset", textContent: "Reset today" });
  reset.addEventListener("click", () => {
    try { localStorage.removeItem(gameKey(todayISO())) } catch {}
    location.reload();
  });
  document.body.append(reset);
}
