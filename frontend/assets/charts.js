// Small dependency-free SVG charts: line (with optional min/max band), time columns and horizontal ranking bars.
// Specs: 2px lines, columns/bars <= 24px with a 4px rounded data end, hairline grid, crosshair + tooltip,
// keyboard support and a table view twin rendered by the caller.

const SVG_NS = "http://www.w3.org/2000/svg";
const MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
const HOUR = 3_600_000;
const DAY = 24 * HOUR;

function svg(tag, attributes = {}, parent = null) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (value !== undefined && value !== null) node.setAttribute(key, String(value));
  }
  if (parent) parent.appendChild(node);
  return node;
}

function html(tag, className, parent = null, text = null) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== null) node.textContent = text;
  if (parent) parent.appendChild(node);
  return node;
}

const finite = (value) => typeof value === "number" && Number.isFinite(value);

export function niceScale(minValue, maxValue, { ticks = 5, minSpan = 0, zero = false } = {}) {
  let low = zero ? Math.min(0, minValue) : minValue;
  let high = zero ? Math.max(0, maxValue) : maxValue;
  if (!finite(low) || !finite(high)) {
    low = 0;
    high = 1;
  }
  if (high - low < minSpan) {
    const middle = (high + low) / 2;
    low = zero && low >= 0 ? 0 : middle - minSpan / 2;
    high = low + Math.max(minSpan, high - low);
  }
  if (high === low) high = low + 1;
  const rough = (high - low) / Math.max(ticks - 1, 1);
  const magnitude = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 2.5, 5, 10].map((factor) => factor * magnitude).find((candidate) => candidate >= rough) || 10 * magnitude;
  const niceLow = Math.floor(low / step) * step;
  const niceHigh = Math.ceil(high / step) * step;
  const values = [];
  for (let value = niceLow; value <= niceHigh + step / 2; value += step) values.push(Number(value.toFixed(10)));
  return { min: niceLow, max: niceHigh, ticks: values };
}

const TIME_INTERVALS = [
  { ms: HOUR, kind: "hour" },
  { ms: 3 * HOUR, kind: "hour" },
  { ms: 6 * HOUR, kind: "hour" },
  { ms: 12 * HOUR, kind: "hour" },
  { ms: DAY, kind: "day" },
  { ms: 2 * DAY, kind: "day" },
  { ms: 7 * DAY, kind: "day" },
  { ms: 14 * DAY, kind: "day" },
  { months: 1, kind: "month" },
  { months: 3, kind: "month" },
  { months: 6, kind: "month" },
  { months: 12, kind: "year" },
];

// Ticks aligned to local boundaries for a fixed UTC offset (Brazilian capitals have no DST).
export function timeTicks(minMs, maxMs, width, offsetSeconds = 0) {
  const maxTicks = Math.max(2, Math.floor(width / 84));
  const shift = offsetSeconds * 1000;
  const span = Math.max(maxMs - minMs, 1);
  const interval =
    TIME_INTERVALS.find((candidate) => (candidate.ms ? span / candidate.ms : span / (candidate.months * 30.44 * DAY)) <= maxTicks) ||
    TIME_INTERVALS[TIME_INTERVALS.length - 1];
  const ticks = [];
  if (interval.ms) {
    for (let local = Math.ceil((minMs + shift) / interval.ms) * interval.ms; local - shift <= maxMs; local += interval.ms) {
      const date = new Date(local);
      const hour = date.getUTCHours();
      const dayLabel = `${String(date.getUTCDate()).padStart(2, "0")}/${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
      ticks.push({ ms: local - shift, label: interval.kind === "hour" && hour !== 0 ? `${hour}h` : dayLabel });
    }
  } else {
    const start = new Date(minMs + shift);
    let year = start.getUTCFullYear();
    let month = start.getUTCMonth();
    if (start.getUTCDate() !== 1 || start.getUTCHours() !== 0) month += 1;
    month = Math.ceil(month / interval.months) * interval.months;
    for (;;) {
      const local = Date.UTC(year + Math.floor(month / 12), month % 12, 1);
      if (local - shift > maxMs) break;
      const date = new Date(local);
      ticks.push({
        ms: local - shift,
        label: interval.kind === "year" ? String(date.getUTCFullYear()) : `${MONTHS[date.getUTCMonth()]} ${String(date.getUTCFullYear()).slice(2)}`,
      });
      month += interval.months;
    }
  }
  return ticks;
}

function medianStep(xs) {
  if (xs.length < 2) return HOUR;
  const steps = xs
    .slice(1)
    .map((x, index) => x - xs[index])
    .sort((a, b) => a - b);
  return steps[Math.floor(steps.length / 2)] || HOUR;
}

function observeWidth(container, render) {
  let lastWidth = 0;
  const run = () => {
    const width = Math.floor(container.clientWidth);
    if (width > 0 && width !== lastWidth) {
      lastWidth = width;
      render(width);
    }
  };
  const observer = new ResizeObserver(() => window.requestAnimationFrame(run));
  observer.observe(container);
  run();
  return observer;
}

function createTooltip(container) {
  const tooltip = html("div", "chart-tooltip", container);
  tooltip.hidden = true;
  return tooltip;
}

function fillTooltip(tooltip, title, rows) {
  tooltip.replaceChildren();
  html("div", "chart-tooltip-title", tooltip, title);
  for (const row of rows) {
    const line = html("div", "chart-tooltip-row", tooltip);
    if (row.color) {
      const key = html("span", row.kind === "box" ? "key-box" : "key-line", line);
      key.style.background = row.color;
    }
    html("strong", null, line, row.value);
    html("span", "chart-tooltip-label", line, row.label);
  }
}

function placeTooltip(tooltip, container, x, y) {
  tooltip.hidden = false;
  const width = tooltip.offsetWidth;
  const containerWidth = container.clientWidth;
  const left = x + 14 + width > containerWidth ? Math.max(0, x - 14 - width) : x + 14;
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${Math.max(0, y - tooltip.offsetHeight / 2)}px`;
}

export function legend(items) {
  const node = html("div", "chart-legend");
  for (const item of items) {
    const entry = html("span", "chart-legend-item", node);
    const key = html("span", item.kind === "box" ? "key-box" : "key-line", entry);
    key.style.background = item.color;
    html("span", null, entry, item.label);
  }
  return node;
}

function drawYAxis(group, scale, y, width, left, axisFormat) {
  for (const tick of scale.ticks) {
    const position = y(tick);
    svg("line", { x1: left, x2: width, y1: position, y2: position, class: "grid" }, group);
    svg("text", { x: left - 8, y: position, class: "tick", "text-anchor": "end", "dominant-baseline": "middle" }, group).textContent = axisFormat(tick);
  }
}

function drawXAxis(group, ticks, x, bottom, left, right) {
  svg("line", { x1: left, x2: right, y1: bottom, y2: bottom, class: "axis" }, group);
  let lastEnd = -Infinity;
  for (const tick of ticks) {
    const position = x(tick.ms);
    if (position < left - 1 || position > right + 1) continue;
    const label = svg("text", { x: position, y: bottom + 18, class: "tick", "text-anchor": "middle" }, group);
    label.textContent = tick.label;
    const halfWidth = tick.label.length * 3.4;
    if (position - halfWidth < lastEnd + 6) label.remove();
    else lastEnd = position + halfWidth;
    svg("line", { x1: position, x2: position, y1: bottom, y2: bottom + 4, class: "axis" }, group);
  }
}

function linePath(points, x, y, maxGap) {
  let path = "";
  let previous = null;
  for (const point of points) {
    if (!finite(point.y)) {
      previous = null;
      continue;
    }
    const command = previous && point.x - previous.x <= maxGap ? "L" : "M";
    path += `${command}${x(point.x).toFixed(1)},${y(point.y).toFixed(1)}`;
    previous = point;
  }
  return path;
}

function bandPath(band, x, y, maxGap) {
  const segments = [];
  let current = [];
  for (const point of band) {
    if (!finite(point.lo) || !finite(point.hi)) {
      if (current.length) segments.push(current);
      current = [];
      continue;
    }
    if (current.length && point.x - current[current.length - 1].x > maxGap) {
      segments.push(current);
      current = [];
    }
    current.push(point);
  }
  if (current.length) segments.push(current);
  return segments
    .filter((segment) => segment.length > 1)
    .map((segment) => {
      const upper = segment.map((point, index) => `${index ? "L" : "M"}${x(point.x).toFixed(1)},${y(point.hi).toFixed(1)}`).join("");
      const lower = segment
        .slice()
        .reverse()
        .map((point) => `L${x(point.x).toFixed(1)},${y(point.lo).toFixed(1)}`)
        .join("");
      return `${upper}${lower}Z`;
    })
    .join("");
}

function nearestIndex(xs, target) {
  let low = 0;
  let high = xs.length - 1;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (xs[middle] < target) low = middle + 1;
    else high = middle;
  }
  if (low > 0 && Math.abs(xs[low - 1] - target) <= Math.abs(xs[low] - target)) return low - 1;
  return low;
}

function emptyState(container, message) {
  container.replaceChildren();
  html("p", "chart-empty", container, message);
}

export function lineChart(container, options) {
  const {
    series,
    height = 220,
    format = (value) => String(value),
    axisFormat = format,
    offsetSeconds = 0,
    tooltipTitle = (ms) => new Date(ms).toISOString(),
    ariaLabel = "Gráfico de linhas",
    minSpan = 0,
    zero = false,
    endLabels = true,
  } = options;
  const hasData = series.some((item) => item.values.some((point) => finite(point.y)));
  if (!hasData) {
    emptyState(container, options.emptyMessage || "Sem dados para o período.");
    return null;
  }
  return observeWidth(container, (width) => {
    container.replaceChildren();
    container.classList.add("chart");
    if (series.length > 1) container.appendChild(legend(series.map((item) => ({ label: item.name, color: item.color }))));
    const xs = [...new Set(series.flatMap((item) => item.values.map((point) => point.x)))].sort((a, b) => a - b);
    const values = series.flatMap((item) => [
      ...item.values.map((point) => point.y),
      ...(item.band || []).flatMap((point) => [point.lo, point.hi]),
    ]);
    const finiteValues = values.filter(finite);
    const scale = niceScale(Math.min(...finiteValues), Math.max(...finiteValues), { minSpan, zero });
    const longestLabel = Math.max(...scale.ticks.map((tick) => axisFormat(tick).length));
    const left = 12 + longestLabel * 7;
    const showEndLabels = endLabels && series.length <= 4 && width >= 360;
    const right = width - (showEndLabels ? (series.length > 1 ? 84 : 60) : 12);
    const top = 10;
    const bottom = height - 28;
    const x = (ms) => left + ((ms - xs[0]) / Math.max(xs[xs.length - 1] - xs[0], 1)) * (right - left);
    const y = (value) => bottom - ((value - scale.min) / (scale.max - scale.min)) * (bottom - top);
    const maxGap = medianStep(xs) * 2.5;

    const root = svg("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": ariaLabel, tabindex: 0 });
    container.appendChild(root);
    const axes = svg("g", {}, root);
    drawYAxis(axes, scale, y, right, left, axisFormat);
    drawXAxis(axes, timeTicks(xs[0], xs[xs.length - 1], right - left, offsetSeconds), x, bottom, left, right);

    for (const item of series) {
      if (item.band) {
        const band = svg("path", { d: bandPath(item.band, x, y, maxGap), class: "band" }, root);
        band.style.fill = item.color;
      }
    }
    const endPoints = [];
    for (const item of series) {
      const path = svg("path", { d: linePath(item.values, x, y, maxGap), class: "line" }, root);
      path.style.stroke = item.color;
      const last = [...item.values].reverse().find((point) => finite(point.y));
      if (last) endPoints.push({ item, point: last });
    }
    for (const { item, point } of endPoints) {
      const dot = svg("circle", { cx: x(point.x), cy: y(point.y), r: 4, class: "dot" }, root);
      dot.style.fill = item.color;
    }
    if (showEndLabels) {
      const positions = endPoints.map(({ point }) => y(point.y)).sort((a, b) => a - b);
      const collide = positions.some((position, index) => index > 0 && position - positions[index - 1] < 14);
      if (!collide) {
        for (const { item, point } of endPoints) {
          const label = svg("text", { x: x(point.x) + 8, y: y(point.y), class: "end-label", "dominant-baseline": "middle" }, root);
          label.textContent = series.length > 1 ? `${item.short || item.name} ${format(point.y)}` : format(point.y);
          label.setAttribute("aria-hidden", "true");
        }
      }
    }

    const crosshair = svg("line", { y1: top, y2: bottom, class: "crosshair", visibility: "hidden" }, root);
    const markers = series.map((item) => {
      const marker = svg("circle", { r: 4, class: "dot", visibility: "hidden" }, root);
      marker.style.fill = item.color;
      return marker;
    });
    const tooltip = createTooltip(container);
    const lookup = series.map((item) => new Map(item.values.map((point) => [point.x, point])));
    let active = -1;

    const show = (index) => {
      active = Math.max(0, Math.min(xs.length - 1, index));
      const ms = xs[active];
      const px = x(ms);
      crosshair.setAttribute("x1", px);
      crosshair.setAttribute("x2", px);
      crosshair.setAttribute("visibility", "visible");
      const rows = [];
      let anchorY = (top + bottom) / 2;
      series.forEach((item, seriesIndex) => {
        const point = lookup[seriesIndex].get(ms);
        const marker = markers[seriesIndex];
        if (point && finite(point.y)) {
          marker.setAttribute("cx", px);
          marker.setAttribute("cy", y(point.y));
          marker.setAttribute("visibility", "visible");
          anchorY = y(point.y);
          rows.push({ color: item.color, value: format(point.y), label: point.extra ? `${item.name} · ${point.extra}` : item.name });
        } else {
          marker.setAttribute("visibility", "hidden");
          rows.push({ color: item.color, value: "–", label: item.name });
        }
      });
      fillTooltip(tooltip, tooltipTitle(ms), rows);
      placeTooltip(tooltip, container, px, anchorY + (series.length > 1 ? 24 : 0));
    };
    const hide = () => {
      crosshair.setAttribute("visibility", "hidden");
      for (const marker of markers) marker.setAttribute("visibility", "hidden");
      tooltip.hidden = true;
    };
    const hit = svg("rect", { x: left, y: top, width: Math.max(right - left, 1), height: bottom - top, class: "hit" }, root);
    hit.addEventListener("pointermove", (event) => {
      const box = root.getBoundingClientRect();
      const ms = xs[0] + ((event.clientX - box.left - left) / Math.max(right - left, 1)) * (xs[xs.length - 1] - xs[0]);
      show(nearestIndex(xs, ms));
    });
    hit.addEventListener("pointerleave", hide);
    root.addEventListener("focus", () => show(active < 0 ? xs.length - 1 : active));
    root.addEventListener("blur", hide);
    root.addEventListener("keydown", (event) => {
      const moves = { ArrowLeft: -1, ArrowRight: 1, Home: -Infinity, End: Infinity };
      if (event.key === "Escape") return hide();
      if (!(event.key in moves)) return;
      event.preventDefault();
      const move = moves[event.key];
      show(move === -Infinity ? 0 : move === Infinity ? xs.length - 1 : active + move);
    });
  });
}

function roundedColumn(x0, width, yTop, yBase, radius) {
  const r = Math.min(radius, width / 2, Math.abs(yBase - yTop));
  if (yTop >= yBase) return "";
  return `M${x0},${yBase}V${yTop + r}Q${x0},${yTop} ${x0 + r},${yTop}H${x0 + width - r}Q${x0 + width},${yTop} ${x0 + width},${yTop + r}V${yBase}Z`;
}

export function columnChart(container, options) {
  const {
    values,
    color,
    height = 170,
    format = (value) => String(value),
    axisFormat = format,
    offsetSeconds = 0,
    tooltipTitle = (ms) => new Date(ms).toISOString(),
    tooltipRows = (point) => [{ color: point.color || color, kind: "box", value: format(point.y), label: "" }],
    ariaLabel = "Gráfico de colunas",
    stepMs,
    align = "start",
    minMax = 1,
    tickCount = 4,
    legendItems = null,
  } = options;
  if (!values.some((point) => finite(point.y))) {
    emptyState(container, options.emptyMessage || "Sem dados para o período.");
    return null;
  }
  return observeWidth(container, (width) => {
    container.replaceChildren();
    container.classList.add("chart");
    if (legendItems) container.appendChild(legend(legendItems));
    const xs = values.map((point) => point.x);
    const step = stepMs || medianStep(xs);
    const shift = align === "start" ? step / 2 : align === "end" ? -step / 2 : 0;
    const scale = niceScale(0, Math.max(minMax, ...values.map((point) => point.y).filter(finite)), { ticks: tickCount, zero: true });
    const longestLabel = Math.max(...scale.ticks.map((tick) => axisFormat(tick).length));
    const left = 12 + longestLabel * 7;
    const right = width - 12;
    const top = 10;
    const bottom = height - 28;
    const domainMin = xs[0] + shift - step / 2;
    const domainMax = xs[xs.length - 1] + shift + step / 2;
    const x = (ms) => left + ((ms - domainMin) / Math.max(domainMax - domainMin, 1)) * (right - left);
    const y = (value) => bottom - ((value - scale.min) / (scale.max - scale.min)) * (bottom - top);
    const slot = ((right - left) * step) / Math.max(domainMax - domainMin, 1);
    const barWidth = Math.max(1.5, Math.min(24, slot - 2));

    const root = svg("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": ariaLabel, tabindex: 0 });
    container.appendChild(root);
    const axes = svg("g", {}, root);
    drawYAxis(axes, scale, y, right, left, axisFormat);
    drawXAxis(axes, timeTicks(domainMin, domainMax, right - left, offsetSeconds), x, bottom, left, right);
    const bars = values.map((point) => {
      if (!finite(point.y) || point.y <= 0) return null;
      const center = x(point.x + shift);
      const bar = svg("path", { d: roundedColumn(center - barWidth / 2, barWidth, y(point.y), y(0), 4), class: "column" }, root);
      bar.style.fill = point.color || color;
      return bar;
    });
    const tooltip = createTooltip(container);
    let active = -1;
    const show = (index) => {
      active = Math.max(0, Math.min(values.length - 1, index));
      bars.forEach((bar, barIndex) => bar?.classList.toggle("dimmed", barIndex !== active));
      const point = values[active];
      fillTooltip(tooltip, tooltipTitle(point.x), tooltipRows(point));
      placeTooltip(tooltip, container, x(point.x + shift), finite(point.y) && point.y > 0 ? y(point.y) : bottom - 20);
    };
    const hide = () => {
      for (const bar of bars) bar?.classList.remove("dimmed");
      tooltip.hidden = true;
    };
    const hit = svg("rect", { x: left, y: top, width: Math.max(right - left, 1), height: bottom - top, class: "hit" }, root);
    hit.addEventListener("pointermove", (event) => {
      const box = root.getBoundingClientRect();
      const ms = domainMin + ((event.clientX - box.left - left) / Math.max(right - left, 1)) * (domainMax - domainMin) - shift;
      show(nearestIndex(xs, ms));
    });
    hit.addEventListener("pointerleave", hide);
    root.addEventListener("focus", () => show(active < 0 ? values.length - 1 : active));
    root.addEventListener("blur", hide);
    root.addEventListener("keydown", (event) => {
      if (event.key === "Escape") return hide();
      const moves = { ArrowLeft: -1, ArrowRight: 1 };
      if (!(event.key in moves)) return;
      event.preventDefault();
      show(active + moves[event.key]);
    });
  });
}

// Horizontal ranking bars. Every bar carries its value at the tip (bars -> value at the tip).
export function barChart(container, options) {
  const { items, color, format = (value) => String(value), ariaLabel = "Ranking", rowHeight = 28, onSelect = null } = options;
  const usable = items.filter((item) => finite(item.value));
  if (!usable.length) {
    emptyState(container, options.emptyMessage || "Sem dados.");
    return null;
  }
  return observeWidth(container, (width) => {
    container.replaceChildren();
    container.classList.add("chart");
    const labelWidth = Math.min(150, Math.max(84, Math.floor(width * 0.3)));
    const valueWidth = 64;
    const height = usable.length * rowHeight + 8;
    const minValue = Math.min(0, ...usable.map((item) => item.value));
    const maxValue = Math.max(0, ...usable.map((item) => item.value));
    const left = labelWidth;
    const right = width - valueWidth;
    const x = (value) => left + ((value - minValue) / Math.max(maxValue - minValue, 1e-9)) * (right - left);
    const root = svg("svg", { width, height, viewBox: `0 0 ${width} ${height}`, role: "list", "aria-label": ariaLabel });
    container.appendChild(root);
    const zero = x(0);
    svg("line", { x1: zero, x2: zero, y1: 0, y2: height, class: "axis" }, root);
    const thickness = Math.min(24, rowHeight - 12);
    usable.forEach((item, index) => {
      const top = 4 + index * rowHeight;
      const group = svg("g", { role: "listitem", tabindex: onSelect ? 0 : undefined, class: onSelect ? "bar-row interactive" : "bar-row" }, root);
      svg("rect", { x: 0, y: top, width, height: rowHeight, class: "row-hit" }, group);
      const label = svg("text", { x: left - 10, y: top + rowHeight / 2, class: "bar-label", "text-anchor": "end", "dominant-baseline": "middle" }, group);
      label.textContent = item.label;
      const start = Math.min(zero, x(item.value));
      const end = Math.max(zero, x(item.value));
      const barTop = top + (rowHeight - thickness) / 2;
      const length = Math.max(end - start, 1);
      const r = Math.min(4, length);
      const d =
        item.value >= 0
          ? `M${start},${barTop}H${start + length - r}Q${start + length},${barTop} ${start + length},${barTop + r}V${barTop + thickness - r}Q${start + length},${barTop + thickness} ${start + length - r},${barTop + thickness}H${start}Z`
          : `M${end},${barTop}H${end - length + r}Q${end - length},${barTop} ${end - length},${barTop + r}V${barTop + thickness - r}Q${end - length},${barTop + thickness} ${end - length + r},${barTop + thickness}H${end}Z`;
      const bar = svg("path", { d, class: "bar" }, group);
      bar.style.fill = item.color || color;
      const valueLabel = svg(
        "text",
        {
          x: item.value >= 0 ? end + 6 : start - 6,
          y: top + rowHeight / 2,
          class: "bar-value",
          "text-anchor": item.value >= 0 ? "start" : "end",
          "dominant-baseline": "middle",
        },
        group,
      );
      valueLabel.textContent = item.display ?? format(item.value);
      const title = svg("title", {}, group);
      title.textContent = `${item.fullLabel || item.label}: ${item.display ?? format(item.value)}`;
      if (onSelect) {
        group.addEventListener("click", () => onSelect(item));
        group.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelect(item);
          }
        });
      }
    });
  });
}

export function tableView({ caption, columns, rows, open = false }) {
  const details = html("details", "table-view");
  details.open = open;
  html("summary", null, details, "Ver dados em tabela");
  const scroll = html("div", "table-scroll", details);
  const table = html("table", null, scroll);
  if (caption) html("caption", null, table, caption);
  const headRow = html("tr", null, html("thead", null, table));
  for (const column of columns) {
    const cell = html("th", column.numeric ? "numeric" : null, headRow, column.label);
    cell.scope = "col";
  }
  const body = html("tbody", null, table);
  for (const row of rows) {
    const tr = html("tr", null, body);
    for (const column of columns) {
      html("td", column.numeric ? "numeric" : null, tr, column.value(row));
    }
  }
  return details;
}
