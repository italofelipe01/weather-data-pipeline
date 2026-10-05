// Formatting helpers (pt-BR). OpenWeather is queried with units=metric: temperature in C, wind in m/s.

const numberFormats = new Map();

function numberFormat(digits) {
  if (!numberFormats.has(digits)) {
    numberFormats.set(digits, new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits }));
  }
  return numberFormats.get(digits);
}

export const isNumber = (value) => typeof value === "number" && Number.isFinite(value);

export function fmtNumber(value, digits = 0) {
  return isNumber(value) ? numberFormat(digits).format(value) : "–";
}

export const fmtTemp = (value, digits = 0) => (isNumber(value) ? `${fmtNumber(value, digits)}°C` : "–");
export const fmtPercent = (value) => (isNumber(value) ? `${fmtNumber(value)}%` : "–");
export const fmtPressure = (value) => (isNumber(value) ? `${fmtNumber(value)} hPa` : "–");
export const fmtRain = (value, digits = 1) => (isNumber(value) ? `${fmtNumber(value, digits)} mm` : "–");
export const fmtRainRate = (value) => (isNumber(value) ? `${fmtNumber(value, 1)} mm/h` : "–");
export const fmtMicrograms = (value) => (isNumber(value) ? `${fmtNumber(value, 1)} µg/m³` : "–");
export const toKmh = (metersPerSecond) => (isNumber(metersPerSecond) ? metersPerSecond * 3.6 : null);
export const fmtWind = (metersPerSecond) => (isNumber(metersPerSecond) ? `${fmtNumber(toKmh(metersPerSecond))} km/h` : "–");

export function fmtVisibility(meters) {
  if (!isNumber(meters)) return "–";
  return meters >= 10000 ? "10 km ou mais" : `${fmtNumber(meters / 1000, 1)} km`;
}

export function fmtCompact(value) {
  if (!isNumber(value)) return "–";
  return new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

const COMPASS = ["N", "NNE", "NE", "ENE", "L", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"];

export function compass(degrees) {
  if (!isNumber(degrees)) return "";
  return COMPASS[Math.round((((degrees % 360) + 360) % 360) / 22.5) % 16];
}

export const AQI_LEVELS = {
  1: { label: "Boa", status: "good", icon: "●" },
  2: { label: "Razoável", status: "good", icon: "●" },
  3: { label: "Moderada", status: "warning", icon: "▲" },
  4: { label: "Ruim", status: "serious", icon: "▲" },
  5: { label: "Muito ruim", status: "critical", icon: "■" },
};

export function aqiLevel(aqi) {
  return AQI_LEVELS[Math.round(aqi)] || null;
}

// WHO 2021 air quality guideline levels (24-hour means, O3 8-hour), in µg/m³.
export const POLLUTANTS = [
  { key: "pm2_5", label: "PM2,5", name: "Partículas finas", guideline: 15 },
  { key: "pm10", label: "PM10", name: "Partículas inaláveis", guideline: 45 },
  { key: "o3", label: "O₃", name: "Ozônio", guideline: 100 },
  { key: "no2", label: "NO₂", name: "Dióxido de nitrogênio", guideline: 25 },
  { key: "so2", label: "SO₂", name: "Dióxido de enxofre", guideline: 40 },
  { key: "co", label: "CO", name: "Monóxido de carbono", guideline: 4000 },
  { key: "nh3", label: "NH₃", name: "Amônia", guideline: null },
  { key: "no", label: "NO", name: "Monóxido de nitrogênio", guideline: null },
];

export function capitalize(text) {
  if (!text) return "";
  return text.charAt(0).toLocaleUpperCase("pt-BR") + text.slice(1);
}

const dateFormats = new Map();

function dateFormat(timeZone, options) {
  const key = `${timeZone}|${JSON.stringify(options)}`;
  if (!dateFormats.has(key)) {
    dateFormats.set(key, new Intl.DateTimeFormat("pt-BR", { timeZone, ...options }));
  }
  return dateFormats.get(key);
}

export const parseDate = (value) => (value ? new Date(value) : null);

export function fmtTime(value, timeZone = "America/Sao_Paulo") {
  const date = value instanceof Date ? value : parseDate(value);
  return date ? dateFormat(timeZone, { hour: "2-digit", minute: "2-digit" }).format(date) : "–";
}

export function fmtDateTime(value, timeZone = "America/Sao_Paulo") {
  const date = value instanceof Date ? value : parseDate(value);
  return date ? dateFormat(timeZone, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date) : "–";
}

export function fmtWeekday(value, timeZone = "America/Sao_Paulo") {
  const date = value instanceof Date ? value : parseDate(value);
  return date ? capitalize(dateFormat(timeZone, { weekday: "short", day: "2-digit" }).format(date).replace(".", "")) : "–";
}

// Calendar dates (YYYY-MM-DD) are local dates already; format them without shifting time zones.
export function fmtIsoDate(isoDate, options = { day: "2-digit", month: "2-digit", year: "numeric" }) {
  if (!isoDate) return "–";
  const [year, month, day] = isoDate.split("-").map(Number);
  return dateFormat("UTC", options).format(new Date(Date.UTC(year, month - 1, day || 1)));
}

export function fmtRelative(value, now = new Date()) {
  const date = value instanceof Date ? value : parseDate(value);
  if (!date) return "";
  const minutes = Math.round((now - date) / 60000);
  if (minutes < 1) return "agora";
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `há ${hours} h`;
  return `há ${Math.round(hours / 24)} dias`;
}

export function fmtDuration(milliseconds) {
  if (!isNumber(milliseconds)) return "–";
  const minutes = Math.round(milliseconds / 60000);
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}
