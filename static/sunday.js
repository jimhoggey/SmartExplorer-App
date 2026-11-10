// The Sunday check on the start screen: while watching is on, has Smart Explorer done its
// job this week? One line per folder, a tick only for what sunday.py could see for itself.
// It follows showWatch, every 5 seconds while watching is on.
const SUN_ICONS = {  // stroked 24×24 paths
  ok: "M5 12.5l4.2 4.2L19 7",
  warn: "M12 4l9 16H3zM12 10v4.5M12 17.5v.01",
  bad: "M7 7l10 10M17 7L7 17",
  work: "M12 4a8 8 0 1 0 8 8M12 8v4l3 2",
  unknown: "M9.2 9a3 3 0 1 1 4.3 2.7c-.9.5-1.5 1.2-1.5 2.3M12 17.5v.01",
};

function sunIcon(state) {
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg"), path = document.createElementNS(ns, "path");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  path.setAttribute("d", SUN_ICONS[state] || SUN_ICONS.unknown);
  svg.appendChild(path);
  return svg;
}

$("sunMore").onclick = () => {
  const open = $("sunday").classList.toggle("open");
  $("sunMore").textContent = open ? "Hide details" : "Details";
};

function showSunday(w) {
  const s = w.sunday || { state: "off" }, on = s.state !== "off";
  $("autoIntro").hidden = on;
  $("sunday").hidden = !on;
  $("sunday").closest(".way").classList.toggle("watching", on);
  if (!on) return;
  $("sunday").dataset.state = s.state;
  $("sunBadge").replaceChildren(sunIcon(s.state));
  $("sunHead").textContent = s.headline;
  $("sunSince").textContent = s.since;
  // One line each, read at a glance: a coloured icon, the folder, a word or two. The sentences
  // (what it's doing now, what's in it) only show under Details.
  $("sunRows").replaceChildren(...s.rows.map((r) => {
    const li = make("li", "sun-" + r.state), dot = make("span", "sun-dot");
    dot.append(sunIcon(r.state));
    li.append(dot, make("b", "", r.name), make("span", "sun-pill", r.short || r.text),
      make("small", "sun-more", [r.text, r.detail].filter(Boolean).join(" · ")));
    return li;
  }));
  const latest = $("sunLatest");
  latest.replaceChildren();
  if (s.latest.length) {
    latest.append(make("div", "sun-label", "Latest"));
    for (const e of s.latest) {
      const row = make("div");
      row.append(make("span", "sun-when", e.when), `${e.folder}: `, make("code", "", e.from), " named ", make("b", "", e.to));
      latest.append(row);
    }
  }
}
