// Data access for the JSON documents published by the Curator and the Publisher under data/.

const CACHE_MS = 60_000;
const cache = new Map();

export async function loadJson(path, { force = false } = {}) {
  const cached = cache.get(path);
  if (!force && cached && Date.now() - cached.at < CACHE_MS) return cached.promise;
  const promise = fetch(`data/${path}`, { cache: "no-cache" })
    .then((response) => (response.ok ? response.json() : null))
    .catch(() => null);
  cache.set(path, { at: Date.now(), promise });
  const value = await promise;
  if (value === null) cache.delete(path);
  return value;
}

export const loadLatest = (options) => loadJson("latest.json", options);
export const loadHourly = (state) => loadJson(`hourly/${state.toLowerCase()}.json`);
export const loadDaily = (state) => loadJson(`daily/${state.toLowerCase()}.json`);
export const loadForecast = (state) => loadJson(`forecast/${state.toLowerCase()}.json`);

export const REGIONS = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"];

const present = (values) => values.filter((value) => typeof value === "number" && Number.isFinite(value));
const mean = (values) => {
  const numbers = present(values);
  return numbers.length ? numbers.reduce((sum, value) => sum + value, 0) / numbers.length : null;
};
const sum = (values) => {
  const numbers = present(values);
  return numbers.length ? numbers.reduce((total, value) => total + value, 0) : null;
};
const min = (values) => {
  const numbers = present(values);
  return numbers.length ? Math.min(...numbers) : null;
};
const max = (values) => {
  const numbers = present(values);
  return numbers.length ? Math.max(...numbers) : null;
};

export function mode(values) {
  const counts = new Map();
  let best = null;
  let bestCount = 0;
  for (const value of values) {
    if (value == null) continue;
    const count = (counts.get(value) || 0) + 1;
    counts.set(value, count);
    if (count >= bestCount) {
      best = value;
      bestCount = count;
    }
  }
  return best;
}

export const stats = { mean, sum, min, max };

function isoDateToUtc(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function periodStart(date, period) {
  const start = new Date(date);
  if (period === "week") {
    const weekday = (start.getUTCDay() + 6) % 7; // Monday = 0
    start.setUTCDate(start.getUTCDate() - weekday);
  } else if (period === "month") {
    start.setUTCDate(1);
  } else if (period === "year") {
    start.setUTCMonth(0, 1);
  }
  return start;
}

const PERIOD_DAYS = { day: 1, week: 7, month: 30, year: 365 };

// Aggregate daily rows (local dates) into weeks, months or years. Rainfall is summed, everything else averaged.
export function aggregateDaily(rows, period = "day") {
  const groups = new Map();
  for (const row of rows) {
    if (!row.observation_date) continue;
    const start = periodStart(isoDateToUtc(row.observation_date), period);
    const key = start.toISOString().slice(0, 10);
    if (!groups.has(key)) groups.set(key, { start, rows: [] });
    groups.get(key).rows.push(row);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, group]) => {
      const items = group.rows;
      return {
        key,
        date: group.start,
        days: items.length,
        expected_days: PERIOD_DAYS[period],
        temperature_avg: mean(items.map((row) => row.temperature_avg)),
        temperature_min: min(items.map((row) => row.temperature_min)),
        temperature_max: max(items.map((row) => row.temperature_max)),
        humidity_avg: mean(items.map((row) => row.humidity_avg)),
        humidity_min: min(items.map((row) => row.humidity_min)),
        rain_mm: sum(items.map((row) => row.rain_mm)),
        rain_days: items.filter((row) => (row.rain_mm || 0) >= 1).length,
        wind_speed_avg: mean(items.map((row) => row.wind_speed_avg)),
        wind_gust_max: max(items.map((row) => row.wind_gust_max)),
        aqi_avg: mean(items.map((row) => row.aqi_avg)),
        pm2_5_avg: mean(items.map((row) => row.pm2_5_avg)),
        weather_icon: mode(items.map((row) => row.weather_icon)),
      };
    });
}

// Summarise the 3-hour forecast per local calendar day.
export function forecastByDay(items, timeZone) {
  const formatter = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" });
  const hourFormatter = new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", hourCycle: "h23" });
  const days = new Map();
  for (const item of items || []) {
    const date = new Date(item.forecast_time);
    const key = formatter.format(date);
    if (!days.has(key)) days.set(key, []);
    days.get(key).push({ ...item, localHour: Number(hourFormatter.format(date)) });
  }
  return [...days.entries()].map(([key, dayItems]) => {
    const daytime = dayItems.filter((item) => item.localHour >= 9 && item.localHour <= 18);
    return {
      key,
      date: new Date(dayItems[0].forecast_time),
      temp_min: min(dayItems.map((item) => item.temp_min ?? item.temperature)),
      temp_max: max(dayItems.map((item) => item.temp_max ?? item.temperature)),
      pop_max: max(dayItems.map((item) => item.pop)),
      rain_mm: sum(dayItems.map((item) => item.rain_3h)),
      icon: mode((daytime.length ? daytime : dayItems).map((item) => item.weather_icon)),
      description: mode((daytime.length ? daytime : dayItems).map((item) => item.weather_description)),
      partial: dayItems.length < 8,
    };
  });
}

export function filterByDays(rows, days, dateKey = "observation_date") {
  if (!days || !rows.length) return rows;
  const last = rows[rows.length - 1][dateKey];
  const lastTime = last.length === 10 ? isoDateToUtc(last).getTime() : new Date(last).getTime();
  const cutoff = lastTime - (days - 1) * 86_400_000;
  return rows.filter((row) => {
    const value = row[dateKey];
    const time = value.length === 10 ? isoDateToUtc(value).getTime() : new Date(value).getTime();
    return time >= cutoff;
  });
}

export function dateFromIso(isoDate) {
  return isoDateToUtc(isoDate);
}
