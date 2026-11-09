// How it works (Settings → Folders): one flow diagram of what Smart Explorer does between
// Google Drive, ProPresenter and RunsheetPilot, drawn from the Folders table as it stands
// (example folders until there are some), with the office's jobs and the set-up steps a
// click away. It only reads: nothing here changes a setting.
// Design: docs/superpowers/specs/2026-11-09-how-it-works-guide-design.md
const HOW_MAC = /Mac/.test(navigator.platform);
const HOW_EXAMPLE = [
  { path: "Preach", name: "Preach", rename: true, render: false, output: "" },
  { path: "Announcements", name: "Announcements", rename: true, render: false, output: "" },
  { path: "Service slides", name: "Service slides", rename: true, render: false, output: "" },
  { path: "Pre-service", name: "Pre-service loop", rename: false, render: true, output: "Loop videos" },
  { path: "Post-service", name: "Post-service loop", rename: false, render: true, output: "Loop videos" },
];
const HOW_OFFICE = [
  { key: "new", label: "New announcement", needs: "slide" },
  { key: "swap", label: "Change or remove one", needs: "slide" },
  { key: "both", label: "Used in two places", needs: "both" },
  { key: "loop", label: "Birthday screen", needs: "loop" },
];
const HOW_SETUP = [
  { key: "c1", label: "1. Google Drive" },
  { key: "c2", label: "2. Smart Explorer" },
  { key: "c3", label: "3. ProPresenter" },
];
const HOW_EVERY_JOB = "new swap both loop";
let howPicked = "", howLanes = null;

// The table as the diagram needs it. A row with both ticks is in both lanes. Each video goes
// under the folder it is saved in. slide and loop are the folders the office's examples use.
function howRead(rows) {
  const example = !rows.length, use = example ? HOW_EXAMPLE : rows;
  const slides = use.filter((r) => r.rename), loops = use.filter((r) => r.render), outputs = [];
  for (const r of loops) {
    const key = folderKey(r.output);
    let out = outputs.find((o) => o.key === key);
    if (!out) outputs.push(out = { key, path: cleanFolder(r.output), rows: [] });
    out.rows.push(r);
  }
  const named = (r) => folderName(r.path);
  return {
    example, slides, loops, outputs, named,
    slide: slides.find((r) => /announce|notice/i.test(named(r))) || slides[0],
    loop: loops.find((r) => /post|end/i.test(named(r))) || loops[loops.length - 1],
  };
}

function howNode(parent, tag, attrs, text) {
  const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const k of Object.keys(attrs || {})) e.setAttribute(k, attrs[k]);
  if (text) e.textContent = text;
  parent.appendChild(e);
  return e;
}

// A line of text. Given a width, it is shortened to fit, with the whole of it on hover.
function howText(parent, cls, x, y, text, { middle, width } = {}) {
  const t = howNode(parent, "text", { class: cls, x, y, "dominant-baseline": "central", "text-anchor": middle ? "middle" : "start" }, text);
  if (width && t.getComputedTextLength() > width) {
    let n = text.length;
    while (n > 1 && t.getComputedTextLength() > width) t.textContent = text.slice(0, --n) + "…";
    howNode(t, "title", {}, text);
  }
  return t;
}

// Drawn with the dialog open: howText has to measure.
function howDraw(l) {
  const ROW = 32, ROW_GAP = 6, LANE_GAP = 16, TOP = 156;
  const stack = (n) => n * ROW + (n - 1) * ROW_GAP;
  const outs = l.outputs.length ? l.outputs : [{ key: "", path: "", rows: [] }];
  const outH = (o) => 42 + Math.max(o.rows.length, 1) * 20, OUT_GAP = 8;
  const slideH = Math.max(stack(Math.max(l.slides.length, 1)), 108);
  const outsH = outs.reduce((sum, o) => sum + outH(o), 0) + (outs.length - 1) * OUT_GAP;
  const loopH = Math.max(stack(Math.max(l.loops.length, 1)), outsH, 90);
  const loopY = TOP + slideH + LANE_GAP, zoneEnd = loopY + loopH + 14, H = zoneEnd + 28 + 44 + 8;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 680 ${H}`);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "The office changes files in Google Drive. Smart Explorer names slide files where they are, and turns each loop folder "
    + "into one video saved in a different folder. ProPresenter's smart playlists show them, and RunsheetPilot builds the service from them.");
  $("howMap").replaceChildren(svg);
  const marker = howNode(howNode(svg, "defs"), "marker", { id: "howArrow", viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto" });
  howNode(marker, "path", { d: "M2 1L8 5L2 9", fill: "none", stroke: "#667085", "stroke-width": 1.5, "stroke-linecap": "round", "stroke-linejoin": "round" });

  const group = (on, cls) => howNode(svg, "g", { "data-on": on, class: cls || "" });
  const edge = (x1, y1, x2, y2, on) => howNode(svg, "line", { class: "how-edge", x1, y1, x2, y2, "marker-end": "url(#howArrow)", "data-on": on });
  const row = (x, y, label, on, cls) => {
    const g = group(on, cls);
    howNode(g, "rect", { class: label ? "how-box" : "how-empty", x, y, width: x === 16 ? 116 : 148, height: ROW, rx: 6 });
    howText(g, "how-s", x + (x === 16 ? 58 : 74), y + ROW / 2, label || "No folder yet", { middle: true, width: x === 16 ? 104 : 136 });
  };
  const band = (y, h, title, lines, on) => {
    const g = group(on);
    howNode(g, "rect", { class: "how-box", x: 8, y, width: 664, height: h, rx: 8 });
    howText(g, "how-t", 24, y + h / 2, title);
    const x = title === "The office" ? 104 : 130;
    lines.forEach((t, i) => howText(g, "how-s", x, y + h / 2 + (i - (lines.length - 1) / 2) * 18, t));
  };

  // The office at the top, RunsheetPilot at the foot, and the three places between them.
  band(12, 56, "The office", ["drops each slide or screen in the right Google Drive folder, and deletes old ones.",
    "Used in two places? Drop it in both. Everything below happens by itself."], HOW_EVERY_JOB);
  edge(74, 70, 74, 94, HOW_EVERY_JOB);
  for (const [x, w, title, sub] of [[8, 132, "Google Drive", HOW_MAC ? "Syncs to this Mac" : "Syncs to this PC"],
    [164, 320, "Smart Explorer", "Runs by itself on this computer"], [508, 164, "ProPresenter", "Smart playlists"]]) {
    howNode(svg, "rect", { class: "how-zone", x, y: 96, width: w, height: zoneEnd - 96, rx: 12 });
    howText(svg, "how-t", x + 12, 116, title);
    howText(svg, "how-s", x + 12, 134, sub);
  }

  // Slide folders: named where they are, one playlist for each.
  const slidesY = TOP + (slideH - stack(Math.max(l.slides.length, 1))) / 2;
  (l.slides.length ? l.slides : [null]).forEach((r, i) => {
    const y = slidesY + i * (ROW + ROW_GAP), mid = y + ROW / 2, on = r && r === l.slide ? "new swap both" : "";
    row(16, y, r && l.named(r), `c1 ${on}`);
    edge(134, mid, 174, mid, on);
    edge(474, mid, 514, mid, on);
    row(516, y, r && l.named(r), `c3 ${on}`, r ? "how-name" : "");
  });
  const name = group("c2 new swap both", "how-name");
  howNode(name, "rect", { x: 176, y: TOP, width: 296, height: slideH, rx: 8 });
  howText(name, "how-t", 324, TOP + slideH / 2 - 22, "Names each new file", { middle: true });
  howText(name, "how-s", 324, TOP + slideH / 2, "IMG_2231.png becomes Welcome Home.png", { middle: true });
  howText(name, "how-s", 324, TOP + slideH / 2 + 20, "It stays in the same folder", { middle: true });

  // Loop folders: two steps, because the video ends up somewhere else.
  const loopsY = loopY + (loopH - stack(Math.max(l.loops.length, 1))) / 2, loopMid = loopY + loopH / 2;
  (l.loops.length ? l.loops : [null]).forEach((r, i) => {
    const y = loopsY + i * (ROW + ROW_GAP), on = r ? `loop${r === l.loop ? " both" : ""}` : "";
    row(16, y, r && l.named(r), `c1 ${on}`);
    edge(134, y + ROW / 2, 174, y + ROW / 2, on);
  });
  [[176, "Step 1", "Makes one video", "From all its screens"], [332, "Step 2", "Saves the video", "To a different folder"]].forEach(([x, step, title, sub]) => {
    const g = group("c2 loop both", "how-video");
    howNode(g, "rect", { x, y: loopY, width: 140, height: loopH, rx: 8 });
    howText(g, "how-s", x + 70, loopMid - 22, step, { middle: true });
    howText(g, "how-t", x + 70, loopMid, title, { middle: true });
    howText(g, "how-s", x + 70, loopMid + 22, sub, { middle: true });
  });
  edge(317, loopMid, 331, loopMid, "loop both");
  let y = loopY + (loopH - outsH) / 2;
  for (const o of outs) {
    const on = `loop${o.rows.includes(l.loop) ? " both" : ""}`, g = group(`c3 ${o.rows.length ? on : ""}`, o.rows.length ? "how-video" : "");
    howNode(g, "rect", { class: o.rows.length ? "" : "how-empty", x: 516, y, width: 148, height: outH(o), rx: 8 });
    howText(g, "how-t", 590, y + 19, o.path ? folderName(o.path) : o.rows.length ? "Choose a folder" : "No video yet", { middle: true, width: 136 });
    o.rows.forEach((r, i) => howText(g, "how-s", 590, y + 42 + i * 20, r.name, { middle: true, width: 136 }));
    edge(474, y + outH(o) / 2, 514, y + outH(o) / 2, on);
    y += outH(o) + OUT_GAP;
  }

  edge(590, zoneEnd + 2, 590, zoneEnd + 26, HOW_EVERY_JOB);
  band(zoneEnd + 28, 44, "RunsheetPilot", ["reads the file names and puts the right screens into Sunday's playlist in ProPresenter"], HOW_EVERY_JOB);
}

// "Pre-service, Post-service or both"
function howEither(names) {
  return names.length === 1 ? names[0] : names.length === 2 ? `${names[0]}, ${names[1]} or both` : "the loop folders it belongs in";
}

// What one of the office's buttons says.
function howJob(key, l) {
  const a = l.slide && l.named(l.slide), b = l.loop && l.named(l.loop);
  return {
    new: `Drop it in ${a} in Google Drive. Smart Explorer names it, and it shows up in the ${a} playlist, ready for RunsheetPilot.`,
    swap: `Delete the old file from ${a} and drop the new one in. It gets a proper name like any new file, and the old one leaves the playlist. Removing one? Just delete it.`,
    both: `Drop it in both ${a} and ${b}. The copy in ${a} gets named, and the copy in ${b} goes into its video.`,
    loop: `It isn't an announcement, it's for the loop: drop it in ${howEither(l.loops.map(l.named))}, and delete it when it's finished with. The video is remade by itself, never during service times.`,
  }[key];
}

// The folders ProPresenter links to: the slide folders, and where the videos go. Never a loop's own folder.
function howPlaylists(l) {
  const list = make("ul", "how-paths");
  const add = (path) => {
    const li = make("li");
    li.append(make("b", "", folderName(path)));
    if (!l.example) li.append(make("small", "", path));
    list.appendChild(li);
  };
  l.slides.forEach((r) => add(r.path));
  l.outputs.filter((o) => o.path).forEach((o) => add(o.path));
  return list;
}

// What one of the set-up buttons says, as numbered steps (a step can be text plus a node).
function howSteps(key, l) {
  if (key === "c1") {
    return [`Click the Google Drive icon ${HOW_MAC ? "in the menu bar" : "near the clock"}, then the gear, then Preferences.`,
      "Click My Computer, then Add folder, and pick the folder.",
      "Tick Sync with Google Drive and confirm.",
      "Do this for every folder in the Google Drive column. A folder already in My Drive needs none of this.",
      "Don't sync the folder the videos go to: it stays on this computer."];
  }
  if (key === "c2") {
    const auto = (watchState || {}).can_autostart ? ", tick Start by itself when the computer starts" : "";
    return [...(status.has_key ? [] : ["Paste your OpenRouter key at the top of Settings and click Test key. Naming needs it; videos don't."]),
      "Tick Watch these folders by itself.",
      "Add each folder: click Choose, pick it, then click Add.",
      "Slide folders: leave Rename new files ticked.",
      "Loop folders: untick Rename new files, tick Render into video, then choose a different folder under Save video to.",
      `Add your service times${auto}, then click Save.`];
  }
  const steps = ["Do this outside a service: clicking an item in the Media Bin can put it live.",
    "In ProPresenter's Media Bin, click + at the lower left, then click New Smart Playlist.",
    ["Choose the folder. Do this once for each:", howPlaylists(l)]];
  if (l.loops.length) steps.push(`Don't link ${l.loops.map(l.named).join(" or ")}: only the folder their videos go to.`);
  steps.push("RunsheetPilot finds these playlists by itself.");
  return steps;
}

function howChoose(key) {
  howPicked = howPicked === key ? "" : key;
  document.querySelectorAll(".how-row button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === howPicked)));
  document.querySelectorAll("#howMap [data-on]").forEach((e) =>
    e.classList.toggle("how-dim", !!howPicked && !e.dataset.on.split(" ").includes(howPicked)));
  const out = $("howOut");
  if (!howPicked) out.replaceChildren();
  else if (howPicked.startsWith("c")) {
    const list = make("ol");
    for (const step of howSteps(howPicked, howLanes)) {
      const li = make("li");
      li.append(...[].concat(step));
      list.appendChild(li);
    }
    out.replaceChildren(list);
  } else out.replaceChildren(make("p", "", howJob(howPicked, howLanes)));
}

function howButtons(box, list) {
  box.replaceChildren(...list.map(({ key, label }) => {
    const b = make("button", "", label);
    b.type = "button";
    b.dataset.key = key;
    b.setAttribute("aria-pressed", "false");
    b.onclick = () => howChoose(key);
    return b;
  }));
}

// On top of Settings, which stays open with its unsaved changes, and these show them.
function howOpen() {
  const l = howLanes = howRead(watchRows);
  $("how").showModal();
  $("howNote").hidden = !l.example;
  howPicked = "";
  $("howOut").replaceChildren();
  howDraw(l);
  howButtons($("howOffice"), HOW_OFFICE.filter((j) => j.needs === "both" ? l.slide && l.loop : l[j.needs]));
  howButtons($("howSetup"), HOW_SETUP);
}

$("howOpen").onclick = howOpen;
$("howClose").onclick = () => $("how").close();
