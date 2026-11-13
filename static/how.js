// The folders map (Settings → Folders → Open, or Set up folders on the start screen): the
// folders as one flow, from the office's Google Drive folders through Smart Explorer to
// ProPresenter and RunsheetPilot. Folders are added, named and taken out here, a loop's video
// folder is chosen here, and Save saves them as Settings' Save does. A row of the map with no
// folders yet shows dashed examples, so the map always explains itself.
// Design: docs/superpowers/specs/2026-11-09-how-it-works-guide-design.md
const HOW_MAC = /Mac/.test(navigator.platform);
const howExample = (name, loop) => ({ path: name, name: loop ? name + " loop" : name, rename: !loop, render: loop,
  output: loop ? "Loop videos" : "", example: true });
const HOW_SLIDES = ["Preach", "Announcements", "Service slides"].map((n) => howExample(n, false));
const HOW_LOOPS = ["Pre-service", "Post-service"].map((n) => howExample(n, true));
const HOW_OFFICE = [
  { key: "new", label: "New announcement" },
  { key: "swap", label: "Change or remove one" },
  { key: "both", label: "Used in two places" },
  { key: "loop", label: "Birthday screen" },
];
const HOW_SETUP = [
  { key: "c1", label: "1. Google Drive" },
  { key: "c2", label: "2. Smart Explorer" },
  { key: "c3", label: "3. ProPresenter" },
];
const HOW_JOBS = "new swap both loop";
let howPicked = "", howLanes = null, howBefore = "";

const howName = (r) => r.name.trim() || folderName(r.path);
// The end of a path, "…\Drive\Announcements" (the whole of it shows on hover).
function howShort(p) {
  const sep = p.includes("\\") ? "\\" : "/", parts = p.replace(/[\\/]+$/, "").split(/[\\/]/);
  return parts.length > 3 ? "…" + sep + parts.slice(-2).join(sep) : p;
}
function howPath(p, cls) {
  const e = make("small", cls, howShort(p));
  e.title = p;
  return e;
}
const howSame = (a, b) => !!a && !!b && folderKey(a) === folderKey(b);
const howState = () => JSON.stringify({ rows: watchRows, on: els.wOn.checked });

// The map's two rows: slide folders (renamed) and loop folders (made into videos), with
// examples for a row that has none. A folder with both ticks is in both. outputs: the folders
// the videos go to, each once (ProPresenter links each once). slide and loop are the folders
// the office's buttons talk about.
function howRead(rows) {
  const slides = rows.filter((r) => r.rename), loops = rows.filter((r) => r.render);
  const l = { slides: slides.length ? slides : HOW_SLIDES, loops: loops.length ? loops : HOW_LOOPS, outputs: [] };
  for (const r of l.loops) {
    const key = folderKey(r.output);
    let out = l.outputs.find((o) => o.key === key);
    if (!out) l.outputs.push(out = { key, path: cleanFolder(r.output), rows: [] });
    out.rows.push(r);
  }
  l.slide = l.slides.find((r) => /announce|notice/i.test(howName(r))) || l.slides[0];
  l.loop = l.loops.find((r) => /post|end/i.test(howName(r))) || l.loops[l.loops.length - 1];
  return l;
}

// An element the office's and set-up buttons light up: on lists the buttons it belongs to.
function hm(tag, cls, on) {
  const e = make(tag, cls);
  if (on !== undefined) e.dataset.on = on;
  return e;
}

function at(e, col, row) {
  e.style.gridColumn = col;
  e.style.gridRow = row;
  return e;
}

// A folder in the Google Drive column: its name to type over, where it is, and × to take
// it out of this row of the map (out of Smart Explorer once it is in neither).
function howFolder(r, lane, on, bad) {
  // Set it up's step 2 lights what is changed here: the names, + Add a folder and where videos go.
  const c = hm("div", "hm-chip hm-out" + (r.example ? " ghost" : "") + (howSame(bad, r.path) ? " bad" : ""), r.example ? on : `c2 ${on}`);
  if (r.example) {
    c.title = "An example: add your own with + Add a folder";
    c.append(make("b", "", r.name));
    return c;
  }
  const top = make("div", "hm-top"), name = make("input"), x = make("button", "hm-x", "×");
  name.type = "text";
  name.value = r.name;
  name.spellcheck = false;
  name.setAttribute("aria-label", "Name for " + r.path);
  name.oninput = () => { r.name = name.value; c.classList.remove("bad"); howNames(r); };
  x.type = "button";
  x.setAttribute("aria-label", `Take ${howName(r)} off the map`);
  x.onclick = () => {
    r[lane === "loop" ? "render" : "rename"] = false;
    if (!r.rename && !r.render) watchRows.splice(watchRows.indexOf(r), 1);
    renderFolders();
  };
  top.append(name, x);
  // The Sunday check expects something new in it every week, unless this is unticked.
  const weekly = make("label", "hm-weekly"), tick = make("input");
  tick.type = "checkbox";
  tick.checked = r.weekly !== false;
  tick.onchange = () => { r.weekly = tick.checked; };
  weekly.append(tick, make("span", "", "Changes every week"));
  c.append(top, howPath(r.path), weekly);
  return c;
}

// Where a folder's name shows elsewhere on the map, as it is typed.
function howLabel(r, cls, ext = "") {
  const e = make("b", cls, howName(r) + ext);
  e.dataset.name = String(watchRows.indexOf(r));
  e.dataset.ext = ext;
  return e;
}

function howNames(r) {
  const i = String(watchRows.indexOf(r));
  document.querySelectorAll("#howMap [data-name]").forEach((e) => {
    if (e.dataset.name === i) e.textContent = howName(r) + e.dataset.ext;
  });
}

// One loop's video in the ProPresenter column: a smart playlist like the slide folders', on
// the folder this video goes to. Each video has its own folder, so two can go to two places.
function howVideo(r, l, bad) {
  const out = cleanFolder(r.output);
  const box = hm("div", "hm-videos hm-in pp" + (r.example ? " ghost" : "") + (!r.example && !out ? " need" : "")
    + (howSame(bad, out) ? " bad" : ""), `c3${r.example ? "" : " c2"} loop${r === l.loop ? " both" : ""}`);
  const where = make("small", "hm-vfolder", "Smart playlist: " + (out ? folderName(out) : "no folder yet"));
  where.title = out;
  box.append(howLabel(r, "hm-vtitle", ".mp4"), where);
  if (r.example) return box;
  const pick = inDialog($("howMsg"), () => howOutput(r));
  if (out) box.append(linkButton("Change folder", pick));
  else {
    const b = make("button", "hm-add", "Choose a folder for this video");
    b.type = "button";
    b.onclick = pick;
    box.append(b);
  }
  return box;
}

// Where a slide folder's named files end up, in the ProPresenter column: the folder its smart
// playlist links. From a drop folder they move there, so ProPresenter never sees a file renamed;
// named where they are, ProPresenter can lose track of one it saw before it was named.
function howTarget(r, on, bad) {
  const dest = cleanFolder(r.move_to || "");
  const box = hm("div", "hm-videos hm-in pp" + (r.example ? " ghost" : "") + (!r.example && !dest ? " need" : "")
    + (howSame(bad, dest) ? " bad" : ""), `c3${r.example ? "" : " c2"} ${on}`);
  const where = make("small", "hm-vfolder", "Smart playlist: " + (r.example ? howName(r) : folderName(dest || r.path)));
  where.title = dest || r.path;
  box.append(howLabel(r, "hm-vtitle"), where);
  if (r.example) return box;
  const pick = inDialog($("howMsg"), () => howMoveTo(r));
  if (dest) box.append(linkButton("Change folder", pick));
  else {
    box.append(make("small", "hm-hint", "Renamed where it is, so ProPresenter can lose track of a file it saw first."));
    const b = make("button", "hm-add", "Choose a folder for named files");
    b.type = "button";
    b.onclick = pick;
    box.append(b);
  }
  return box;
}

async function howMoveTo(r) {
  const path = await howPick();
  if (!path) return;
  r.move_to = path;
  say($("howMsg"), "");
  renderFolders();
}

function howAddButton(lane) {
  const b = hm("button", "hm-add", "c1 c2");
  b.type = "button";
  b.textContent = "+ Add a folder";
  b.onclick = inDialog($("howMsg"), () => howAdd(lane));
  return b;
}

// The whole map, from watchRows as they stand. bad: a folder to mark (Save found it wrong).
function howDraw(bad) {
  const l = howLanes = howRead(watchRows), grid = make("div", "hm-grid");
  for (const c of [1, 3, 5]) grid.append(at(make("div", "hm-zone"), c, "1 / 4"));
  for (const [c, title, sub] of [[1, "Google Drive", HOW_MAC ? "Syncs to this Mac" : "Syncs to this PC"],
    [3, "Smart Explorer", "Runs by itself on this computer"], [5, "ProPresenter", "Smart playlists"]]) {
    const h = at(make("div", "hm-head"), c, 1);
    h.append(make("b", "", title), make("small", "", sub));
    grid.append(h);
  }

  // Slide folders: named where they are, a playlist for each.
  // Each place has its own colour: Google Drive blue, Smart Explorer purple, ProPresenter green.
  const from = at(make("div", "hm-col drive"), 1, 2), to = at(make("div", "hm-col"), 5, 2);
  for (const r of l.slides) {
    const on = r === l.slide ? "new swap both" : "";
    from.append(howFolder(r, "slide", `c1 ${on}`, bad));
    to.append(howTarget(r, on, bad));
  }
  from.append(howAddButton("slide"));
  const real = l.slides.filter((r) => !r.example), moving = real.filter((r) => cleanFolder(r.move_to || "")).length;
  const names = at(hm("div", "hm-box se", "c2 new swap both"), 3, 2);
  names.append(make("b", "", "Names each new file"), make("span", "", "IMG_2231.png becomes Welcome Home.png"),
    make("span", "", !real.length || moving === real.length ? "Then moves it to a different folder"
      : moving ? "Moves it on, where a folder is chosen" : "It stays in the same folder"));
  grid.append(from, names, to);

  // Loop folders: two steps, because the video ends up in another folder.
  const lfrom = at(make("div", "hm-col drive"), 1, 3), steps = at(make("div", "hm-steps"), 3, 3), lto = at(make("div", "hm-col"), 5, 3);
  for (const r of l.loops) lfrom.append(howFolder(r, "loop", `c1 loop${r === l.loop ? " both" : ""}`, bad));
  lfrom.append(howAddButton("loop"));
  [["Step 1", "Makes one video", "From all its screens"], ["Step 2", "Saves the video", "To a different folder"]].forEach(([step, title, sub], n) => {
    const s = hm("div", "hm-box se" + (n ? " hm-in hm-near" : ""), "c2 loop both");
    s.append(make("small", "", step), make("b", "", title), make("span", "", sub));
    steps.append(s);
  });
  for (const r of l.loops) lto.append(howVideo(r, l, bad));
  grid.append(lfrom, steps, lto);

  const office = hm("div", "hm-band", HOW_JOBS), lines = make("span");
  lines.append(make("span", "", "drops each slide or screen in the right Google Drive folder, and deletes old ones."),
    make("span", "", "Used in two places? Drop it in both. Everything below happens by itself."));
  office.append(make("b", "", "The office"), lines);
  const rp = hm("div", "hm-band", HOW_JOBS);
  rp.append(make("b", "", "RunsheetPilot"), make("span", "", "reads the file names and puts the right screens into Sunday's playlist in ProPresenter"));
  $("howMap").replaceChildren(office, hm("div", "hm-down", HOW_JOBS), grid, hm("div", "hm-down hm-right", HOW_JOBS), rp);
  $("howNote").textContent = "Add folders with + Add a folder: slide folders in the top row, loop folders in the bottom one."
    + (l.slides[0].example || l.loops[0].example ? " Dashed ones are examples." : "");
  howShow();
}

// A folder from the computer's folder window (in a plain browser, a pasted path).
async function howPick() {
  if (!window.pywebview) return cleanFolder(prompt("Paste the folder's path") || "");
  return cleanFolder((await api("pick-folder")).folder || "");
}

// Adds a folder to a row of the map. A loop starts with the folder the other videos go to.
async function howAdd(lane) {
  const path = await howPick();
  if (!path) return;
  let row = watchRows.find((r) => howSame(r.path, path));
  if (!row) {
    if (watchRows.length >= MAX_FOLDERS) throw new Error(`Smart Explorer can watch up to ${MAX_FOLDERS} folders.`);
    const outs = new Map(watchRows.filter((r) => r.render && cleanFolder(r.output)).map((r) => [folderKey(r.output), cleanFolder(r.output)]));
    row = { path, name: folderName(path), rename: false, render: false, output: outs.size === 1 ? [...outs.values()][0] : "",
      weekly: true, move_to: "" };
    watchRows.push(row);
  }
  row[lane === "loop" ? "render" : "rename"] = true;
  say($("howMsg"), "");
  renderFolders();
}

// Where one loop's video goes: only that loop's, so the loops can go to different folders.
async function howOutput(r) {
  const path = await howPick();
  if (!path) return;
  r.output = path;
  say($("howMsg"), "");
  renderFolders();
}

// "Pre-service, Post-service or both"
function howEither(names) {
  return names.length === 1 ? names[0] : names.length === 2 ? `${names[0]}, ${names[1]} or both` : "the loop folders it belongs in";
}

// What one of the office's buttons says.
function howJob(key, l) {
  // The folders the office sees in Drive: where it drops a file, and (from a drop folder) where the named one lands.
  const a = howName(l.slide), moved = l.slide.example || cleanFolder(l.slide.move_to || "");
  const drop = l.slide.example ? `${a} - drop here` : folderName(l.slide.path);
  const ready = l.slide.example ? a : moved ? folderName(l.slide.move_to) : drop;
  const loopDrop = folderName(l.loop.path);
  return {
    new: `Drop it in ${drop} in Google Drive. Smart Explorer names it${moved ? ` and moves it to ${ready}` : ""}, and it shows up in the ${a} playlist, ready for RunsheetPilot.`,
    swap: `Delete the old file from ${ready} and drop the new one in ${drop}. It gets a proper name like any new file, and the old one leaves the playlist. Removing one? Just delete it from ${ready}.`,
    both: `Drop it in both ${drop} and ${loopDrop}. The copy in ${drop} gets named${moved ? ` and moves to ${ready}` : ""}, and the copy in ${loopDrop} goes into its video.`,
    loop: `It isn't an announcement, it's for the loop: drop it in ${howEither(l.loops.map((r) => folderName(r.path)))}, and delete it when it's finished with. The video is remade by itself, never during service times.`,
  }[key];
}

// The folders ProPresenter links to: where named slides end up, and where the videos go. Never
// a drop folder or a loop's own folder.
function howPlaylists(l) {
  const list = make("ul", "how-paths");
  const add = (name, path) => {
    const li = make("li");
    li.append(make("b", "", name));
    if (path) li.append(make("small", "", path));
    list.appendChild(li);
  };
  l.slides.forEach((r) => add(howName(r), !r.example && (cleanFolder(r.move_to || "") || r.path)));
  l.outputs.filter((o) => o.path).forEach((o) => add(folderName(o.path), !o.rows[0].example && o.path));
  return list;
}

// What one of the set-up buttons says, as numbered steps (a step can be text plus a list).
function howSteps(key, l) {
  if (key === "c1") {
    return [`Click the Google Drive icon ${HOW_MAC ? "in the menu bar" : "near the clock"}, then the gear, then Preferences.`,
      "Click My Computer, then Add folder, and pick the folder.",
      "Tick Sync with Google Drive and confirm.",
      "Do this for every folder in the Google Drive column, and for the folders named slides move to, so the office can delete old ones. A folder already in My Drive needs none of this.",
      "Don't sync the folder the videos go to: it stays on this computer."];
  }
  if (key === "c2") {
    return [...(status.has_key ? [] : ["Paste your OpenRouter key at the top of Settings and click Test key. Naming needs it; videos don't."]),
      "Slide folders: click + Add a folder in the top row and pick the drop folder, the one the office drops files in. Then choose a folder for named files in the ProPresenter column: the one its smart playlist links.",
      "Loop folders: click + Add a folder in the bottom row, then Choose a folder for this video in the ProPresenter column: one outside Google Drive.",
      "Type over a name to change it. A loop's name is its video's name, which RunsheetPilot looks for.",
      "Tick Watch these folders by itself, then click Save.",
      "Service times and starting with the computer are in Settings, under Folders."];
  }
  const steps = ["Do this outside a service: clicking an item in the Media Bin can put it live.",
    "In ProPresenter's Media Bin, click + at the lower left, then click New Smart Playlist.",
    ["Choose the folder. Do this once for each:", howPlaylists(l)]];
  const drops = [...l.slides.filter((r) => !r.example && cleanFolder(r.move_to || "")), ...l.loops.filter((r) => !r.example)];
  if (drops.length) steps.push(`Don't link ${drops.map((r) => folderName(r.path)).join(" or ")}: only the folders named files and videos go to.`);
  steps.push("RunsheetPilot finds these playlists by itself.");
  return steps;
}

// What is lit, which button is pressed, and what it says.
function howShow() {
  document.querySelectorAll(".how-row button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === howPicked)));
  document.querySelectorAll("#howMap [data-on]").forEach((e) =>
    e.classList.toggle("how-dim", !!howPicked && !e.dataset.on.split(" ").includes(howPicked)));
  const out = $("howOut");
  if (!howPicked) return out.replaceChildren();
  if (!howPicked.startsWith("c")) return out.replaceChildren(make("p", "", howJob(howPicked, howLanes)));
  const list = make("ol");
  for (const step of howSteps(howPicked, howLanes)) {
    const li = make("li");
    li.append(...[].concat(step));
    list.appendChild(li);
  }
  out.replaceChildren(list);
}

function howButtons(box, list) {
  box.replaceChildren(...list.map(({ key, label }) => {
    const b = make("button", "", label);
    b.type = "button";
    b.dataset.key = key;
    b.onclick = () => { howPicked = howPicked === key ? "" : key; howShow(); };
    return b;
  }));
}

// On top of Settings, which stays open: the map changes Settings' folders, and Cancel puts them back.
function howOpen() {
  howBefore = howState();
  howPicked = "";
  $("howOn").checked = els.wOn.checked;
  say($("howMsg"), "");
  $("how").showModal();
  howDraw();
}

function howCancel() {
  if (howState() !== howBefore && !confirm("Close without saving your changes to the folders?")) return;
  const was = JSON.parse(howBefore);
  watchRows = was.rows;
  els.wOn.checked = was.on;
  els.wFields.hidden = !was.on;
  $("how").close();
  renderFolders();
}

async function howSave() {
  if (!watchState || !watchFilled) throw new Error("Smart Explorer couldn't read its folder settings. Close Settings and open it again.");
  if (!(await saveWatch())) return;
  $("how").close();
  renderFolders();
  say(els.keymsg, "Folders saved.");
}

howButtons($("howOffice"), HOW_OFFICE);
howButtons($("howSetup"), HOW_SETUP);
$("howOpen").onclick = howOpen;
$("autoOpen").onclick = guarded(async () => { await els.gear.onclick(); howOpen(); });
$("howCancel").onclick = howCancel;
$("how").addEventListener("cancel", (e) => { e.preventDefault(); howCancel(); });  // Escape
$("how").querySelector("form").onsubmit = (e) => e.preventDefault();  // Enter in a name box must not close the map
$("howSave").onclick = inDialog($("howMsg"), howSave);
$("howOn").onchange = () => { els.wOn.checked = $("howOn").checked; els.wFields.hidden = !els.wOn.checked; };
