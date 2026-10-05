"""Generate synthetic OpenWeather snapshots and run the real Curator/Publisher locally.

The output lands in frontend/data/, so the dashboard can be previewed without AWS or an API key:

    python scripts/sample_data.py
    python -m http.server 8000 --directory frontend
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("METRICS_DISABLED", "true")

from curator.handler import CuratorConfig, run  # noqa: E402
from publisher.handler import PublisherConfig, publish_latest  # noqa: E402
from scripts.local_s3 import LocalDirS3  # noqa: E402
from shared.capitals import BRAZIL_CAPITALS, Capital  # noqa: E402
from shared.daily_table import build_curated_daily_key, daily_records_to_parquet  # noqa: E402
from shared.source_plan import build_collection_jobs  # noqa: E402
from shared.storage import build_source_key, build_source_object, put_json_once  # noqa: E402
from shared.time_utils import floor_hour, iso_z  # noqa: E402

RAW_BUCKET = "local-raw"
SITE_BUCKET = "local-site"

# Approximate annual mean temperature (C) and seasonal amplitude per capital.
CLIMATE: dict[str, tuple[float, float]] = {
    "AC": (25.5, 1.5), "AL": (25.5, 1.5), "AP": (27.5, 0.7), "AM": (27.5, 0.8), "BA": (25.5, 1.6), "CE": (27.0, 0.8),
    "DF": (21.5, 2.0), "ES": (24.5, 2.5), "GO": (24.0, 2.0), "MA": (27.0, 0.8), "MT": (26.5, 2.0), "MS": (24.0, 3.5),
    "MG": (21.5, 2.5), "PA": (27.0, 0.6), "PB": (26.5, 1.3), "PR": (17.5, 4.5), "PE": (26.0, 1.4), "PI": (28.0, 1.5),
    "RJ": (24.0, 3.0), "RN": (26.5, 1.2), "RS": (19.5, 5.5), "RO": (26.0, 1.2), "RR": (28.0, 0.8), "SC": (21.0, 4.0),
    "SP": (20.0, 3.5), "SE": (26.0, 1.4), "TO": (27.0, 1.5),
}  # fmt: skip
HIGH_ALTITUDE = {"DF": 890.0, "GO": 930.0, "MG": 910.0, "PR": 910.0, "SP": 925.0, "MS": 960.0}


def _seed(text: str) -> int:
    return sum(ord(char) * (index + 1) for index, char in enumerate(text))


def _noise(*parts: object) -> random.Random:
    return random.Random("|".join(str(part) for part in parts))


def _temperature(capital: Capital, moment: datetime) -> float:
    base, seasonal = CLIMATE[capital["state"]]
    local = moment + timedelta(seconds=capital["utc_offset_seconds"])
    day_of_year = local.timetuple().tm_yday
    seasonal_term = seasonal * math.cos(2 * math.pi * (day_of_year - 20) / 365.25)
    hour = local.hour + local.minute / 60
    diurnal = (3.0 + seasonal / 2) * math.sin(2 * math.pi * (hour - 9) / 24)
    weather_front = 2.0 * math.sin(2 * math.pi * (local.toordinal() + _seed(capital["state"]) % 7) / 9.0)
    return round(base + seasonal_term + diurnal + weather_front + _noise(capital["state"], moment.isoformat()).gauss(0, 0.4), 2)


def _rain_rate(capital: Capital, moment: datetime) -> float:
    local = moment + timedelta(seconds=capital["utc_offset_seconds"])
    rng = _noise("rain-day", capital["state"], local.date())
    wet_season = capital["region"] in {"Norte", "Centro-Oeste", "Sudeste"} and local.month in (11, 12, 1, 2, 3)
    if rng.random() > (0.45 if wet_season else 0.22):
        return 0.0
    start = rng.randint(11, 20)
    duration = rng.randint(1, 4)
    if not start <= local.hour < start + duration:
        return 0.0
    return round(rng.uniform(0.3, 9.0) * _noise("rain", capital["state"], moment.isoformat()).uniform(0.6, 1.2), 2)


def _condition(rain: float, clouds: float, is_day: bool) -> dict[str, Any]:
    suffix = "d" if is_day else "n"
    if rain >= 4:
        return {"id": 501, "main": "Rain", "description": "chuva moderada", "icon": f"10{suffix}"}
    if rain > 0:
        return {"id": 500, "main": "Rain", "description": "chuva leve", "icon": f"10{suffix}"}
    if clouds > 84:
        return {"id": 804, "main": "Clouds", "description": "nublado", "icon": f"04{suffix}"}
    if clouds > 50:
        return {"id": 803, "main": "Clouds", "description": "nuvens quebradas", "icon": f"04{suffix}"}
    if clouds > 20:
        return {"id": 802, "main": "Clouds", "description": "nuvens dispersas", "icon": f"03{suffix}"}
    if clouds > 10:
        return {"id": 801, "main": "Clouds", "description": "algumas nuvens", "icon": f"02{suffix}"}
    return {"id": 800, "main": "Clear", "description": "céu limpo", "icon": f"01{suffix}"}


def _sun(capital: Capital, moment: datetime) -> tuple[int, int]:
    local_midnight = datetime.combine((moment + timedelta(seconds=capital["utc_offset_seconds"])).date(), datetime.min.time(), UTC)
    utc_midnight = local_midnight - timedelta(seconds=capital["utc_offset_seconds"])
    day_of_year = local_midnight.timetuple().tm_yday
    half_day = 6 + capital["latitude"] / 90 * 1.6 * math.cos(2 * math.pi * (day_of_year - 172) / 365.25)
    longitude_shift = (capital["longitude"] - (capital["utc_offset_seconds"] / 3600 * 15)) / 15
    noon = 12 - longitude_shift
    sunrise = utc_midnight + timedelta(hours=noon - half_day)
    sunset = utc_midnight + timedelta(hours=noon + half_day)
    return int(sunrise.timestamp()), int(sunset.timestamp())


def current_weather(capital: Capital, moment: datetime) -> dict[str, Any]:
    observed = moment.replace(minute=(moment.minute // 10) * 10, second=0, microsecond=0)
    temp = _temperature(capital, observed)
    rain = _rain_rate(capital, observed)
    rng = _noise("wx", capital["state"], observed.isoformat())
    humidity = max(18.0, min(100.0, 78 - 2.2 * (temp - CLIMATE[capital["state"]][0]) + (15 if rain else 0) + rng.gauss(0, 3)))
    if capital["state"] in {"DF", "GO", "TO", "MT"} and observed.month in (7, 8, 9):
        humidity = max(12.0, humidity - 35)
    clouds = 95.0 if rain else max(0.0, min(100.0, 45 + 40 * math.sin(observed.toordinal() / 3 + _seed(capital["state"]) % 5) + rng.gauss(0, 10)))
    sunrise, sunset = _sun(capital, observed)
    is_day = sunrise <= observed.timestamp() < sunset
    wind = max(0.3, 2.8 + 1.5 * math.sin(2 * math.pi * observed.hour / 24) + rng.gauss(0, 0.6))
    response: dict[str, Any] = {
        "coord": {"lon": capital["longitude"], "lat": capital["latitude"]},
        "weather": [_condition(rain, clouds, is_day)],
        "base": "stations",
        "main": {
            "temp": temp,
            "feels_like": round(temp + (humidity - 60) / 25 if temp > 24 else temp - wind / 3, 2),
            "temp_min": round(temp - 0.8, 2),
            "temp_max": round(temp + 0.8, 2),
            "pressure": round(1013 + rng.gauss(0, 3)),
            "humidity": round(humidity),
            "sea_level": round(1013 + rng.gauss(0, 3)),
            "grnd_level": round(HIGH_ALTITUDE.get(capital["state"], 1008) + rng.gauss(0, 2)),
        },
        "visibility": 6000 if rain >= 4 else 10000,
        "wind": {"speed": round(wind, 2), "deg": round((120 + 60 * math.sin(observed.toordinal() / 4) + rng.gauss(0, 15)) % 360), "gust": round(wind * 1.8, 2)},
        "clouds": {"all": round(clouds)},
        "dt": int(observed.timestamp()),
        "sys": {"country": "BR", "sunrise": sunrise, "sunset": sunset},
        "timezone": capital["utc_offset_seconds"],
        "name": capital["city"],
        "cod": 200,
    }
    if rain:
        response["rain"] = {"1h": rain}
    return response


def _air_components(capital: Capital, moment: datetime) -> dict[str, Any]:
    rng = _noise("air", capital["state"], moment.isoformat())
    urban = 1.6 if capital["state"] in {"SP", "RJ", "MG", "DF"} else 1.0
    rush = 1.4 if (moment + timedelta(seconds=capital["utc_offset_seconds"])).hour in (7, 8, 18, 19) else 1.0
    pm2_5 = max(1.0, rng.gauss(9, 4) * urban * rush)
    components = {
        "co": round(rng.uniform(180, 420) * urban, 2),
        "no": round(rng.uniform(0, 3) * rush, 2),
        "no2": round(rng.uniform(2, 25) * urban * rush, 2),
        "o3": round(rng.uniform(20, 95), 2),
        "so2": round(rng.uniform(0.5, 9), 2),
        "pm2_5": round(pm2_5, 2),
        "pm10": round(pm2_5 * rng.uniform(1.3, 2.1), 2),
        "nh3": round(rng.uniform(0.2, 6), 2),
    }
    aqi = 1 if pm2_5 < 10 else 2 if pm2_5 < 25 else 3 if pm2_5 < 50 else 4
    return {"dt": int(moment.timestamp()), "main": {"aqi": aqi}, "components": components}


def air_pollution(capital: Capital, moment: datetime) -> dict[str, Any]:
    return {"coord": {"lon": capital["longitude"], "lat": capital["latitude"]}, "list": [_air_components(capital, floor_hour(moment))]}


def air_pollution_forecast(capital: Capital, moment: datetime) -> dict[str, Any]:
    start = floor_hour(moment)
    return {
        "coord": {"lon": capital["longitude"], "lat": capital["latitude"]},
        "list": [_air_components(capital, start + timedelta(hours=offset)) for offset in range(96)],
    }


def forecast(capital: Capital, moment: datetime) -> dict[str, Any]:
    start = floor_hour(moment) + timedelta(hours=3 - floor_hour(moment).hour % 3)
    items = []
    for index in range(40):
        when = start + timedelta(hours=3 * index)
        current = current_weather(capital, when)
        rain = sum(_rain_rate(capital, when - timedelta(hours=offset)) for offset in range(3))
        pop = (
            min(1.0, round(0.15 + rain / 6 + _noise("pop", capital["state"], when.isoformat()).uniform(0, 0.25), 2))
            if rain
            else round(_noise("pop", capital["state"], when.isoformat()).uniform(0, 0.25), 2)
        )
        item = {
            "dt": int(when.timestamp()),
            "main": {**current["main"], "temp_kf": 0},
            "weather": current["weather"],
            "clouds": current["clouds"],
            "wind": current["wind"],
            "visibility": current["visibility"],
            "pop": pop,
            "sys": {"pod": current["weather"][0]["icon"][-1]},
            "dt_txt": when.strftime("%Y-%m-%d %H:%M:%S"),
        }
        if rain:
            item["rain"] = {"3h": round(rain, 2)}
        items.append(item)
    sunrise, sunset = _sun(capital, moment)
    return {
        "cod": "200",
        "message": 0,
        "cnt": len(items),
        "list": items,
        "city": {
            "name": capital["city"],
            "coord": {"lat": capital["latitude"], "lon": capital["longitude"]},
            "country": "BR",
            "population": _noise("pop", capital["state"]).randint(250_000, 12_000_000),
            "timezone": capital["utc_offset_seconds"],
            "sunrise": sunrise,
            "sunset": sunset,
        },
    }


BUILDERS = {
    "current_weather": current_weather,
    "air_pollution": air_pollution,
    "forecast_5d_3h": forecast,
    "air_pollution_forecast": air_pollution_forecast,
}


def _store(s3: LocalDirS3, product: str, moment: datetime) -> int:
    jobs = build_collection_jobs(BRAZIL_CAPITALS, [product], "metric", "pt_br", iso_z(moment))
    for job, capital in zip(jobs, BRAZIL_CAPITALS, strict=True):
        put_json_once(s3, RAW_BUCKET, build_source_key(job), build_source_object(job, BUILDERS[product](capital, moment)))
    return len(jobs)


def generate_raw(s3: LocalDirS3, now: datetime, hours: int) -> int:
    stored = 0
    first = floor_hour(now) - timedelta(hours=hours)
    for offset in range(hours + 1):
        hour = first + timedelta(hours=offset)
        for minute in (0, 20, 40):
            moment = hour + timedelta(minutes=minute)
            if moment <= now:
                stored += _store(s3, "current_weather", moment)
        if hour + timedelta(minutes=5) <= now:
            stored += _store(s3, "forecast_5d_3h", hour + timedelta(minutes=5))
        if hour + timedelta(minutes=35) <= now:
            stored += _store(s3, "air_pollution", hour + timedelta(minutes=35))
        if hour.hour % 6 == 0 and hour + timedelta(minutes=50) <= now:
            stored += _store(s3, "air_pollution_forecast", hour + timedelta(minutes=50))
    return stored


def generate_daily_history(s3: LocalDirS3, first_day: date, last_day: date) -> int:
    """Daily rows for dates older than the synthetic raw window, so long-range charts have something to show."""
    written = 0
    day = first_day
    while day <= last_day:
        records = []
        for capital in BRAZIL_CAPITALS:
            noon = datetime.combine(day, datetime.min.time(), UTC) + timedelta(hours=15)
            temps = [_temperature(capital, noon - timedelta(hours=12) + timedelta(hours=hour)) for hour in range(24)]
            rain = round(sum(_rain_rate(capital, noon - timedelta(hours=12) + timedelta(hours=hour)) for hour in range(24)), 2)
            air = _air_components(capital, noon)
            weather = current_weather(capital, noon)
            records.append(
                {
                    "observation_date": day,
                    "year": day.year,
                    "month": day.month,
                    "day": day.day,
                    "city": capital["city"],
                    "state": capital["state"],
                    "region": capital["region"],
                    "ibge_code": capital["ibge_code"],
                    "latitude": capital["latitude"],
                    "longitude": capital["longitude"],
                    "temperature_avg": round(sum(temps) / len(temps), 2),
                    "temperature_min": min(temps),
                    "temperature_max": max(temps),
                    "temperature_amplitude": round(max(temps) - min(temps), 2),
                    "feels_like_avg": round(sum(temps) / len(temps) + 0.5, 2),
                    "feels_like_max": round(max(temps) + 1.2, 2),
                    "humidity_avg": weather["main"]["humidity"],
                    "humidity_min": max(10, weather["main"]["humidity"] - 18),
                    "humidity_max": min(100, weather["main"]["humidity"] + 15),
                    "pressure_avg": weather["main"]["pressure"],
                    "wind_speed_avg": weather["wind"]["speed"],
                    "wind_speed_max": weather["wind"]["gust"],
                    "wind_gust_max": round(weather["wind"]["gust"] * 1.3, 2),
                    "clouds_avg": weather["clouds"]["all"],
                    "visibility_avg": weather["visibility"],
                    "rain_mm": rain,
                    "rain_hours": sum(1 for hour in range(24) if _rain_rate(capital, noon - timedelta(hours=12) + timedelta(hours=hour))),
                    "snow_mm": 0.0,
                    "weather_main": "Rain" if rain else weather["weather"][0]["main"],
                    "weather_description": "chuva leve" if rain else weather["weather"][0]["description"],
                    "weather_icon": "10d" if rain else weather["weather"][0]["icon"][:-1] + "d",
                    "aqi_avg": float(air["main"]["aqi"]),
                    "aqi_max": air["main"]["aqi"],
                    "pm2_5_avg": air["components"]["pm2_5"],
                    "pm10_avg": air["components"]["pm10"],
                    "o3_avg": air["components"]["o3"],
                    "no2_avg": air["components"]["no2"],
                    "so2_avg": air["components"]["so2"],
                    "co_avg": air["components"]["co"],
                    "hours_observed": 24,
                    "sample_count": 480,
                    "processed_at": datetime.now(UTC),
                }
            )
        s3.put_object(Bucket=RAW_BUCKET, Key=build_curated_daily_key(day), Body=daily_records_to_parquet(records))
        written += 1
        day += timedelta(days=1)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Gera dados sinteticos e executa Curator/Publisher locais para pre-visualizar o dashboard.")
    parser.add_argument("--hours", type=int, default=36, help="Horas de snapshots raw sinteticos (padrao: 36)")
    parser.add_argument("--history-days", type=int, default=400, help="Dias de historico diario sintetico (padrao: 400)")
    parser.add_argument("--raw-dir", default=".local-data/raw", help="Diretorio do bucket raw local")
    parser.add_argument("--site-dir", default="frontend", help="Diretorio do site (os JSON vao para <site-dir>/data)")
    parser.add_argument("--now", default="", help="Instante de referencia ISO-8601 (padrao: agora)")
    args = parser.parse_args()

    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")).astimezone(UTC) if args.now else datetime.now(UTC)
    s3 = LocalDirS3({RAW_BUCKET: ROOT / args.raw_dir, SITE_BUCKET: ROOT / args.site_dir})
    stored = generate_raw(s3, now, args.hours)
    raw_start = (floor_hour(now) - timedelta(hours=args.hours) - timedelta(hours=5)).date()
    history = generate_daily_history(s3, raw_start - timedelta(days=args.history_days), raw_start - timedelta(days=1)) if args.history_days else 0
    config = CuratorConfig(raw_bucket=RAW_BUCKET, site_bucket=SITE_BUCKET, lookback_hours=args.hours)
    curation = run({"rebuild_serving": True}, s3, config, now)
    latest = publish_latest(s3, PublisherConfig(raw_bucket=RAW_BUCKET, site_bucket=SITE_BUCKET), now)
    print(
        json.dumps(
            {
                "raw_snapshots": stored,
                "synthetic_daily_files": history,
                "hours_curated": curation["hours_written"],
                "daily_curated": [item["date"] for item in curation["daily"] if item["status"] == "written"],
                "published": curation["published"],
                "latest_observation_at": latest["latest_observation_at"],
            },
            indent=2,
        )
    )
    print(f"\nDashboard: python -m http.server 8000 --directory {args.site_dir}  ->  http://localhost:8000/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
