const $ = (id) => document.getElementById(id);
const els = ["gear", "pick", "folder", "name", "rename", "progress", "empty", "grid", "toast", "undo", "stat", "drop",
  "profile", "context", "order", "settings", "key", "model", "custom", "modelnote", "keymsg", "test", "cancel",
  "save"].reduce((o, k) => (o[k] = $(k), o), {});
// sources: what the user loaded (folders and/or files); items: the files found in them.
let sources = [], items = [], status = { models: [], profiles: [] }, journal = null, toastTimer = null, profile = "propresenter";
let naming = false, loading = null;
const FOLDER_HINT = els.folder.placeholder;

async function api(path, body) {
  const r = await fetch("/api/" + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

function toast(msg, opts = {}) {
  clearTimeout(toastTimer);
  els.toast.firstElementChild.textContent = msg;
  els.toast.classList.toggle("error", !!opts.error);
  els.undo.hidden = !opts.undo;
  els.toast.hidden = false;
  els.toast.title = opts.error ? "Click to dismiss" : "";
  // Errors never auto-hide: a silent failure that scrolls past is the thing
  // this app must not do.
  if (!opts.error) toastTimer = setTimeout(() => (els.toast.hidden = true), opts.undo ? 12000 : 4500);
}

const stem = (name) => name.replace(/\.[^.]+$/, "");
const inputs = () => [...els.grid.querySelectorAll("input.name")];
const parent = (p) => p.replace(/[\\/][^\\/]*$/, "");
const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const money = (usd) => !usd ? "" : usd < 0.01 ? " for under 1c" : ` for $${usd.toFixed(2)}`;

function render() {
  els.grid.innerHTML = "";
  els.empty.hidden = items.length > 0;
  els.empty.firstElementChild.textContent = "Nothing to rename";
  els.empty.lastElementChild.textContent = "No supported files there (images, HEIC photos, PDFs, mp4, mov).";
  items.forEach((it, n) => {
    const card = document.createElement("article");
    card.className = "card";
    card.dataset.id = it.id;
    card.style.setProperty("--i", n);
    const badge = it.kind === "image" ? "" : `<span class="kind">${it.kind === "pdf" ? "PDF" : "VIDEO"}</span>`;
    card.innerHTML = `<div class="thumb"><img alt=""><span class="idx">${String(n + 1).padStart(2, "0")}</span>${badge}</div>
      <div class="meta"><div class="orig"></div><input class="name" spellcheck="false" placeholder="—" aria-label="New name"></div>`;
    if (it.thumb) card.querySelector("img").src = "data:image/jpeg;base64," + it.thumb;
    card.querySelector(".orig").textContent = card.querySelector(".orig").title = it.name;
    const inp = card.querySelector("input");
    inp.value = stem(it.name);
    inp.addEventListener("input", () => updateChanged(inp, it));
    inp.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" || e.metaKey || e.ctrlKey) return;
      const all = inputs(), next = all[all.indexOf(inp) + 1];
      next ? (next.focus(), next.select()) : inp.blur();
    });
    els.grid.appendChild(card);
  });
  updateButtons();
}

function updateChanged(inp, it) {
  const changed = inp.value.trim() !== stem(it.name);
  inp.classList.toggle("changed", changed);
  inp.closest(".card").classList.toggle("is-changed", changed);
  updateButtons();
}

function updateButtons() {
  const changed = inputs().filter((i) => i.classList.contains("changed")).length;
  els.name.disabled = !items.length || naming;
  els.rename.disabled = !changed || naming;
  els.stat.innerHTML = items.length
    ? `<b>${items.length}</b> file${items.length === 1 ? "" : "s"}${changed ? ` · <span class="on">${changed} to rename</span>` : ""}`
    : "";
}

function showSources() {
  els.folder.placeholder = FOLDER_HINT;
  if (sources.length === 1) { els.folder.value = sources[0]; return; }
  const folders = new Set(items.map((i) => parent(i.path))).size;
  els.folder.value = "";
  els.folder.placeholder = `${plural(items.length, "file")} from ${plural(folders, "folder")} (dropped)`;
}

async function load(paths) {
  paths = paths.filter(Boolean);
  if (!paths.length) return;
  if (naming) return toast("Wait for naming to finish before loading more files.", { error: true });
  const run = (async () => {
    try {
      items = (await api("scan", { paths })).items;
      sources = paths;
      render();
      showSources();
      els.progress.hidden = true;
    } catch (e) { toast(e.message, { error: true }); }
  })();
  loading = run;
  try { await run; } finally { if (loading === run) loading = null; }
}

async function nameAll() {
  // A path typed and then left by clicking this button starts loading first;
  // name what that load shows, not the list it is about to replace.
  if (loading) await loading;
  if (naming || !items.length) return;
  naming = true;
  els.undo.hidden = true;  // undoing now would rename files the job is reading
  els.name.disabled = els.rename.disabled = true;
  els.progress.hidden = false;
  els.progress.className = "busy";
  els.progress.firstElementChild.style.width = "0";
  inputs().forEach((i) => (i.closest(".card").className = "card pending", i.disabled = true));
  try {
    const { job } = await api("name", {
      paths: items.map((i) => i.path), profile, context: els.context.value.trim(), keep_order: els.order.checked,
    });
    let r;
    do {
      await new Promise((res) => setTimeout(res, 700));
      r = await api("name/" + job);
      els.progress.firstElementChild.style.width = (r.total ? (r.progress / r.total) * 90 : 0) + "%";
    } while (!r.done);
    if (r.error) throw new Error(r.error);
    let errors = 0, missing = 0, why = null;
    for (const it of items) {
      const res = r.results[it.path], inp = els.grid.querySelector(`[data-id="${it.id}"] input`);
      inp.closest(".card").className = "card" + (res && !res.error ? "" : " error");
      if (!res) { missing++; inp.title = "This file was not there when naming ran. Load the folder again."; continue; }
      if (res.error) { errors++; inp.title = res.error; why = why || res.error; }
      if (res.proposed) { inp.value = res.proposed; updateChanged(inp, it); }
    }
    els.progress.firstElementChild.style.width = "100%";
    const bad = errors + missing;
    toast(why ? why
      : missing ? `${plural(missing, "file")} ${missing === 1 ? "is" : "are"} no longer there. Load the folder again before renaming.`
      : errors ? `Named ${items.length - errors} of ${items.length}${money(r.cost)}. ${errors} could not be read.`
      : `Named ${plural(items.length, "file")}${money(r.cost)}. Review, edit, then Rename all.`, { error: bad > 0 });
    inputs()[0] && inputs()[0].focus();
  } catch (e) {
    toast(e.message, { error: true });
    inputs().forEach((i, n) => { i.closest(".card").className = "card"; updateChanged(i, items[n]); });
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
  const changed = items.map((it, i) => ({ path: it.path, new_name: inp[i].value.trim() }))
    .filter((x, i) => x.new_name && x.new_name !== stem(items[i].name));
  if (!changed.length) return;
  try {
    const r = await api("rename", { items: changed });
    journal = r.journal;
    follow(r.moved);
    const msg = `Renamed ${plural(r.renamed, "file")}`;
    toast(r.error ? `${msg}, then stopped: ${r.error}` : msg, { undo: r.renamed > 0, error: !!r.error });
    await load(sources);
  } catch (e) { toast(e.message, { error: true }); }
}

async function undo() {
  if (naming) return;  // the button is hidden while naming; this guards a stray click
  try {
    const r = await api("undo", { journal });
    journal = null;
    follow(r.moved);
    toast(`Restored ${plural(r.restored, "file")}`);
    await load(sources);
  } catch (e) { toast(e.message, { error: true }); }
}

function renderProfiles() {
  els.profile.innerHTML = "";
  for (const p of status.profiles) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = p.label;
    b.setAttribute("role", "radio");
    b.setAttribute("aria-checked", String(p.id === profile));
    b.title = p.id === "propresenter" ? "Names for the ProPresenter media bin: Category - Subject - Detail"
      : "Names for everyday files on disk: date first when the file has one";
    b.onclick = () => { profile = p.id; renderProfiles(); };
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
  els.key.placeholder = status.has_key ? "•••••••• (saved, leave blank to keep)" : "sk-or-…";
  els.keymsg.textContent = "";
  els.keymsg.className = "msg";
  showModelNote();
}

async function saveSettings() {
  const body = { model: els.model.value || els.custom.value.trim() || status.model };
  if (els.key.value.trim()) body.key = els.key.value.trim();
  status = await api("settings", body);
  fillSettings();
  els.settings.close();
  toast("Settings saved");
}

async function testKey() {
  els.keymsg.textContent = "Checking…";
  els.keymsg.className = "msg";
  const r = await api("check-key", { key: els.key.value.trim() });
  els.keymsg.textContent = r.ok ? `Key works${r.label ? " (" + r.label + ")" : ""}` : r.error;
  els.keymsg.className = "msg " + (r.ok ? "ok" : "err");
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
  paths.length ? load(paths) : toast("Could not read the dropped items. Try Pick folder.", { error: true });
};

els.pick.onclick = async () => {
  const { folder } = await api("pick-folder");
  if (folder) load([folder]); else els.folder.focus();
};
// Block bodies on purpose: an on<event> handler that returns false cancels the
// event, and `e.key === "Enter" && ...` is false for every other key, which
// silently swallowed all typing and Cmd/Ctrl+V.
els.folder.onkeydown = (e) => { if (e.key === "Enter") load([els.folder.value.trim()]); };
els.folder.onchange = () => { if (els.folder.value.trim()) load([els.folder.value.trim()]); };
els.name.onclick = nameAll;
els.rename.onclick = renameAll;
els.undo.onclick = undo;
els.toast.onclick = (e) => { if (e.target !== els.undo) els.toast.hidden = true; };
els.gear.onclick = () => { fillSettings(); els.settings.showModal(); };
els.cancel.onclick = () => els.settings.close();
const guarded = (fn) => () => fn().catch((e) => toast(e.message, { error: true }));
els.save.onclick = guarded(saveSettings);
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
  els.order.checked = !!s.keep_order;
  renderProfiles();
  fillSettings();
  if (!s.has_key) els.settings.showModal();
});
