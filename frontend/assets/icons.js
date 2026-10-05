// Self-contained SVG icons for the OpenWeather condition codes (01d ... 50n), so the dashboard needs no
// external request and works fully offline.

const NS = "http://www.w3.org/2000/svg";

function node(tag, attributes, parent) {
  const element = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value));
  parent.appendChild(element);
  return element;
}

function sun(svg, cx, cy, r) {
  const group = node("g", { class: "wx-sun" }, svg);
  node("circle", { cx, cy, r }, group);
  for (let index = 0; index < 8; index += 1) {
    const angle = (Math.PI / 4) * index;
    node(
      "line",
      {
        x1: (cx + Math.cos(angle) * (r + 4)).toFixed(1),
        y1: (cy + Math.sin(angle) * (r + 4)).toFixed(1),
        x2: (cx + Math.cos(angle) * (r + 9)).toFixed(1),
        y2: (cy + Math.sin(angle) * (r + 9)).toFixed(1),
      },
      group,
    );
  }
}

function moon(svg, cx, cy, r) {
  node("path", { class: "wx-moon", d: `M${cx + r * 0.35} ${cy - r}a${r} ${r} 0 1 0 ${r * 0.65} ${r * 1.55}A${r * 0.8} ${r * 0.8} 0 0 1 ${cx + r * 0.35} ${cy - r}z` }, svg);
}

function cloud(svg, dx, dy, scale, className = "wx-cloud") {
  node(
    "path",
    {
      class: className,
      transform: `translate(${dx} ${dy}) scale(${scale})`,
      d: "M10 26h14a5 5 0 0 0 0-10 7 7 0 0 0-13.4 2.2A4 4 0 0 0 10 26z",
    },
    svg,
  );
}

function drops(svg, count) {
  const group = node("g", { class: "wx-rain" }, svg);
  for (let index = 0; index < count; index += 1) {
    const x = 24 + index * 8;
    node("line", { x1: x, y1: 50, x2: x - 3, y2: 58 }, group);
  }
}

function flakes(svg) {
  const group = node("g", { class: "wx-snow" }, svg);
  for (const x of [26, 36, 46]) {
    node("line", { x1: x, y1: 50, x2: x, y2: 58 }, group);
    node("line", { x1: x - 4, y1: 54, x2: x + 4, y2: 54 }, group);
  }
}

const DRAW = {
  "01": (svg, night) => (night ? moon(svg, 30, 32, 14) : sun(svg, 32, 32, 12)),
  "02": (svg, night) => {
    if (night) moon(svg, 24, 22, 11);
    else sun(svg, 24, 22, 9);
    cloud(svg, 12, 6, 1.6);
  },
  "03": (svg) => cloud(svg, 2, -6, 1.9),
  "04": (svg) => {
    cloud(svg, 14, -12, 1.4, "wx-cloud-dark");
    cloud(svg, 0, -4, 1.8);
  },
  "09": (svg) => {
    cloud(svg, 2, -14, 1.9, "wx-cloud-dark");
    drops(svg, 4);
  },
  10: (svg, night) => {
    if (night) moon(svg, 22, 18, 10);
    else sun(svg, 22, 18, 8);
    cloud(svg, 6, -10, 1.8);
    drops(svg, 3);
  },
  11: (svg) => {
    cloud(svg, 2, -14, 1.9, "wx-cloud-dark");
    node("path", { class: "wx-bolt", d: "M34 40l-8 12h7l-4 11 11-15h-7l5-8z" }, svg);
  },
  13: (svg) => {
    cloud(svg, 2, -14, 1.9);
    flakes(svg);
  },
  50: (svg) => {
    const group = node("g", { class: "wx-mist" }, svg);
    for (const [y, x1, x2] of [
      [24, 12, 52],
      [34, 8, 48],
      [44, 16, 56],
    ]) {
      node("line", { x1, y1: y, x2, y2: y }, group);
    }
  },
};

export function weatherIconSvg(code, description = "", className = "weather-icon") {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 64 64");
  svg.setAttribute("class", className);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", description || "Condição do tempo");
  const title = node("title", {}, svg);
  title.textContent = description || "";
  const match = /^(\d{2})([dn])$/.exec(code || "");
  const draw = match && DRAW[match[1]];
  if (draw) draw(svg, match[2] === "n");
  else node("circle", { class: "wx-unknown", cx: 32, cy: 32, r: 10 }, svg);
  return svg;
}
