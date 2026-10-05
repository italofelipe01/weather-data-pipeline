import { barChart, columnChart, legend, lineChart, tableView } from "./charts.js";
import {
  REGIONS,
  aggregateDaily,
  dateFromIso,
  filterByDays,
  forecastByDay,
  loadDaily,
  loadForecast,
  loadHourly,
  loadLatest,
  stats,
} from "./data.js";
import {
  POLLUTANTS,
  aqiLevel,
  capitalize,
  compass,
  fmtCompact,
  fmtDateTime,
  fmtDuration,
  fmtIsoDate,
  fmtMicrograms,
  fmtNumber,
  fmtPercent,
  fmtPressure,
  fmtRain,
  fmtRainRate,
  fmtRelative,
  fmtTemp,
  fmtTime,
  fmtVisibility,
  fmtWeekday,
  fmtWind,
  iconUrl,
  isNumber,
  toKmh,
} from "./format.js";

const app = document.getElementById("app");
const HOUR = 3_600_000;
const BRASILIA = "America/Sao_Paulo";
const STALE_MINUTES = 45;
const REFRESH_MS = 5 * 60_000;
const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];
const STATUS_COLORS = {
  good: "var(--status-good)",
  warning: "var(--status-warning)",
  serious: "var(--status-serious)",
  critical: "var(--status-critical)",
};

let observers = [];
let refreshTimer = null;
let renderToken = 0;

// ---------------------------------------------------------------------------
// DOM helpers (no innerHTML: every label coming from data is inserted as text)

function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else node.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// Charts measure their container, so they are drawn only after the view is attached to the document.
const pendingCharts = new WeakMap();

function deferChart(container, chart, options) {
  container.dataset.chart = "";
  pendingCharts.set(container, { chart, options });
  return container;
}

function mountCharts(root) {
  for (const container of root.querySelectorAll("[data-chart]")) {
    const pending = pendingCharts.get(container);
    if (!pending) continue;
    pendingCharts.delete(container);
    const observer = pending.chart(container, pending.options);
    if (observer) observers.push(observer);
  }
}

function chartBlock(title, chart, options, extra = null) {
  const block = h("div", { class: "chart-block" });
  if (title) block.appendChild(h("h3", { class: "chart-title", text: title }));
  block.appendChild(deferChart(h("div"), chart, options));
  if (extra) block.appendChild(extra);
  return block;
}

function card(title, subtitle, ...content) {
  return h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("div", {}, h("h2", { text: title }), subtitle ? h("p", { text: subtitle }) : null)),
    ...content,
  );
}

function cardWithTools(title, subtitle, tools, ...content) {
  return h(
    "section",
    { class: "card" },
    h("div", { class: "card-head" }, h("div", {}, h("h2", { text: title }), subtitle ? h("p", { text: subtitle }) : null), tools),
    ...content,
  );
}

function tile(label, value, detail = null, href = null) {
  return h(href ? "a" : "div", { class: "tile", href }, h("div", { class: "tile-label", text: label }), h("div", { class: "tile-value" }, value), detail ? h("div", { class: "tile-detail" }, detail) : null);
}

function weatherIcon(icon, description, size = "") {
  const url = iconUrl(icon);
  const fallback = () => h("span", { class: "icon-fallback", "aria-hidden": "true", text: "?" });
  if (!url) return fallback();
  const image = h("img", { class: `weather-icon ${size}`.trim(), src: url, alt: description || "", width: 64, height: 64, loading: "lazy", decoding: "async" });
  image.addEventListener("error", () => image.replaceWith(fallback()), { once: true });
  return image;
}

function aqiBadge(aqi, withIndex = true) {
  const level = aqiLevel(aqi);
  if (!level) return h("span", { class: "badge", text: "Sem dados de ar" });
  return h(
    "span",
    { class: `badge status-${level.status}`, title: `Índice de qualidade do ar OpenWeather: ${aqi} de 5` },
    h("span", { class: "glyph", "aria-hidden": "true", text: level.icon }),
    h("span", { class: "status-text", text: withIndex ? `${level.label} (${aqi}/5)` : level.label }),
  );
}

function windArrow(degrees) {
  if (!isNumber(degrees)) return null;
  const ns = "http://www.w3.org/2000/svg";
  const arrow = document.createElementNS(ns, "svg");
  arrow.setAttribute("viewBox", "0 0 16 16");
  arrow.setAttribute("class", "wind-arrow");
  arrow.setAttribute("aria-hidden", "true");
  const path = document.createElementNS(ns, "path");
  // Meteorological direction is where the wind comes from; the arrow points where it goes.
  path.setAttribute("d", "M8 15V3M8 3L4 7M8 3l4 4");
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("transform", `rotate(${(degrees + 180) % 360} 8 8)`);
  arrow.appendChild(path);
  return arrow;
}

function chips(options, selected, onSelect, label) {
  return h(
    "div",
    { class: "chips", role: "group", "aria-label": label },
    options.map((option) =>
      h("button", { type: "button", class: "chip", "aria-pressed": String(option.value === selected), text: option.label, onClick: () => onSelect(option.value) }),
    ),
  );
}

function select(options, selected, onChange, label) {
  const node = h(
    "select",
    { "aria-label": label },
    options.map((option) =>
      option.group
        ? h("optgroup", { label: option.group }, option.items.map((item) => h("option", { value: item.value, selected: item.value === selected, text: item.label })))
        : h("option", { value: option.value, selected: option.value === selected, text: option.label }),
    ),
  );
  node.addEventListener("change", () => onChange(node.value));
  return node;
}

function setParams(route, changes) {
  const params = new URLSearchParams(route.params);
  for (const [key, value] of Object.entries(changes)) {
    if (value === null || value === undefined || value === "") params.delete(key);
    else params.set(key, value);
  }
  const query = params.toString();
  location.hash = `${route.path}${query ? `?${query}` : ""}`;
}

function capitalOptions(capitals) {
  return REGIONS.map((region) => ({
    group: region,
    items: capitals.filter((capital) => capital.region === region).map((capital) => ({ value: capital.state, label: `${capital.name} (${capital.state})` })),
  }));
}

function staleNotice(latest) {
  const observed = latest?.latest_observation_at ? new Date(latest.latest_observation_at) : null;
  if (!observed) return null;
  const minutes = (Date.now() - observed) / 60000;
  if (minutes < STALE_MINUTES) return null;
  return h(
    "div",
    { class: "notice", role: "status" },
    h("strong", { text: "Dados desatualizados. " }),
    `A observação mais recente é de ${fmtDateTime(observed, BRASILIA)} (${fmtRelative(observed)}). Confira se os agendamentos (EnableSchedules=true) estão ativos.`,
  );
}

function emptyView(message, title = "Ainda não há dados publicados") {
  return h(
    "section",
    { class: "card empty" },
    h("h1", { text: title }),
    h("p", { class: "subtle", text: message || "Assim que a coleta rodar, a Publisher grava data/latest.json e este painel passa a mostrar as 27 capitais." }),
    h(
      "p",
      { class: "subtle" },
      "Para testar localmente sem AWS: ",
      h("code", { text: "python scripts/sample_data.py" }),
      " e depois ",
      h("code", { text: "python -m http.server 8000 --directory frontend" }),
      ".",
    ),
  );
}

const hourTitle = (timeZone) => (ms) => fmtDateTime(new Date(ms), timeZone);
const axisNumber = (value) => fmtNumber(value, Number.isInteger(value) ? 0 : 1);

function simpleTable(columns, rows, caption = null) {
  return h(
    "div",
    { class: "table-scroll" },
    h(
      "table",
      {},
      caption ? h("caption", { text: caption }) : null,
      h("thead", {}, h("tr", {}, columns.map((column) => h("th", { scope: "col", class: column.numeric ? "numeric" : null, text: column.label })))),
      h("tbody", {}, rows.map((row) => h("tr", {}, columns.map((column) => h("td", { class: column.numeric ? "numeric" : null }, column.value(row)))))),
    ),
  );
}

// A precipitation chart full of zero-height columns says less than one sentence.
function rainBlock(title, values, options, emptyText) {
  if (!values.some((point) => isNumber(point.y) && point.y > 0)) {
    return h("div", { class: "chart-block" }, h("h3", { class: "chart-title", text: title }), h("p", { class: "muted", text: emptyText }));
  }
  return chartBlock(title, columnChart, { ...options, values });
}
const dayTitle = (ms) => fmtIsoDate(new Date(ms).toISOString().slice(0, 10), { weekday: "short", day: "2-digit", month: "short", year: "numeric" });

// ---------------------------------------------------------------------------
// Overview

const METRICS = {
  temperature: { label: "Temperatura", get: (c) => c.current?.temperature, format: (v) => fmtTemp(v, 1), color: "var(--temp)" },
  feels_like: { label: "Sensação térmica", get: (c) => c.current?.feels_like, format: (v) => fmtTemp(v, 1), color: "var(--temp)" },
  humidity: { label: "Umidade relativa", get: (c) => c.current?.humidity, format: fmtPercent, color: "var(--humidity)" },
  wind: { label: "Vento", get: (c) => toKmh(c.current?.wind_speed), format: (v) => `${fmtNumber(v)} km/h`, color: "var(--wind)" },
  clouds: { label: "Nebulosidade", get: (c) => c.current?.clouds, format: fmtPercent, color: "var(--series-1)" },
  pm2_5: { label: "Partículas finas (PM2,5)", get: (c) => c.air?.pm2_5, format: fmtMicrograms, color: "var(--series-1)" },
};

function extreme(capitals, getter, direction) {
  return capitals
    .filter((capital) => isNumber(getter(capital)))
    .sort((a, b) => (direction === "max" ? getter(b) - getter(a) : getter(a) - getter(b)))[0];
}

function capitalCard(capital) {
  const current = capital.current;
  return h(
    "a",
    { class: "capital-card", href: `#/capital/${capital.state}` },
    current ? weatherIcon(current.weather_icon, current.weather_description) : h("span", { class: "icon-fallback", text: "–" }),
    h("div", {}, h("span", { class: "name", text: capital.name }), h("span", { class: "uf", text: capital.state })),
    h("div", { class: "temp", text: current ? fmtTemp(current.temperature) : "–" }),
    h(
      "div",
      { class: "meta" },
      current ? `${capitalize(current.weather_description)} · ${fmtPercent(current.humidity)} · ${fmtWind(current.wind_speed)}` : "Sem observação recente",
      capital.air?.aqi ? h("div", {}, aqiBadge(capital.air.aqi, false)) : null,
    ),
  );
}

async function overviewView(route) {
  const latest = await loadLatest();
  if (!latest) return [emptyView()];
  const region = route.params.get("regiao") || "Todas";
  const metricKey = METRICS[route.params.get("metrica")] ? route.params.get("metrica") : "temperature";
  const metric = METRICS[metricKey];
  const all = latest.capitals;
  const capitals = region === "Todas" ? all : all.filter((capital) => capital.region === region);
  const withData = capitals.filter((capital) => capital.current);
  const observed = latest.latest_observation_at;

  const hottest = extreme(withData, (c) => c.current.temperature, "max");
  const coldest = extreme(withData, (c) => c.current.temperature, "min");
  const driest = extreme(withData, (c) => c.current.humidity, "min");
  const worstAir = capitals.filter((c) => c.air?.aqi).sort((a, b) => b.air.aqi - a.air.aqi || (b.air.pm2_5 || 0) - (a.air.pm2_5 || 0))[0];
  const raining = withData.filter((c) => (c.current.rain_1h || 0) > 0);

  const ranking = capitals
    .map((capital) => ({ key: capital.state, label: capital.name, fullLabel: `${capital.name} (${capital.state})`, value: metric.get(capital) }))
    .filter((item) => isNumber(item.value))
    .sort((a, b) => b.value - a.value);

  const filters = h(
    "div",
    { class: "filters" },
    chips(
      ["Todas", ...REGIONS].map((value) => ({ value, label: value })),
      region,
      (value) => setParams(route, { regiao: value === "Todas" ? null : value }),
      "Filtrar por região",
    ),
    h(
      "label",
      { class: "inline" },
      "Ranking por",
      select(
        Object.entries(METRICS).map(([value, item]) => ({ value, label: item.label })),
        metricKey,
        (value) => setParams(route, { metrica: value === "temperature" ? null : value }),
        "Métrica do ranking",
      ),
    ),
  );

  const kpis = h(
    "div",
    { class: "tiles" },
    tile("Mais quente", hottest ? fmtTemp(hottest.current.temperature, 1) : "–", hottest ? `${hottest.name} (${hottest.state})` : null, hottest ? `#/capital/${hottest.state}` : null),
    tile("Mais fria", coldest ? fmtTemp(coldest.current.temperature, 1) : "–", coldest ? `${coldest.name} (${coldest.state})` : null, coldest ? `#/capital/${coldest.state}` : null),
    tile("Menor umidade", driest ? fmtPercent(driest.current.humidity) : "–", driest ? `${driest.name} (${driest.state})` : null, driest ? `#/capital/${driest.state}` : null),
    tile(
      "Pior qualidade do ar",
      worstAir ? aqiBadge(worstAir.air.aqi) : "–",
      worstAir ? `${worstAir.name} · PM2,5 ${fmtMicrograms(worstAir.air.pm2_5)}` : null,
      worstAir ? `#/capital/${worstAir.state}` : null,
    ),
    tile("Chovendo agora", `${raining.length} de ${withData.length}`, raining.length ? raining.map((c) => c.state).join(", ") : "Nenhuma capital com chuva"),
  );

  const rankingContainer = deferChart(h("div"), barChart, {
    items: ranking,
    color: metric.color,
    format: metric.format,
    ariaLabel: `${metric.label} por capital`,
    onSelect: (item) => {
      location.hash = `#/capital/${item.key}`;
    },
  });
  const table = tableView({
    caption: "Observação mais recente por capital",
    columns: [
      { label: "Capital", value: (c) => `${c.name} (${c.state})` },
      { label: "Temp.", numeric: true, value: (c) => fmtTemp(c.current?.temperature, 1) },
      { label: "Sensação", numeric: true, value: (c) => fmtTemp(c.current?.feels_like, 1) },
      { label: "Umidade", numeric: true, value: (c) => fmtPercent(c.current?.humidity) },
      { label: "Vento", numeric: true, value: (c) => fmtWind(c.current?.wind_speed) },
      { label: "Pressão", numeric: true, value: (c) => fmtPressure(c.current?.pressure) },
      { label: "Nuvens", numeric: true, value: (c) => fmtPercent(c.current?.clouds) },
      { label: "Chuva", numeric: true, value: (c) => fmtRainRate(c.current?.rain_1h) },
      { label: "Qualidade do ar", value: (c) => (aqiLevel(c.air?.aqi) ? `${aqiLevel(c.air.aqi).label} (${c.air.aqi})` : "–") },
      { label: "Observado", value: (c) => fmtTime(c.current?.observed_at, c.timezone) },
    ],
    rows: capitals,
  });

  const groups = (region === "Todas" ? REGIONS : [region]).map((name) =>
    h("div", {}, h("h3", { text: name }), h("div", { class: "capital-grid" }, all.filter((c) => c.region === name).map(capitalCard))),
  );
  const regionRows = REGIONS.map((name) => {
    const members = all.filter((c) => c.region === name && c.current);
    const air = all.filter((c) => c.region === name && c.air?.aqi);
    const worst = air.sort((a, b) => b.air.aqi - a.air.aqi)[0];
    return {
      name,
      temperature: stats.mean(members.map((c) => c.current.temperature)),
      humidity: stats.mean(members.map((c) => c.current.humidity)),
      raining: members.filter((c) => (c.current.rain_1h || 0) > 0).length,
      total: members.length,
      worst,
    };
  });
  const regionTable = simpleTable(
    [
      { label: "Região", value: (row) => row.name },
      { label: "Temp. média", numeric: true, value: (row) => fmtTemp(row.temperature, 1) },
      { label: "Umidade", numeric: true, value: (row) => fmtPercent(row.humidity) },
      { label: "Com chuva", numeric: true, value: (row) => `${row.raining} de ${row.total}` },
      { label: "Pior ar", value: (row) => (row.worst ? aqiBadge(row.worst.air.aqi, false) : "–") },
    ],
    regionRows,
  );

  return [
    h(
      "div",
      { class: "page-head" },
      h(
        "div",
        {},
        h("h1", { text: "Clima agora nas capitais" }),
        h("p", {
          class: "subtle",
          text: observed ? `Observações até ${fmtDateTime(observed, BRASILIA)} (Brasília) · publicado ${fmtRelative(latest.generated_at)}` : "Sem observações recentes",
        }),
      ),
    ),
    staleNotice(latest),
    filters,
    kpis,
    h(
      "div",
      { class: "stack" },
      h(
        "div",
        { class: "grid-2" },
        card(`Ranking: ${metric.label}`, `${ranking.length} capitais · clique em uma barra para ver detalhes`, rankingContainer, table),
        h(
          "div",
          { class: "stack" },
          card("Resumo por região", "Média das observações mais recentes", regionTable),
          card(
            "Fontes desta página",
            null,
            h(
              "p",
              { class: "subtle", text: "Current Weather API a cada 3 minutos e Air Pollution API a cada hora, para as 27 capitais. Previsões e histórico ficam na página de cada capital." },
            ),
            h("p", {}, h("a", { href: "#/comparar", text: "Comparar capitais →" }), " · ", h("a", { href: "#/sobre", text: "Como os dados são coletados →" })),
          ),
        ),
      ),
      card("Capitais", region === "Todas" ? "Agrupadas por região" : region, h("div", { class: "capital-groups" }, groups)),
    ),
  ];
}

// ---------------------------------------------------------------------------
// Capital detail

function factsList(current, capital) {
  const timeZone = capital.timezone;
  const daylight = current.sunrise && current.sunset ? new Date(current.sunset) - new Date(current.sunrise) : null;
  const fact = (label, value, detail = null) => h("div", {}, h("dt", { text: label }), h("dd", {}, value, detail ? h("span", {}, ` ${detail}`) : null));
  return h(
    "dl",
    { class: "facts" },
    fact("Umidade", fmtPercent(current.humidity)),
    fact("Vento", h("span", {}, windArrow(current.wind_deg), fmtWind(current.wind_speed)), current.wind_deg != null ? `de ${compass(current.wind_deg)}` : null),
    fact("Rajadas", fmtWind(current.wind_gust)),
    fact("Pressão", fmtPressure(current.pressure), isNumber(current.grnd_level) ? `· solo ${fmtNumber(current.grnd_level)}` : null),
    fact("Visibilidade", fmtVisibility(current.visibility)),
    fact("Nebulosidade", fmtPercent(current.clouds)),
    fact("Chuva", fmtRainRate(current.rain_1h)),
    fact("Nascer do sol", fmtTime(current.sunrise, timeZone)),
    fact("Pôr do sol", fmtTime(current.sunset, timeZone), daylight ? `· ${fmtDuration(daylight)} de luz` : null),
  );
}

function airQualityCard(air, capital) {
  if (!air) return card("Qualidade do ar", "Air Pollution API", h("p", { class: "muted", text: "Sem medição de qualidade do ar recente." }));
  const rows = POLLUTANTS.filter((pollutant) => isNumber(air[pollutant.key])).map((pollutant) => {
    const value = air[pollutant.key];
    const ratio = pollutant.guideline ? value / pollutant.guideline : null;
    const meter = h("div", { class: `meter${ratio !== null && ratio > 1 ? " over" : ""}`, role: "presentation" });
    const fill = h("span");
    fill.style.width = `${Math.min(100, Math.round((ratio ?? 0) * 100))}%`;
    meter.appendChild(fill);
    return h(
      "li",
      { class: "meter-row", title: pollutant.name },
      h("span", { class: "meter-name", text: pollutant.label }),
      pollutant.guideline ? meter : h("span", { class: "muted", text: "sem referência" }),
      h(
        "span",
        { class: "meter-value" },
        fmtMicrograms(value),
        ratio !== null ? h("span", { class: "visually-hidden", text: ` (${Math.round(ratio * 100)}% da referência OMS)` }) : null,
      ),
    );
  });
  return card(
    "Qualidade do ar",
    `Medição de ${fmtTime(air.observed_at, capital.timezone)} · barras comparam com as diretrizes OMS 2021 (médias de 24 h; O₃ de 8 h)`,
    h("p", {}, aqiBadge(air.aqi)),
    h("ul", { class: "meter-list" }, rows),
  );
}

function forecastCard(forecast, capital) {
  const weather = forecast?.weather;
  if (!weather?.items?.length) return card("Previsão para 5 dias", "5 Day / 3 Hour Forecast API", h("p", { class: "muted", text: "Previsão ainda não publicada." }));
  const timeZone = capital.timezone;
  const days = forecastByDay(weather.items, timeZone);
  const strip = h(
    "div",
    { class: "day-strip" },
    days.map((day) =>
      h(
        "div",
        { class: "day" },
        h("div", { class: "day-name", text: fmtWeekday(day.date, timeZone) }),
        weatherIcon(day.icon, day.description, "small"),
        h("div", { class: "day-temps" }, fmtTemp(day.temp_max), h("span", { text: ` / ${fmtTemp(day.temp_min)}` })),
        h("div", { class: "day-rain", text: `${fmtPercent((day.pop_max || 0) * 100)} · ${fmtRain(day.rain_mm)}` }),
      ),
    ),
  );
  const items = weather.items.map((item) => ({ ...item, x: new Date(item.forecast_time).getTime() }));
  const offset = capital.utc_offset_seconds;
  return card(
    "Previsão para 5 dias",
    `Emitida às ${fmtTime(weather.issued_at, timeZone)} (hora local) · intervalos de 3 horas · probabilidade e volume de chuva por dia`,
    strip,
    chartBlock("Temperatura e sensação térmica (°C)", lineChart, {
      series: [
        { name: "Temperatura", short: "Temp.", color: "var(--temp)", values: items.map((item) => ({ x: item.x, y: item.temperature, extra: capitalize(item.weather_description) })) },
        { name: "Sensação térmica", short: "Sens.", color: "var(--feels)", values: items.map((item) => ({ x: item.x, y: item.feels_like })) },
      ],
      format: (v) => fmtTemp(v, 1),
      axisFormat: (v) => `${axisNumber(v)}°`,
      offsetSeconds: offset,
      tooltipTitle: hourTitle(timeZone),
      minSpan: 4,
      ariaLabel: "Previsão de temperatura e sensação térmica",
    }),
    rainBlock(
      "Chuva prevista (mm a cada 3 horas)",
      items.map((item) => ({ x: item.x, y: item.rain_3h, pop: item.pop })),
      {
      color: "var(--rain)",
      format: (v) => fmtRain(v),
      axisFormat: axisNumber,
      offsetSeconds: offset,
      stepMs: 3 * HOUR,
      align: "end",
      tooltipTitle: (ms) => `Até ${fmtDateTime(new Date(ms), timeZone)}`,
      tooltipRows: (point) => [
        { color: "var(--rain)", kind: "box", value: fmtRain(point.y), label: "chuva em 3 h" },
        { value: fmtPercent((point.pop || 0) * 100), label: "probabilidade" },
      ],
      ariaLabel: "Previsão de chuva",
      },
      `Sem chuva prevista para os próximos 5 dias (probabilidade máxima: ${fmtPercent(Math.max(0, ...items.map((item) => item.pop || 0)) * 100)}).`,
    ),
    tableView({
      columns: [
        { label: "Horário", value: (item) => fmtDateTime(item.forecast_time, timeZone) },
        { label: "Condição", value: (item) => capitalize(item.weather_description) },
        { label: "Temp.", numeric: true, value: (item) => fmtTemp(item.temperature, 1) },
        { label: "Sensação", numeric: true, value: (item) => fmtTemp(item.feels_like, 1) },
        { label: "Umidade", numeric: true, value: (item) => fmtPercent(item.humidity) },
        { label: "Vento", numeric: true, value: (item) => fmtWind(item.wind_speed) },
        { label: "Prob. chuva", numeric: true, value: (item) => fmtPercent((item.pop || 0) * 100) },
        { label: "Chuva 3 h", numeric: true, value: (item) => fmtRain(item.rain_3h) },
      ],
      rows: weather.items,
    }),
  );
}

function airForecastCard(forecast, capital) {
  const air = forecast?.air;
  if (!air?.items?.length) return null;
  const timeZone = capital.timezone;
  const now = Date.now() - HOUR;
  const items = air.items.filter((item) => new Date(item.forecast_time).getTime() >= now);
  const statuses = ["good", "warning", "serious", "critical"];
  const legendItems = statuses.map((status) => ({
    kind: "box",
    color: STATUS_COLORS[status],
    label: { good: "Boa/Razoável (1–2)", warning: "Moderada (3)", serious: "Ruim (4)", critical: "Muito ruim (5)" }[status],
  }));
  return card(
    "Previsão da qualidade do ar",
    `Air Pollution API · próximos 4 dias, hora a hora · emitida às ${fmtTime(air.issued_at, timeZone)}`,
    chartBlock("Índice de qualidade do ar (1 = boa, 5 = muito ruim)", columnChart, {
      values: items.map((item) => ({ x: new Date(item.forecast_time).getTime(), y: item.aqi, pm2_5: item.pm2_5, color: STATUS_COLORS[aqiLevel(item.aqi)?.status] })),
      format: (v) => fmtNumber(v),
      axisFormat: (v) => fmtNumber(v),
      offsetSeconds: capital.utc_offset_seconds,
      stepMs: HOUR,
      minMax: 5,
      tickCount: 6,
      height: 150,
      legendItems,
      tooltipTitle: hourTitle(timeZone),
      tooltipRows: (point) => [
        { color: point.color, kind: "box", value: `${aqiLevel(point.y)?.label ?? "–"} (${point.y})`, label: "índice" },
        { value: fmtMicrograms(point.pm2_5), label: "PM2,5" },
      ],
      ariaLabel: "Previsão do índice de qualidade do ar",
    }),
    tableView({
      columns: [
        { label: "Horário", value: (item) => fmtDateTime(item.forecast_time, timeZone) },
        { label: "Índice", value: (item) => `${aqiLevel(item.aqi)?.label ?? "–"} (${item.aqi})` },
        { label: "PM2,5", numeric: true, value: (item) => fmtMicrograms(item.pm2_5) },
        { label: "PM10", numeric: true, value: (item) => fmtMicrograms(item.pm10) },
        { label: "O₃", numeric: true, value: (item) => fmtMicrograms(item.o3) },
        { label: "NO₂", numeric: true, value: (item) => fmtMicrograms(item.no2) },
      ],
      rows: items,
    }),
  );
}

function recentCard(hourly, capital, route) {
  const rowsAll = hourly?.rows || [];
  if (!rowsAll.length) return card("Últimas horas", "Tabela horária curada", h("p", { class: "muted", text: "O histórico horário aparece depois da primeira curadoria (a cada hora, minuto 20)." }));
  const window = route.params.get("horas") || "72";
  const hours = Number(window);
  const lastTime = new Date(rowsAll[rowsAll.length - 1].observation_timestamp).getTime();
  const rows = rowsAll.filter((row) => new Date(row.observation_timestamp).getTime() > lastTime - hours * HOUR);
  const timeZone = capital.timezone;
  const offset = capital.utc_offset_seconds;
  const points = rows.map((row) => ({ ...row, x: new Date(row.observation_timestamp).getTime() }));
  const totalRain = stats.sum(rows.map((row) => row.rain_mm));
  return cardWithTools(
    "Últimas horas",
    `Médias horárias dos snapshots (cada observação conta uma vez) · chuva no período: ${fmtRain(totalRain)}`,
    chips(
      [
        { value: "24", label: "24 h" },
        { value: "72", label: "72 h" },
        { value: "168", label: "7 dias" },
      ],
      window,
      (value) => setParams(route, { horas: value === "72" ? null : value }),
      "Janela do histórico horário",
    ),
    chartBlock(
      "Temperatura (°C) · faixa = mínima e máxima da hora",
      lineChart,
      {
        series: [
          {
            name: "Temperatura média",
            color: "var(--temp)",
            values: points.map((row) => ({ x: row.x, y: row.temperature_avg, extra: capitalize(row.weather_description) })),
            band: points.map((row) => ({ x: row.x, lo: row.temperature_min, hi: row.temperature_max })),
          },
        ],
        format: (v) => fmtTemp(v, 1),
        axisFormat: (v) => `${fmtNumber(v)}°`,
        offsetSeconds: offset,
        tooltipTitle: hourTitle(timeZone),
        minSpan: 4,
        ariaLabel: "Temperatura horária",
      },
    ),
    chartBlock("Umidade relativa (%)", lineChart, {
      series: [{ name: "Umidade", color: "var(--humidity)", values: points.map((row) => ({ x: row.x, y: row.humidity_avg })) }],
      format: fmtPercent,
      axisFormat: (v) => fmtNumber(v),
      offsetSeconds: offset,
      tooltipTitle: hourTitle(timeZone),
      minSpan: 20,
      height: 170,
      ariaLabel: "Umidade horária",
    }),
    rainBlock(
      "Chuva por hora (mm)",
      points.map((row) => ({ x: row.x, y: row.rain_mm })),
      {
      color: "var(--rain)",
      format: (v) => fmtRain(v),
      axisFormat: axisNumber,
      offsetSeconds: offset,
      stepMs: HOUR,
      align: "start",
      height: 140,
      tooltipTitle: hourTitle(timeZone),
      tooltipRows: (point) => [{ color: "var(--rain)", kind: "box", value: fmtRain(point.y), label: "na hora" }],
      ariaLabel: "Chuva horária",
      },
      "Sem chuva registrada no período.",
    ),
    tableView({
      columns: [
        { label: "Hora local", value: (row) => fmtDateTime(row.observation_timestamp, timeZone) },
        { label: "Média", numeric: true, value: (row) => fmtTemp(row.temperature_avg, 1) },
        { label: "Mín.", numeric: true, value: (row) => fmtTemp(row.temperature_min, 1) },
        { label: "Máx.", numeric: true, value: (row) => fmtTemp(row.temperature_max, 1) },
        { label: "Umidade", numeric: true, value: (row) => fmtPercent(row.humidity_avg) },
        { label: "Vento", numeric: true, value: (row) => fmtWind(row.wind_speed_avg) },
        { label: "Chuva", numeric: true, value: (row) => fmtRain(row.rain_mm) },
        { label: "Ar", value: (row) => (aqiLevel(row.aqi) ? `${aqiLevel(row.aqi).label} (${row.aqi})` : "–") },
        { label: "Obs.", numeric: true, value: (row) => fmtNumber(row.observation_count) },
      ],
      rows: [...rows].reverse(),
    }),
  );
}

const PERIODS = [
  { value: "day", label: "Dia" },
  { value: "week", label: "Semana" },
  { value: "month", label: "Mês" },
  { value: "year", label: "Ano" },
];
const RANGES = [
  { value: "30", label: "30 dias" },
  { value: "90", label: "90 dias" },
  { value: "365", label: "1 ano" },
  { value: "730", label: "2 anos" },
];

function historyCard(daily, capital, route) {
  const allRows = daily?.rows || [];
  if (!allRows.length) return card("Histórico", "Agregados diários", h("p", { class: "muted", text: "Os agregados diários aparecem quando o primeiro dia local completo é fechado." }));
  const period = PERIODS.some((item) => item.value === route.params.get("agregacao")) ? route.params.get("agregacao") : "day";
  const range = RANGES.some((item) => item.value === route.params.get("intervalo")) ? route.params.get("intervalo") : "90";
  const rows = filterByDays(allRows, Number(range));
  const groups = aggregateDaily(rows, period).map((group) => ({ ...group, x: group.date.getTime() }));
  const periodLabel = PERIODS.find((item) => item.value === period).label.toLowerCase();
  const hottest = [...rows].filter((row) => isNumber(row.temperature_max)).sort((a, b) => b.temperature_max - a.temperature_max)[0];
  const coldest = [...rows].filter((row) => isNumber(row.temperature_min)).sort((a, b) => a.temperature_min - b.temperature_min)[0];
  const wettest = [...rows].filter((row) => isNumber(row.rain_mm)).sort((a, b) => b.rain_mm - a.rain_mm)[0];
  const rainDays = rows.filter((row) => (row.rain_mm || 0) >= 1).length;
  const title = (ms) =>
    period === "day"
      ? dayTitle(ms)
      : period === "week"
        ? `Semana de ${fmtIsoDate(new Date(ms).toISOString().slice(0, 10))}`
        : period === "month"
          ? capitalize(fmtIsoDate(new Date(ms).toISOString().slice(0, 10), { month: "long", year: "numeric" }))
          : String(new Date(ms).getUTCFullYear());
  const tools = h(
    "div",
    { class: "toolbar" },
    chips(PERIODS, period, (value) => setParams(route, { agregacao: value === "day" ? null : value }), "Agregação"),
    select(RANGES, range, (value) => setParams(route, { intervalo: value === "90" ? null : value }), "Intervalo"),
  );
  return cardWithTools(
    "Histórico",
    `${rows.length} dias com dados entre ${fmtIsoDate(rows[0].observation_date)} e ${fmtIsoDate(rows[rows.length - 1].observation_date)} · datas no horário local`,
    tools,
    h(
      "div",
      { class: "tiles" },
      tile("Dia mais quente", hottest ? fmtTemp(hottest.temperature_max, 1) : "–", hottest ? fmtIsoDate(hottest.observation_date) : null),
      tile("Dia mais frio", coldest ? fmtTemp(coldest.temperature_min, 1) : "–", coldest ? fmtIsoDate(coldest.observation_date) : null),
      tile("Dia mais chuvoso", wettest ? fmtRain(wettest.rain_mm) : "–", wettest ? fmtIsoDate(wettest.observation_date) : null),
      tile("Chuva acumulada", fmtRain(stats.sum(rows.map((row) => row.rain_mm)), 0), `${rainDays} dias com 1 mm ou mais`),
    ),
    chartBlock(`Temperatura por ${periodLabel} (°C) · faixa = mínima e máxima absolutas`, lineChart, {
      series: [
        {
          name: "Temperatura média",
          color: "var(--temp)",
          values: groups.map((group) => ({ x: group.x, y: group.temperature_avg })),
          band: groups.map((group) => ({ x: group.x, lo: group.temperature_min, hi: group.temperature_max })),
        },
      ],
      format: (v) => fmtTemp(v, 1),
      axisFormat: (v) => `${fmtNumber(v)}°`,
      tooltipTitle: title,
      minSpan: 4,
      ariaLabel: `Temperatura por ${periodLabel}`,
    }),
    rainBlock(
      `Chuva acumulada por ${periodLabel} (mm)`,
      groups.map((group) => ({ x: group.x, y: group.rain_mm, days: group.days })),
      {
      color: "var(--rain)",
      format: (v) => fmtRain(v),
      axisFormat: (v) => fmtCompact(v),
      stepMs: period === "day" ? 24 * HOUR : undefined,
      align: period === "day" ? "start" : "center",
      height: 150,
      tooltipTitle: title,
      tooltipRows: (point) => [
        { color: "var(--rain)", kind: "box", value: fmtRain(point.y), label: "acumulado" },
        ...(period === "day" ? [] : [{ value: fmtNumber(point.days), label: "dias com dados" }]),
      ],
      ariaLabel: `Chuva por ${periodLabel}`,
      },
      "Sem chuva registrada no período.",
    ),
    tableView({
      columns: [
        { label: "Período", value: (group) => title(group.x) },
        { label: "Média", numeric: true, value: (group) => fmtTemp(group.temperature_avg, 1) },
        { label: "Mín.", numeric: true, value: (group) => fmtTemp(group.temperature_min, 1) },
        { label: "Máx.", numeric: true, value: (group) => fmtTemp(group.temperature_max, 1) },
        { label: "Umidade", numeric: true, value: (group) => fmtPercent(group.humidity_avg) },
        { label: "Chuva", numeric: true, value: (group) => fmtRain(group.rain_mm) },
        { label: "Dias c/ chuva", numeric: true, value: (group) => fmtNumber(group.rain_days) },
        { label: "Rajada máx.", numeric: true, value: (group) => fmtWind(group.wind_gust_max) },
        { label: "Ar (média)", numeric: true, value: (group) => fmtNumber(group.aqi_avg, 1) },
        { label: "Dias", numeric: true, value: (group) => fmtNumber(group.days) },
      ],
      rows: [...groups].reverse(),
    }),
  );
}

async function capitalView(route) {
  const state = route.state;
  const [latest, forecast, hourly, daily] = await Promise.all([loadLatest(), loadForecast(state), loadHourly(state), loadDaily(state)]);
  const entry = latest?.capitals.find((item) => item.state === state);
  const capital = entry || forecast?.capital || hourly?.capital || daily?.capital;
  if (!capital) return [emptyView(`Não há dados publicados para a UF ${state}. Escolha uma das 27 capitais na visão geral.`, "Capital não encontrada")];
  const current = entry?.current;
  const timeZone = capital.timezone;
  const capitals = latest?.capitals || [capital];

  const todayKey = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  const today = (hourly?.rows || []).filter((row) => row.local_date === todayKey);
  const todayMin = stats.min(today.map((row) => row.temperature_min));
  const todayMax = stats.max(today.map((row) => row.temperature_max));

  const header = h(
    "div",
    { class: "page-head" },
    h(
      "div",
      {},
      h("a", { class: "back-link", href: "#/", text: "← Todas as capitais" }),
      h("h1", { text: capital.name }),
      h("p", { class: "subtle", text: `${capital.state} · Região ${capital.region} · hora local ${fmtTime(new Date(), timeZone)}` }),
    ),
    h("label", { class: "inline" }, "Capital", select(capitalOptions(capitals), state, (value) => (location.hash = `#/capital/${value}`), "Escolher capital")),
  );

  const hero = current
    ? h(
        "section",
        { class: "card hero" },
        h(
          "div",
          {},
          h(
            "div",
            { class: "hero-now" },
            weatherIcon(current.weather_icon, current.weather_description),
            h("div", { class: "hero-figure" }, fmtNumber(current.temperature), h("small", { text: "°C" })),
            h("div", {}, h("div", { text: capitalize(current.weather_description) }), h("div", { class: "hero-meta", text: `Sensação de ${fmtTemp(current.feels_like)}` })),
          ),
          h(
            "p",
            { class: "hero-meta" },
            "Observado às ",
            h("strong", { text: fmtTime(current.observed_at, timeZone) }),
            ` (${fmtRelative(current.observed_at)})`,
            isNumber(todayMin) ? ` · hoje até agora: mín. ${fmtTemp(todayMin)} / máx. ${fmtTemp(todayMax)}` : "",
          ),
        ),
        factsList(current, capital),
      )
    : card("Agora", null, h("p", { class: "muted", text: "Sem observação recente para esta capital." }));

  return [
    header,
    staleNotice(latest),
    h(
      "div",
      { class: "stack" },
      hero,
      h("div", { class: "grid-2" }, forecastCard(forecast, capital), h("div", { class: "stack" }, airQualityCard(entry?.air, capital), airForecastCard(forecast, capital))),
      recentCard(hourly, capital, route),
      historyCard(daily, capital, route),
    ),
  ];
}

// ---------------------------------------------------------------------------
// Compare

const COMPARE_METRICS = {
  temperature: { label: "Temperatura média (°C)", hourly: "temperature_avg", daily: "temperature_avg", format: (v) => fmtTemp(v, 1), axis: (v) => `${fmtNumber(v)}°`, minSpan: 4 },
  humidity: { label: "Umidade relativa média (%)", hourly: "humidity_avg", daily: "humidity_avg", format: fmtPercent, axis: (v) => fmtNumber(v), minSpan: 20 },
  rain: { label: "Chuva acumulada no período (mm)", hourly: "rain_mm", daily: "rain_mm", format: (v) => fmtRain(v, 0), axis: (v) => fmtCompact(v), cumulative: true },
  pm2_5: { label: "Partículas finas PM2,5 (µg/m³)", hourly: "pm2_5", daily: "pm2_5_avg", format: fmtMicrograms, axis: (v) => fmtNumber(v), minSpan: 5 },
};
const COMPARE_PERIODS = [
  { value: "7d", label: "7 dias (horário)" },
  { value: "90d", label: "90 dias (diário)" },
  { value: "1a", label: "1 ano (semanal)" },
  { value: "2a", label: "2 anos (semanal)" },
];

async function compareView(route) {
  const latest = await loadLatest();
  const capitals = latest?.capitals || [];
  const known = new Set(capitals.map((capital) => capital.state));
  // Slots keep their position (and color) when another capital is removed: "SP,,DF" keeps DF in slot 3.
  const slots = (route.params.get("ufs") ?? "SP,RJ,DF,AM")
    .split(",")
    .slice(0, 4)
    .map((value) => value.trim().toUpperCase())
    .map((value) => (known.has(value) ? value : ""));
  const metricKey = COMPARE_METRICS[route.params.get("metrica")] ? route.params.get("metrica") : "temperature";
  const metric = COMPARE_METRICS[metricKey];
  const period = COMPARE_PERIODS.some((item) => item.value === route.params.get("periodo")) ? route.params.get("periodo") : "7d";
  const writeSlots = (next) => setParams(route, { ufs: next.join(",").replace(/,+$/, "") || "," });

  const selected = slots.map((state, index) => ({ state, index })).filter((slot) => slot.state);
  const byState = new Map(capitals.map((capital) => [capital.state, capital]));
  const documents = await Promise.all(selected.map((slot) => (period === "7d" ? loadHourly(slot.state) : loadDaily(slot.state))));

  const series = selected.map((slot, position) => {
    const capital = byState.get(slot.state);
    const rows = documents[position]?.rows || [];
    let points;
    if (period === "7d") {
      points = rows.map((row) => ({ x: new Date(row.observation_timestamp).getTime(), y: row[metric.hourly] }));
    } else if (period === "90d") {
      points = filterByDays(rows, 90).map((row) => ({ x: dateFromIso(row.observation_date).getTime(), y: row[metric.daily] }));
    } else {
      const weeks = aggregateDaily(filterByDays(rows, period === "1a" ? 365 : 730), "week");
      const field = { temperature: "temperature_avg", humidity: "humidity_avg", rain: "rain_mm", pm2_5: "pm2_5_avg" }[metricKey];
      points = weeks.map((week) => ({ x: week.x ?? week.date.getTime(), y: week[field] }));
    }
    if (metric.cumulative) {
      let total = 0;
      points = points.map((point) => {
        total += isNumber(point.y) ? point.y : 0;
        return { x: point.x, y: Number(total.toFixed(2)) };
      });
    }
    return { name: `${capital.name} (${capital.state})`, short: capital.state, color: SERIES[slot.index], values: points, state: capital.state };
  });

  const freeSlot = slots.findIndex((state) => !state);
  const nextIndex = freeSlot === -1 ? slots.length : freeSlot;
  const available = capitals.filter((capital) => !slots.includes(capital.state));
  const selectionChips = h(
    "div",
    { class: "chips", role: "group", "aria-label": "Capitais comparadas" },
    selected.map((slot) => {
      const capital = byState.get(slot.state);
      const key = h("span", { class: "key-line" });
      key.style.background = SERIES[slot.index];
      return h(
        "button",
        {
          type: "button",
          class: "chip",
          "aria-label": `Remover ${capital.name}`,
          onClick: () => {
            const next = [...slots];
            next[slot.index] = "";
            writeSlots(next);
          },
        },
        key,
        ` ${capital.name}`,
        h("span", { class: "remove", "aria-hidden": "true", text: "×" }),
      );
    }),
  );
  const adder =
    nextIndex < 4
      ? select(
          [{ value: "", label: "Adicionar capital…" }, ...capitalOptions(available)],
          "",
          (value) => {
            if (!value) return;
            const next = [...slots];
            while (next.length < nextIndex) next.push("");
            next[nextIndex] = value;
            writeSlots(next);
          },
          "Adicionar capital",
        )
      : h("span", { class: "muted", text: "Máximo de 4 capitais" });

  const summaryRows = series.map((item) => {
    const values = item.values.map((point) => point.y).filter(isNumber);
    return {
      name: item.name,
      color: item.color,
      last: values[values.length - 1],
      mean: stats.mean(values),
      min: stats.min(values),
      max: stats.max(values),
      count: values.length,
    };
  });

  return [
    h("div", { class: "page-head" }, h("div", {}, h("h1", { text: "Comparar capitais" }), h("p", { class: "subtle", text: "Até 4 capitais na mesma escala · as cores acompanham cada capital" }))),
    h(
      "div",
      { class: "filters" },
      selectionChips,
      adder,
      h(
        "label",
        { class: "inline" },
        "Métrica",
        select(
          Object.entries(COMPARE_METRICS).map(([value, item]) => ({ value, label: item.label })),
          metricKey,
          (value) => setParams(route, { metrica: value === "temperature" ? null : value }),
          "Métrica",
        ),
      ),
      chips(COMPARE_PERIODS, period, (value) => setParams(route, { periodo: value === "7d" ? null : value }), "Período"),
    ),
    series.length
      ? card(
          metric.label,
          period === "7d" ? "Médias horárias (horário de Brasília no eixo)" : period === "90d" ? "Valores diários por data local" : "Médias semanais (chuva somada)",
          chartBlock(null, lineChart, {
            series,
            format: metric.format,
            axisFormat: metric.axis,
            offsetSeconds: period === "7d" ? -10800 : 0,
            tooltipTitle: period === "7d" ? hourTitle(BRASILIA) : dayTitle,
            minSpan: metric.minSpan || 0,
            zero: Boolean(metric.cumulative),
            height: 300,
            ariaLabel: `Comparação: ${metric.label}`,
            emptyMessage: "Sem dados para as capitais e o período escolhidos.",
          }),
          tableView({
            caption: "Resumo do período",
            open: true,
            columns: [
              { label: "Capital", value: (row) => row.name },
              { label: metric.cumulative ? "Total" : "Último", numeric: true, value: (row) => metric.format(row.last) },
              ...(metric.cumulative
                ? []
                : [
                    { label: "Média", numeric: true, value: (row) => metric.format(row.mean) },
                    { label: "Mínimo", numeric: true, value: (row) => metric.format(row.min) },
                    { label: "Máximo", numeric: true, value: (row) => metric.format(row.max) },
                  ]),
              { label: "Pontos", numeric: true, value: (row) => fmtNumber(row.count) },
            ],
            rows: summaryRows,
          }),
        )
      : card("Nenhuma capital selecionada", null, h("p", { class: "muted", text: "Use “Adicionar capital” para montar a comparação." })),
  ];
}

// ---------------------------------------------------------------------------
// About / pipeline status

async function aboutView() {
  const latest = await loadLatest();
  const budget = latest?.budget;
  const usage = budget ? budget.calls_month_to_date / budget.operational_limit : null;
  const products = [
    ["Current Weather", "a cada 3 minutos", "Temperatura, sensação, umidade, pressão (mar e solo), vento e rajadas, visibilidade, nuvens, chuva, nascer/pôr do sol"],
    ["5 Day / 3 Hour Forecast", "a cada hora", "40 previsões de 3 h: temperatura, probabilidade e volume de chuva, vento, condição"],
    ["Air Pollution (atual)", "a cada hora", "Índice 1–5 e concentrações de CO, NO, NO₂, O₃, SO₂, PM2,5, PM10 e NH₃"],
    ["Air Pollution (previsão)", "a cada 6 horas", "Previsão horária da qualidade do ar para 4 dias"],
  ];
  return [
    h("div", { class: "page-head" }, h("div", {}, h("h1", { text: "Sobre os dados" }), h("p", { class: "subtle", text: "Como o painel é alimentado e o que cada número significa" }))),
    h(
      "div",
      { class: "grid-2" },
      card(
        "Situação do pipeline",
        latest ? `Publicado ${fmtRelative(latest.generated_at)} · ${fmtDateTime(latest.generated_at, BRASILIA)}` : "Nenhum dado publicado ainda",
        budget
          ? h(
              "div",
              {},
              h("p", {}, h("strong", { text: `${fmtNumber(budget.calls_month_to_date)} chamadas` }), ` à OpenWeather em ${budget.month}, de um teto operacional de ${fmtNumber(budget.operational_limit)}.`),
              (() => {
                const meter = h("div", { class: `usage-meter${usage > 0.85 ? " warn" : ""}`, role: "meter", "aria-valuemin": 0, "aria-valuemax": budget.operational_limit, "aria-valuenow": budget.calls_month_to_date, "aria-label": "Uso do teto mensal" });
                const fill = h("span");
                fill.style.width = `${Math.min(100, usage * 100).toFixed(1)}%`;
                meter.appendChild(fill);
                return meter;
              })(),
              h("p", { class: "subtle", text: `Projeção para o mês: ${fmtNumber(budget.projected_month_total)} chamadas. O Planner suspende novas coletas se o teto for atingido.` }),
            )
          : h("p", { class: "muted", text: "O consumo mensal aparece quando o painel roda na AWS (métrica OpenWeatherApiCalls)." }),
        h("p", { class: "subtle", text: `Capitais com observação: ${latest ? latest.capitals.filter((c) => c.current).length : 0} de 27.` }),
      ),
      card(
        "Fluxo",
        "Tudo serverless, sem intervenção manual depois do deploy",
        h(
          "ol",
          { class: "steps" },
          h("li", { text: "EventBridge agenda o Planner, que cria um job por capital e produto e respeita o teto mensal." }),
          h("li", { text: "A fila SQS FIFO entrega os jobs ao Collector, limitado a 2 execuções simultâneas (abaixo de 60 chamadas/min)." }),
          h("li", { text: "O Collector chama a OpenWeather e grava o JSON bruto no S3 (expira em 30 dias)." }),
          h("li", { text: "O Curator, a cada hora, gera tabelas Parquet horária, diária e de previsão, recupera horas perdidas e publica as séries deste painel." }),
          h("li", { text: "O Publisher, a cada 10 minutos, publica a observação mais recente de cada capital." }),
        ),
      ),
    ),
    h(
      "div",
      { class: "stack about-sections" },
      card(
        "APIs do plano gratuito usadas",
        "OpenWeather Free: 60 chamadas/minuto e 1.000.000/mês; o projeto usa no máximo 50%",
        simpleTable(
          [
            { label: "Produto", value: (row) => row[0] },
            { label: "Frequência", value: (row) => row[1] },
            { label: "Campos aproveitados", value: (row) => row[2] },
          ],
          products,
        ),
      ),
      card(
        "Como ler os números",
        null,
        h(
          "div",
          { class: "prose" },
          h("p", { text: "Chuva: a OpenWeather informa a intensidade da última hora em mm/h. A chuva de uma hora é a média dessas intensidades; a chuva do dia é a soma das horas." }),
          h("p", { text: "Temperatura horária: média das observações distintas da hora (a OpenWeather atualiza a cada ~10 minutos, então snapshots repetidos contam uma vez); mínima e máxima são as extremas observadas." }),
          h("p", { text: "Dias e semanas usam a data local de cada capital (Acre UTC−5; Amazonas, Rondônia, Roraima, Mato Grosso e Mato Grosso do Sul UTC−4; demais UTC−3)." }),
          h("p", { text: "Qualidade do ar: índice OpenWeather de 1 (boa) a 5 (muito ruim). As barras de poluentes comparam a medição horária com as diretrizes da OMS de 2021, que são médias de 24 horas (O₃: 8 horas) — servem como referência, não como laudo." }),
        ),
        legend([
          { kind: "box", color: STATUS_COLORS.good, label: "Boa/Razoável" },
          { kind: "box", color: STATUS_COLORS.warning, label: "Moderada" },
          { kind: "box", color: STATUS_COLORS.serious, label: "Ruim" },
          { kind: "box", color: STATUS_COLORS.critical, label: "Muito ruim" },
        ]),
      ),
    ),
  ];
}

// ---------------------------------------------------------------------------
// Router, theme and refresh

function parseRoute() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  const params = new URLSearchParams(query);
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "capital" && /^[a-z]{2}$/i.test(parts[1] || "")) return { name: "capital", path: `#/capital/${parts[1].toUpperCase()}`, state: parts[1].toUpperCase(), params };
  if (parts[0] === "comparar") return { name: "compare", path: "#/comparar", params };
  if (parts[0] === "sobre") return { name: "about", path: "#/sobre", params };
  return { name: "overview", path: "#/", params };
}

const VIEWS = { overview: overviewView, capital: capitalView, compare: compareView, about: aboutView };
const TITLES = { overview: "Visão geral", capital: "Capital", compare: "Comparar", about: "Sobre os dados" };

async function render({ keepScroll = false } = {}) {
  const token = ++renderToken;
  const route = parseRoute();
  for (const link of document.querySelectorAll(".nav a")) {
    link.toggleAttribute("aria-current", link.dataset.route === route.name || (route.name === "capital" && link.dataset.route === "overview"));
    if (link.hasAttribute("aria-current")) link.setAttribute("aria-current", "page");
  }
  app.classList.add("is-loading");
  let content;
  try {
    content = await VIEWS[route.name](route);
  } catch (error) {
    console.error(error);
    content = [emptyView("Não foi possível carregar os dados agora. Tente novamente em instantes.", "Erro ao carregar")];
  }
  if (token !== renderToken) return;
  const scroll = window.scrollY;
  for (const observer of observers) observer.disconnect();
  observers = [];
  app.replaceChildren(...content.filter(Boolean));
  mountCharts(app);
  app.classList.remove("is-loading");
  const heading = app.querySelector("h1");
  document.title = `${route.name === "capital" && heading ? heading.textContent : TITLES[route.name]} · Clima das Capitais`;
  if (keepScroll) window.scrollTo(0, scroll);
}

let lastHash = location.hash;
window.addEventListener("hashchange", () => {
  const samePage = location.hash.split("?")[0] === lastHash.split("?")[0];
  lastHash = location.hash;
  render({ keepScroll: samePage });
  if (!samePage) window.scrollTo(0, 0);
});

const THEMES = ["auto", "light", "dark"];
const THEME_LABELS = { auto: "Tema: automático", light: "Tema: claro", dark: "Tema: escuro" };

function readTheme() {
  try {
    return localStorage.getItem("theme") || "auto";
  } catch {
    return "auto";
  }
}

function applyTheme(theme) {
  if (theme === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", theme);
  const button = document.getElementById("theme-toggle");
  if (button) button.textContent = THEME_LABELS[theme];
  try {
    localStorage.setItem("theme", theme);
  } catch {
    // storage may be unavailable (private mode); the theme still applies for this visit
  }
}

document.getElementById("theme-toggle")?.addEventListener("click", () => {
  const next = THEMES[(THEMES.indexOf(readTheme()) + 1) % THEMES.length];
  applyTheme(next);
  render({ keepScroll: true });
});

async function refresh() {
  if (document.hidden) return;
  const before = (await loadLatest())?.generated_at;
  const after = (await loadLatest({ force: true }))?.generated_at;
  if (after && after !== before) render({ keepScroll: true });
}

applyTheme(readTheme());
render();
refreshTimer = window.setInterval(refresh, REFRESH_MS);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
window.addEventListener("beforeunload", () => window.clearInterval(refreshTimer));
