const $ = (id) => document.getElementById(id);
const els = ["gear", "next", "pick", "pickEmpty", "folder", "name", "rename", "clear", "progress", "empty", "emptyTitle", "emptyText", "grid", "toast", "stat", "drop", "flow", "steps", "guide",
  "profile", "context", "order", "settings", "key", "showkey", "model", "custom", "modelnote", "spend", "keymsg", "test", "cancel", "version",
  "save", "editPrompts", "prompts", "ptabs", "pdesc", "pedit", "pcategories", "preader", "prules", "pfull", "pread", "pname", "pmsg",
  "preset", "pshow", "pcancel", "psave", "update", "updateText", "updateLink", "updateGo", "updateLater",
  "checkUpdates", "updateMsg", "watchbar", "watchText", "watchStart", "wOn", "wFields", "wFolder", "wPick", "wProfile",
  "wWait", "wLimit", "wSpent", "wAutoRow", "wAuto", "wAutoNote", "wShowStartup", "wWaitRow", "wStatus", "wLog"]
  .reduce((o, k) => (o[k] = $(k), o), {});
// sources: what the user loaded (folders and/or files); items: the files found in them.
let sources = [], items = [], status = { models: [], profiles: [] }, journal = null, toastTimer = null, profile = "propresenter";
// loadGen: bumped by every load and by Clear, so a scan that finishes after a newer
// load or a Clear is dropped instead of replacing what is on screen.
let naming = false, loading = null, loadGen = 0;
// What the guide line reports: the last naming run's cost (null until one ran for
// these files) and how many files the last Rename changed.
let lastCost = null, renamedCount = 0;
// namedProfile: the style the suggestions on screen were made in. autoOrder: Keep order
// was switched on for this batch because its files are numbered. drafts: the names
// that went into the last Rename, so Undo can put them back as suggestions.
let namedProfile = null, autoOrder = false, drafts = null;
const FOLDER_HINT = els.folder.placeholder;
const EMPTY_TEXT = els.emptyText.textContent;

async function api(path, body) {
  const r = await fetch("/api/" + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

// Pop-ups are for errors and for news the screen does not already show;
// what a batch cost and Undo live in the guide line, once.
function toast(msg, opts = {}) {
  clearTimeout(toastTimer);
  els.toast.firstElementChild.textContent = msg;
  els.toast.classList.toggle("error", !!opts.error);
  els.toast.hidden = false;
  els.toast.title = opts.error ? "Click to dismiss" : "";
  // Errors never auto-hide: a silent failure that scrolls past is the thing
  // this app must not do.
  if (!opts.error) toastTimer = setTimeout(() => (els.toast.hidden = true), 4500);
}

const stem = (name) => name.replace(/\.[^.]+$/, "");
const inputs = () => [...els.grid.querySelectorAll(".name")];
const parent = (p) => p.replace(/[\\/][^\\/]*$/, "");
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const dollars = (usd) => "US$" + (usd >= 0.01 ? usd.toFixed(2) : usd.toFixed(4));
// OpenRouter's own figure for the batch; the month's total once other batches are in it too.
const costText = (usd) => usd
  ? `Cost ${dollars(usd)}${status.spent_month > usd + 1e-9 ? ` · ${dollars(status.spent_month)} this month` : ""}`
  : status.has_key ? "Cost not reported" : "";
const styleName = (id) => (status.profiles.find((p) => p.id === id) || { label: id }).label;

// Names wrap instead of being cut off, so every card shows its whole name.
// scrollHeight leaves out the border, which border-box heights include.
const fullHeight = (b) => b.scrollHeight + b.offsetHeight - b.clientHeight;
function fit(box) {
  box.style.height = "auto";
  box.style.height = fullHeight(box) + "px";
}
function fitAll() {  // read every height before setting any: one layout, not one per card
  const boxes = inputs();
  boxes.forEach((b) => (b.style.height = "auto"));
  const heights = boxes.map(fullHeight);
  boxes.forEach((b, n) => (b.style.height = heights[n] + "px"));
}

// Keep order's 01, 02… prefixes: per folder, in list order, at least two digits.
function numberItems() {
  const totals = {}, seen = {};
  for (const it of items) totals[parent(it.path)] = (totals[parent(it.path)] || 0) + 1;
  for (const it of items) {
    const f = parent(it.path);
    seen[f] = (seen[f] || 0) + 1;
    it.num = String(seen[f]).padStart(Math.max(2, String(totals[f]).length), "0");
  }
}

// Numbers go on suggested names only, and sit outside the editable text so
// editing a name cannot drop its number and move the file out of order.
const numbered = (it) => els.order.checked && !!it.named;
function finalName(it, box) {
  const base = box.value.trim();
  return base && numbered(it) ? `${it.num} ${base}` : base;
}

function render() {
  els.grid.innerHTML = "";
  numberItems();
  els.empty.hidden = items.length > 0;
  showEmpty(true);
  items.forEach((it, n) => {
    const card = document.createElement("article");
    card.className = "card";
    card.dataset.id = it.id;
    card.style.setProperty("--i", n);
    const badge = it.kind === "image" ? "" : `<span class="kind">${it.kind === "pdf" ? "PDF" : "VIDEO"}</span>`;
    card.innerHTML = `<div class="thumb"><img alt="">${badge}</div>
      <div class="meta"><div class="orig"></div>
      <div class="namebox"><span class="num" hidden title="Keep order puts this number in front of the name"></span>
      <textarea class="name" rows="1" spellcheck="false" placeholder="—" aria-label="New name"></textarea></div></div>`;
    if (it.thumb) card.querySelector("img").src = "data:image/jpeg;base64," + it.thumb;
    card.querySelector(".orig").textContent = card.querySelector(".orig").title = it.name;
    const inp = card.querySelector(".name");
    inp.value = stem(it.name);
    inp.addEventListener("input", () => {
      if (/[\r\n]/.test(inp.value)) inp.value = inp.value.replace(/\s*[\r\n]+\s*/g, " ");  // pasted lines
      updateChanged(inp, it);
    });
    inp.addEventListener("focus", () => (inp.dataset.before = inp.value));
    inp.addEventListener("keydown", (e) => {
      if (e.isComposing) return;  // Enter or Escape is picking an input-method candidate
      if (e.key === "Escape") {  // undo this edit
        inp.value = inp.dataset.before ?? inp.value;
        updateChanged(inp, it);
        inp.blur();
      } else if (e.key === "Enter") {
        e.preventDefault();  // a name is one line; Cmd/Ctrl+Enter still reaches Rename
        if (!e.metaKey && !e.ctrlKey) inp.blur();
      }
    });
    els.grid.appendChild(card);
  });
  refreshCards();
}

function showEmpty(loaded) {
  els.emptyTitle.textContent = loaded ? "No files Smart Explorer can name in there"
    : profile === "general" ? "Drop a folder of files here" : "Drop a folder of slides here";
  els.emptyText.textContent = loaded
    ? "It reads images (PNG, JPEG and more), iPhone photos (HEIC), PDFs and videos (MP4, MOV). Try another folder."
    : EMPTY_TEXT;
}

function refreshCards() {
  inputs().forEach((inp, n) => updateChanged(inp, items[n], false));
  fitAll();
  updateButtons();
}

function updateChanged(inp, it, one = true) {
  const name = finalName(it, inp), changed = !!name && name !== stem(it.name);
  const num = inp.previousElementSibling;
  num.hidden = !numbered(it);
  num.textContent = it.num;
  inp.classList.toggle("changed", changed);
  inp.closest(".card").classList.toggle("is-changed", changed);
  if (one) { fit(inp); updateButtons(); }
}

function updateButtons() {
  const changed = inputs().filter((i) => i.classList.contains("changed")).length;
  els.name.disabled = !items.length || naming;
  els.rename.disabled = !changed || naming;
  els.clear.disabled = !items.length || naming;
  els.rename.textContent = changed ? `Rename ${plural(changed, "file")}` : "Rename";
  // The coloured button is always the next step: Name, then Rename, then Rename more files.
  const done = !changed && renamedCount > 0 && !naming;
  els.clear.textContent = done ? "Rename more files" : "Clear";
  els.clear.title = done ? "Start on the next set of files. The files you renamed keep their new names."
    : "Empty the list to start on other files. Files on disk are not touched.";
  const restyle = restyled(changed);
  els.name.classList.toggle("primary", (!changed && !done) || restyle);
  els.rename.classList.toggle("primary", changed > 0 && !restyle);
  els.clear.classList.toggle("primary", done);
  els.stat.innerHTML = items.length ? `<b>${items.length}</b> file${items.length === 1 ? "" : "s"}` : "";
  showFlow(changed);
  showNext();
}

const ORDER_HINT = els.order.parentElement.title;
const orderHint = () => (els.order.parentElement.title = autoOrder
  ? "Turned on because these files are numbered in order. " + ORDER_HINT : ORDER_HINT);

// Suggestions made in one style while the other is now picked.
const restyled = (changed) => changed > 0 && !naming && namedProfile !== null && namedProfile !== profile;

// Once the toolbar has scrolled out of sight, the header offers the next step.
let barInView = true;
function showNext() {
  const next = [els.name, els.rename, els.clear].find((b) => b.classList.contains("primary"));
  els.next.hidden = barInView || !next || !items.length;
  if (!next) return;
  els.next.textContent = next.textContent;
  els.next.disabled = next.disabled;
  els.next.onclick = () => next.click();
}

// The three steps, where you are, and what to do next. Built from numbers only.
function showFlow(changed) {
  els.flow.hidden = !items.length;
  if (!items.length) return;
  const step = naming ? 2 : changed ? 3 : renamedCount ? 4 : 2;
  [...els.steps.children].forEach((li, n) => {
    li.classList.toggle("on", n + 1 === step);
    li.classList.toggle("done", n + 1 < step);
  });
  let html = naming ? `Reading ${plural(items.length, "file")}…`
    : restyled(changed) ? `These names were made for <b>${styleName(namedProfile)}</b>. Click <b>Name with AI</b> to redo them for <b>${styleName(profile)}</b>.`
    : changed ? `Check the names (click one to change it), then <b>Rename ${plural(changed, "file")}</b>.`
    : renamedCount ? `<b>Renamed ${plural(renamedCount, "file")}.</b>${journal ? ' <button type="button" class="mini" data-undo>Undo</button>' : ""}`
    : "Click <b>Name with AI</b>. Nothing changes on disk until you rename.";
  const cost = naming || lastCost === null ? "" : costText(lastCost);
  if (cost) html += ` <span class="cost" title="What naming cost on OpenRouter">${cost}</span>`;
  els.guide.innerHTML = html;
}

function showSources() {
  els.folder.placeholder = FOLDER_HINT;
  if (sources.length === 1) { els.folder.value = sources[0]; return; }
  const folders = new Set(items.map((i) => parent(i.path))).size;
  els.folder.value = "";
  els.folder.placeholder = `${plural(items.length, "file")} from ${plural(folders, "folder")} (dropped)`;
}

async function load(paths, afterRename = false) {
  paths = paths.filter(Boolean);
  if (!paths.length) return;
  if (naming) return toast("Wait for naming to finish before loading more files.", { error: true });
  const gen = ++loadGen;
  const run = (async () => {
    try {
      const scan = await api("scan", { paths });
      if (gen !== loadGen) return;
      items = scan.items;
      if (!afterRename) {  // new files: a fresh start, with nothing carried over from the last set
        lastCost = null;
        renamedCount = 0;
        namedProfile = null;
        drafts = null;
        // Numbered in sequence (1.png…, Slide1…): Keep order starts on (scanner.looks_numbered).
        els.order.checked = autoOrder = !!scan.numbered;
        orderHint();
      }
      sources = paths;
      els.folder.classList.remove("bad");
      render();
      showSources();
      els.progress.hidden = true;
    } catch (e) {
      if (gen !== loadGen) return;
      // Keep the typed path to correct, marked, so it is not mistaken for the list below.
      els.folder.classList.add("bad");
      toast(e.message, { error: true });
    }
  })();
  loading = run;
  try { await run; } finally { if (loading === run) loading = null; }
}

async function nameAll() {
  // A path typed and then left by clicking this button starts loading first;
  // name what that load shows, not the list it is about to replace.
  if (loading) await loading;
  if (naming || !items.length) return;
  if (updating()) return toast("Smart Explorer is updating and will reopen in a moment.", { error: true });
  const style = profile;
  naming = true;
  renamedCount = 0;
  lastCost = null;  // the last batch's cost would read as this one's
  els.progress.hidden = false;
  els.progress.className = "busy";
  els.progress.firstElementChild.style.width = "0";
  inputs().forEach((i) => (i.closest(".card").className = "card pending", i.disabled = true));
  updateButtons();  // step 2 lights up and the guide says what is happening
  try {
    const { job } = await api("name", {
      paths: items.map((i) => i.path), profile: style, context: els.context.value.trim(),
    });
    let r;
    do {
      await new Promise((res) => setTimeout(res, 700));
      r = await api("name/" + job);
      els.progress.firstElementChild.style.width = (r.total ? (r.progress / r.total) * 90 : 0) + "%";
    } while (!r.done);
    if (r.cost) lastCost = r.cost;  // a failed batch can still have cost something
    if (r.error) throw new Error(r.error);
    let errors = 0, missing = 0, why = null;
    for (const it of items) {
      const res = r.results[it.path], inp = els.grid.querySelector(`[data-id="${it.id}"] .name`);
      inp.closest(".card").className = "card" + (res && !res.error ? "" : " error");
      if (!res) { missing++; inp.title = "This file was not there when naming ran. Load the folder again."; continue; }
      if (res.error) { errors++; inp.title = res.error; why = why || res.error; }
      it.named = true;
      if (res.proposed) inp.value = res.proposed;
      updateChanged(inp, it, false);
    }
    fitAll();
    els.progress.firstElementChild.style.width = "100%";
    lastCost = r.cost || 0;
    namedProfile = style;
    drafts = null;
    Object.assign(status, await api("status").catch(() => ({})));  // this month's total, for the guide
    if (errors + missing) toast(why
      || (missing ? `${plural(missing, "file")} ${missing === 1 ? "is" : "are"} no longer there. Load the folder again before renaming.`
        : `Named ${items.length - errors} of ${items.length}. ${errors} could not be read.`), { error: true });
  } catch (e) {
    toast(e.message, { error: true });
    inputs().forEach((i) => (i.closest(".card").className = "card"));
    refreshCards();
  } finally {
    naming = false;
    els.progress.className = "";
    setTimeout(() => (els.progress.hidden = true), 800);
    inputs().forEach((i) => (i.disabled = false));
    updateButtons();
  }
}

// Renamed files keep their place in the list: dropped file paths follow the rename.
const follow = (moved) => {
  const map = new Map(moved);
  sources = sources.map((s) => map.get(s) || s);
};

async function renameAll() {
  if (naming) return;
  const inp = inputs();
  const changed = items.map((it, i) => ({ path: it.path, new_name: finalName(it, inp[i]) }))
    .filter((x, i) => x.new_name && x.new_name !== stem(items[i].name));
  if (!changed.length) return;
  const kept = new Map(items.map((it, i) => [it.path, { name: inp[i].value, named: !!it.named }]));
  try {
    const r = await api("rename", { items: changed });
    journal = r.renamed ? r.journal : null;
    drafts = r.renamed ? kept : null;
    renamedCount = r.renamed;
    follow(r.moved);
    if (r.error) toast(`Renamed ${plural(r.renamed, "file")}, then stopped: ${r.error}`, { error: true });
    await load(sources, true);
  } catch (e) { toast(e.message, { error: true }); }
}

async function undo() {
  if (naming) return;  // the button is hidden while naming; this guards a stray click
  try {
    const r = await api("undo", { journal });
    journal = null;
    renamedCount = 0;
    follow(r.moved);
    await load(sources, true);
    // The files have their old names again; the suggestions and edits come back
    // too, so fixing one name does not mean paying to name them all again.
    const back = drafts || new Map();
    drafts = null;
    let kept = 0;
    inputs().forEach((inp, n) => {
      const d = back.get(items[n].path);
      if (d) { inp.value = d.name; items[n].named = d.named; kept++; }
    });
    if (kept) refreshCards();
    toast(kept ? "Old names are back. Your suggestions are still below." : "Old names are back.");
  } catch (e) { toast(e.message, { error: true }); }
}

// Empty the list for a new set of files. Only the list: nothing on disk changes.
function clearAll() {
  if (naming) return;
  const pending = inputs().filter((i) => i.classList.contains("changed")).length;
  if (pending && !confirm(`Clear the list and drop ${plural(pending, "suggested name")} you have not applied? Files on disk are not changed.`)) return;
  loadGen++;  // a folder still loading (say, a path just typed) must not refill the list
  items = [];
  sources = [];
  lastCost = null;
  renamedCount = 0;
  namedProfile = null;
  drafts = null;
  els.order.checked = autoOrder = false;
  orderHint();
  els.context.value = "";  // the note was about the set just cleared
  render();
  showEmpty(false);
  els.folder.value = "";
  els.folder.classList.remove("bad");
  els.folder.placeholder = FOLDER_HINT;
  els.progress.hidden = true;
}

function renderProfiles() {
  els.profile.innerHTML = "";
  for (const p of status.profiles) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = p.label;
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(p.id === profile));
    b.title = p.description;
    b.onclick = () => {
      profile = p.id;
      renderProfiles();
      if (items.length) updateButtons(); else if (!sources.length) showEmpty(false);
    };
    els.profile.appendChild(b);
  }
}

function showModelNote() {
  const m = status.models.find((x) => x.id === els.model.value);
  els.modelnote.textContent = m ? m.note : "Any OpenRouter model that accepts images.";
}

function fillSettings() {
  els.gear.classList.toggle("warn", !status.has_key);
  els.model.innerHTML = "";
  for (const m of [...status.models, { id: "", label: "Custom…" }]) els.model.add(new Option(m.label, m.id));
  const known = status.models.some((m) => m.id === status.model);
  els.model.value = known ? status.model : "";
  els.custom.hidden = known;
  els.custom.value = known ? "" : status.model;
  els.key.value = "";
  els.key.type = "password";
  els.showkey.textContent = "Show";
  els.key.placeholder = status.has_key ? "•••••••• (saved, leave blank to keep)" : "sk-or-…";
  els.spend.textContent = status.spent_total
    ? `Spent on naming: ${dollars(status.spent_month || 0)} this month, ${dollars(status.spent_total)} in all.`
    : "";
  els.keymsg.textContent = "";
  els.keymsg.className = "msg";
  els.version.textContent = status.version ? `Smart Explorer ${status.version}` : "";
  els.updateMsg.textContent = "";
  showModelNote();
}

async function saveSettings() {
  if (!(await saveWatch())) return;
  const body = { model: els.model.value || els.custom.value.trim() || status.model };
  if (els.key.value.trim()) body.key = els.key.value.trim();
  status = await api("settings", body);
  fillSettings();
  els.settings.close();
  const w = watchState || {}, s = w.settings || {};
  toast(s.enabled && s.autostart && w.autostart_on  // read back from the computer, not assumed
    ? "Settings saved. Smart Explorer is in this computer's start-up items." : "Settings saved");
}

async function testKey() {
  els.keymsg.textContent = "Checking…";
  els.keymsg.className = "msg";
  const r = await api("check-key", { key: els.key.value.trim() });
  const spent = r.spent === undefined ? "" : ` ${dollars(r.spent)} spent on this key so far` + (r.left === undefined ? "." : `, ${dollars(r.left)} left on its limit.`);
  els.keymsg.textContent = r.ok ? `Key works${r.label ? " (" + r.label + ")" : ""}.${spent}` : r.error;
  els.keymsg.className = "msg " + (r.ok ? "ok" : "err");
}

// Naming prompts: what the AI is told for each naming style, to read and change.
// Each style has three parts (the categories, what to look for in each file, how
// to name them); edits to both styles are kept here until Save.
let promptData = null, promptTab = null, promptDrafts = {};
const PROMPT_FIELDS = ["categories", "reader", "rules"];
const catLines = (s) => s.split(/\s+·\s+/).join("\n");  // "A · B" is shown one per line
const catJoin = (s) => s.split("\n").map((x) => x.trim()).filter(Boolean).join(" · ");
const sameText = (a, b) => (a || "").trim() === (b || "").trim();
const promptStyle = (id) => promptData.profiles.find((p) => p.id === id);
const promptBoxes = () => ({ categories: catJoin(els.pcategories.value), reader: els.preader.value, rules: els.prules.value });
const promptChanged = (id) => {
  const d = promptDrafts[id];
  return !!d && PROMPT_FIELDS.some((f) => !sameText(d[f], promptStyle(id).current[f]));
};

function showPromptStyle(id) {
  if (promptTab) promptDrafts[promptTab] = promptBoxes();
  promptTab = id;
  const p = promptStyle(id), d = promptDrafts[id] || p.current;
  els.pcategories.value = catLines(d.categories);
  els.preader.value = d.reader;
  els.prules.value = d.rules;
  els.pdesc.textContent = p.description;
  say(els.pmsg, "");
  showPromptTabs();
  showFullPrompt(false);
}

function showPromptTabs() {
  els.ptabs.innerHTML = "";
  for (const p of promptData.profiles) {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(p.id === promptTab));
    b.textContent = p.label;
    if (p.edited.length) b.insertAdjacentHTML("beforeend", ' <span class="tag">edited</span>');
    b.onclick = () => showPromptStyle(p.id);
    els.ptabs.appendChild(b);
  }
}

async function showFullPrompt(on) {
  say(els.pmsg, "");
  if (on) {
    const r = await api("prompts/preview", { profile: promptTab, ...promptBoxes() });
    els.pread.textContent = r.read;
    els.pname.textContent = r.name;
  }
  els.pfull.hidden = !on;
  els.pedit.hidden = on;
  els.preset.hidden = on;
  els.pshow.textContent = on ? "Back to editing" : "Show full prompt";
}

async function openPrompts() {
  promptData = await api("prompts");
  promptDrafts = {};
  promptTab = null;
  showPromptStyle(profile);  // start on the style picked on the main screen
  els.settings.close();
  els.prompts.showModal();
}

async function savePrompts() {
  promptDrafts[promptTab] = promptBoxes();
  for (const id of Object.keys(promptDrafts)) {
    if (promptChanged(id)) promptData = await api("prompts", { profile: id, ...promptDrafts[id] });
  }
  promptDrafts = {};
  els.prompts.close();
  toast("Naming prompts saved");
}

function closePrompts() {
  promptDrafts[promptTab] = promptBoxes();
  if (Object.keys(promptDrafts).some(promptChanged) && !confirm("Close without saving your changes to the prompts?")) return;
  promptDrafts = {};
  els.prompts.close();
}

// Updates. The window asks GitHub once when it opens (Settings can ask again); a
// newer release shows a banner, and Update now downloads, installs and reopens.
let update = {}, updateLater = false, updateTimer = 0;
const UPDATING = ["downloading", "installing", "restarting"];
const updating = () => UPDATING.includes((update.progress || {}).state);

function showUpdate(u) {
  update = u;
  const p = u.progress || {}, busy = updating();
  const show = busy || p.state === "error" || !!u.failed || (u.newer && !updateLater);
  els.update.hidden = !show;
  if (!show) return;
  const v = u.latest || u.failed;
  const retry = p.state === "error" || (u.failed && !busy);
  els.updateText.innerHTML = p.state === "downloading" ? `Downloading Smart Explorer ${v}… ${p.total ? Math.floor((p.done / p.total) * 100) : 0}%`
    : busy ? `Installing Smart Explorer ${v}. It will close and open again.`
    : p.state === "error" ? `The update didn't finish: ${escapeHtml(p.error || "")}`
    : u.failed ? `The update to ${u.failed} didn't install.`
    : `<b>Smart Explorer ${v}</b> is available.` + (u.can_install ? "" : ` <small>${escapeHtml(u.why_not || "")}</small>`);
  els.updateGo.hidden = busy || !u.can_install;
  els.updateGo.textContent = retry ? "Try again" : "Update now";
  els.updateLink.hidden = busy;
  els.updateLink.href = u.page;
  els.updateLink.textContent = u.can_install && !retry ? "What's new" : "Download it";
  els.updateLater.hidden = busy;
}
const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

async function startUpdate() {
  if (naming) return toast("Wait for naming to finish, then update.", { error: true });
  try {
    const r = await api("update", {});
    showUpdate({ ...update, progress: r.progress });
    clearInterval(updateTimer);
    updateTimer = setInterval(async () => {
      try {
        showUpdate(await api("update"));
        if (!updating()) clearInterval(updateTimer);
      } catch (e) { /* the app is closing to install */ }
    }, 700);
  } catch (e) { toast(e.message, { error: true }); }
}

async function checkUpdates() {
  const note = (msg, ok = true) => { els.updateMsg.textContent = msg; els.updateMsg.style.color = ok ? "" : "var(--err)"; };
  note("Checking…");
  try {
    const u = await api("update?force=1");
    updateLater = false;
    showUpdate(u);
    note(u.error || (u.newer ? `Version ${u.latest} is available: see the bar at the top.` : "You have the latest version."), !u.error);
  } catch (e) { note(e.message, false); }
}

// Background renaming (Settings, Watch a folder). Settings sets it up; the bar under
// the header says what it is doing, read from the background copy's status file.
// watchFilled: Settings shows the saved values, so Save may send them back.
let watchState = null, watchTimer = 0, watchFilled = false;

function watchLine(w) {
  if (!w.running) return w.starting ? "Starting…" : "Background renaming isn't running.";
  return (w.status && w.status.state !== "stopped" && w.status.message) || "Starting…";
}

function showWatch(w) {
  watchState = w;
  const on = w.settings.enabled, down = !w.running && !w.starting;
  els.watchbar.hidden = !on;
  const trouble = w.running && ["paused", "warning"].includes((w.status || {}).state);  // warning: Google Drive is off
  els.watchbar.classList.toggle("problem", on && (down || trouble));
  els.watchText.textContent = on ? watchLine(w) : "";
  els.watchStart.hidden = !on || !down;
  els.wStatus.textContent = on ? watchLine(w) : "";
  if (watchFilled) showAutostart();  // what the start-up note says follows what is really there
  clearTimeout(watchTimer);
  if (on) watchTimer = setTimeout(refreshWatch, 5000);
}

async function refreshWatch() {
  try { showWatch(await api("watch")); } catch (e) { /* the app is closing */ }
}

function fillWatch() {
  const w = watchState;
  watchFilled = !!w;
  if (!w) return;
  const s = w.settings;
  els.wOn.checked = s.enabled;
  els.wFolder.value = s.folder;
  els.wProfile.innerHTML = "";
  for (const p of status.profiles) els.wProfile.add(new Option(p.label, p.id));
  els.wProfile.value = s.profile;
  els.wWait.value = s.startup_wait_min;
  els.wLimit.value = s.monthly_limit_usd;
  els.wSpent.textContent = w.spent_month ? `${dollars(w.spent_month)} spent this month in the background.`
    : "Nothing spent in the background this month.";
  els.wAutoRow.hidden = !w.can_autostart;
  els.wAuto.checked = s.autostart && w.can_autostart;
  els.wStatus.textContent = s.enabled ? watchLine(w) : "";
  els.wFields.hidden = !els.wOn.checked;
  showAutostart();
}

// Start by itself: what it means, and the wait that only applies when the computer starts.
// The note never claims more than is true: the tick is only a wish until Save, and
// "is in the start-up items" comes from the server reading the entry back.
function showAutostart() {
  const w = watchState || {}, can = !!w.can_autostart, ticked = can && els.wAuto.checked;
  const saved = !!(w.settings && w.settings.enabled && w.settings.autostart), there = !!w.autostart_on;
  let note = "", ok = false;
  if (!can) note = "It keeps running after you close this window, until the computer restarts. Then open Smart Explorer to start it again.";
  else if (!ticked) note = there ? "Click Save to take Smart Explorer out of the computer's start-up items."
    : "Without this, it runs until the computer restarts. Then open Smart Explorer to start it again.";
  else if (saved && there) { note = "✓ Smart Explorer is in this computer's start-up items, so it starts by itself when you sign in."; ok = true; }
  else if (saved) note = "Smart Explorer isn't in the start-up items yet. Click Save to try again.";
  else note = "Click Save, and Smart Explorer adds itself to this computer's start-up items.";
  els.wAutoNote.textContent = note;
  els.wAutoNote.parentElement.classList.toggle("ok", ok);
  els.wShowStartup.hidden = !there;
  els.wWaitRow.hidden = !ticked;
}

function watchDraft() {
  return {
    enabled: els.wOn.checked, folder: els.wFolder.value.trim(), profile: els.wProfile.value,
    startup_wait_min: Math.round(Number(els.wWait.value) || 0), monthly_limit_usd: Number(els.wLimit.value) || 0,
    autostart: els.wAuto.checked,
  };
}

// Saves Watch a folder when it changed. Returns false when the user backed out.
async function saveWatch() {
  if (!watchState || !watchFilled) return true;
  const d = watchDraft(), s = watchState.settings;
  if (!Object.keys(d).some((k) => d[k] !== s[k])) return true;
  els.wFolder.classList.remove("bad");
  const badFolder = (msg) => {  // nothing is saved: say so next to the box that needs fixing
    els.wFolder.classList.add("bad");
    els.wFolder.focus();
    return new Error(msg + " Nothing was saved yet.");
  };
  if (d.enabled && !d.folder) throw badFolder("Choose the folder to watch first.");
  if (d.enabled && (!s.enabled || d.folder !== s.folder)) {
    let count;
    try { ({ count } = await api("watch/preview", { folder: d.folder })); } catch (e) { throw badFolder(e.message); }
    const left = count === 0 ? "" : count === 1 ? "\n\nThe file already in it will be left as it is."
      : `\n\nThe ${count} files already in it will be left as they are.`;
    const msg = "Smart Explorer will rename new files in this folder by itself, even with this window closed." + left;
    if (!confirm(msg)) return false;
  }
  const w = await api("watch", d);
  showWatch(w);
  if (w.error) throw new Error(w.error);
  return true;
}

// Drag and drop. The desktop window hands full paths to onDropPaths; a plain
// browser only exposes file names, so there the folder has to be pasted.
let dragDepth = 0;
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
document.addEventListener("dragenter", (e) => { if (hasFiles(e)) { dragDepth++; els.drop.hidden = false; } });
document.addEventListener("dragleave", (e) => { if (hasFiles(e) && --dragDepth <= 0) { dragDepth = 0; els.drop.hidden = true; } });
document.addEventListener("dragover", (e) => { if (hasFiles(e)) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } });
document.addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0;
  els.drop.hidden = true;
  if (!window.pywebview) toast("Drag and drop works in the desktop app. Here, paste the folder path instead.", { error: true });
});
window.onDropPaths = (paths) => {
  els.drop.hidden = true;
  paths.length ? load(paths) : toast("Could not read the dropped items. Try Choose folder.", { error: true });
};

els.pick.onclick = els.pickEmpty.onclick = async () => {
  const { folder } = await api("pick-folder");
  if (folder) load([folder]); else els.folder.focus();
};
// Block bodies on purpose: an on<event> handler that returns false cancels the
// event, and `e.key === "Enter" && ...` is false for every other key, which
// silently swallowed all typing and Cmd/Ctrl+V.
els.folder.onkeydown = (e) => { if (e.key === "Enter") load([els.folder.value.trim()]); };
els.folder.onchange = () => { if (els.folder.value.trim()) load([els.folder.value.trim()]); };
els.context.onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing && !els.name.disabled) nameAll(); };
els.order.onchange = () => {  // numbers come and go at once, no need to name again
  autoOrder = false;
  orderHint();
  refreshCards();
};
els.folder.oninput = () => els.folder.classList.remove("bad");
els.showkey.onclick = () => {
  const show = els.key.type === "password";
  els.key.type = show ? "text" : "password";
  els.showkey.textContent = show ? "Hide" : "Show";
};
new IntersectionObserver(([e]) => { barInView = e.isIntersecting; showNext(); },
  { rootMargin: `-${document.querySelector("header").offsetHeight}px 0px 0px 0px` }).observe(document.querySelector(".bar"));
let fitting = 0;
window.addEventListener("resize", () => { cancelAnimationFrame(fitting); fitting = requestAnimationFrame(fitAll); });
els.name.onclick = nameAll;
els.updateGo.onclick = startUpdate;
els.updateLater.onclick = () => { updateLater = true; els.update.hidden = true; };
els.checkUpdates.onclick = checkUpdates;
els.rename.onclick = renameAll;
els.clear.onclick = clearAll;
els.guide.onclick = (e) => { if (e.target.matches("[data-undo]")) undo(); };
els.toast.onclick = () => (els.toast.hidden = true);
const guarded = (fn) => () => Promise.resolve().then(fn).catch((e) => toast(e.message, { error: true }));
els.gear.onclick = async () => {
  fillSettings();
  watchFilled = false;
  try { watchState = await api("watch"); } catch (e) { watchState = null; /* the rest of Settings still works */ }
  fillWatch();
  if (!els.settings.open) els.settings.showModal();
};
// A pop-up would sit behind an open dialog, so dialogs show their errors inside.
const say = (el, msg, ok = true) => { el.textContent = msg; el.className = "msg" + (ok ? "" : " err"); };
const inDialog = (el, fn) => () => Promise.resolve().then(fn).catch((e) => say(el, e.message, false));
els.editPrompts.onclick = inDialog(els.keymsg, openPrompts);
els.pshow.onclick = inDialog(els.pmsg, () => showFullPrompt(els.pfull.hidden));
els.preset.onclick = () => {  // the defaults go in the boxes; nothing is saved until Save
  const p = promptStyle(promptTab).defaults;
  els.pcategories.value = catLines(p.categories);
  els.preader.value = p.reader;
  els.prules.value = p.rules;
  say(els.pmsg, "Defaults restored. Save to keep them.");
};
els.psave.onclick = inDialog(els.pmsg, savePrompts);
els.pcancel.onclick = closePrompts;
els.prompts.addEventListener("cancel", (e) => { e.preventDefault(); closePrompts(); });  // Escape
els.cancel.onclick = () => els.settings.close();
els.save.onclick = inDialog(els.keymsg, saveSettings);  // a folder that can't be found is said in the dialog
els.wOn.onchange = () => (els.wFields.hidden = !els.wOn.checked);
els.wAuto.onchange = showAutostart;
els.wShowStartup.onclick = inDialog(els.keymsg, () => api("watch/startup-items", {}));
els.wFolder.oninput = () => els.wFolder.classList.remove("bad");
els.wPick.onclick = inDialog(els.keymsg, async () => {
  const { folder } = await api("pick-folder");
  if (folder) els.wFolder.value = folder;
});
els.wLog.onclick = inDialog(els.keymsg, () => api("watch/log", {}));
els.watchStart.onclick = guarded(async () => showWatch(await api("watch/start", {})));
els.test.onclick = guarded(testKey);
els.model.onchange = () => {
  els.custom.hidden = !!els.model.value;
  showModelNote();
  if (!els.model.value) els.custom.focus();
};
els.settings.onkeydown = (e) => {
  if (e.key === "Enter" && e.target.tagName === "INPUT") { e.preventDefault(); els.save.click(); }
};
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && !els.rename.disabled) renameAll();
  if (e.key === "," && (e.metaKey || e.ctrlKey)) { e.preventDefault(); els.gear.click(); }
});

api("status").then((s) => {
  status = s;
  profile = s.profile || profile;
  renderProfiles();
  showEmpty(false);
  fillSettings();
  if (!s.has_key) els.gear.click();  // the same way as the button, so every section is filled
  api("update").then(showUpdate).catch(() => {});  // offline: no banner, no fuss
  api("watch").then(showWatch).catch(() => {});
});
