from __future__ import annotations

from typing import TypedDict


class Capital(TypedDict):
    city: str
    display_name: str
    state: str
    region: str
    ibge_code: str
    latitude: float
    longitude: float
    timezone: str
    utc_offset_seconds: int


REGIONS = ("Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul")

# Brazil has no daylight saving time since 2019, so a fixed UTC offset per capital is exact.
_BRT = -3 * 3600
_AMT = -4 * 3600
_ACT = -5 * 3600

# fmt: off
_CAPITAL_ROWS: tuple[tuple[str, str, str, str, str, float, float, str, int], ...] = (
    # city, display_name, state, region, ibge_code, latitude, longitude, timezone, utc_offset_seconds
    ("Rio Branco", "Rio Branco", "AC", "Norte", "1200401", -9.97499, -67.8243, "America/Rio_Branco", _ACT),
    ("Maceio", "Maceió", "AL", "Nordeste", "2704302", -9.66599, -35.735, "America/Maceio", _BRT),
    ("Macapa", "Macapá", "AP", "Norte", "1600303", 0.034934, -51.0694, "America/Belem", _BRT),
    ("Manaus", "Manaus", "AM", "Norte", "1302603", -3.10194, -60.025, "America/Manaus", _AMT),
    ("Salvador", "Salvador", "BA", "Nordeste", "2927408", -12.9714, -38.5014, "America/Bahia", _BRT),
    ("Fortaleza", "Fortaleza", "CE", "Nordeste", "2304400", -3.71722, -38.5433, "America/Fortaleza", _BRT),
    ("Brasilia", "Brasília", "DF", "Centro-Oeste", "5300108", -15.7939, -47.8828, "America/Sao_Paulo", _BRT),
    ("Vitoria", "Vitória", "ES", "Sudeste", "3205309", -20.3155, -40.3128, "America/Sao_Paulo", _BRT),
    ("Goiania", "Goiânia", "GO", "Centro-Oeste", "5208707", -16.6869, -49.2648, "America/Sao_Paulo", _BRT),
    ("Sao Luis", "São Luís", "MA", "Nordeste", "2111300", -2.53073, -44.3068, "America/Fortaleza", _BRT),
    ("Cuiaba", "Cuiabá", "MT", "Centro-Oeste", "5103403", -15.601, -56.0974, "America/Cuiaba", _AMT),
    ("Campo Grande", "Campo Grande", "MS", "Centro-Oeste", "5002704", -20.4697, -54.6201, "America/Campo_Grande", _AMT),
    ("Belo Horizonte", "Belo Horizonte", "MG", "Sudeste", "3106200", -19.9167, -43.9345, "America/Sao_Paulo", _BRT),
    ("Belem", "Belém", "PA", "Norte", "1501402", -1.45583, -48.5044, "America/Belem", _BRT),
    ("Joao Pessoa", "João Pessoa", "PB", "Nordeste", "2507507", -7.11509, -34.8641, "America/Fortaleza", _BRT),
    ("Curitiba", "Curitiba", "PR", "Sul", "4106902", -25.4284, -49.2733, "America/Sao_Paulo", _BRT),
    ("Recife", "Recife", "PE", "Nordeste", "2611606", -8.04756, -34.877, "America/Recife", _BRT),
    ("Teresina", "Teresina", "PI", "Nordeste", "2211001", -5.08921, -42.8016, "America/Fortaleza", _BRT),
    ("Rio de Janeiro", "Rio de Janeiro", "RJ", "Sudeste", "3304557", -22.9068, -43.1729, "America/Sao_Paulo", _BRT),
    ("Natal", "Natal", "RN", "Nordeste", "2408102", -5.79448, -35.211, "America/Fortaleza", _BRT),
    ("Porto Alegre", "Porto Alegre", "RS", "Sul", "4314902", -30.0346, -51.2177, "America/Sao_Paulo", _BRT),
    ("Porto Velho", "Porto Velho", "RO", "Norte", "1100205", -8.76194, -63.9039, "America/Porto_Velho", _AMT),
    ("Boa Vista", "Boa Vista", "RR", "Norte", "1400100", 2.82384, -60.6753, "America/Boa_Vista", _AMT),
    ("Florianopolis", "Florianópolis", "SC", "Sul", "4205407", -27.5954, -48.548, "America/Sao_Paulo", _BRT),
    ("Sao Paulo", "São Paulo", "SP", "Sudeste", "3550308", -23.5505, -46.6333, "America/Sao_Paulo", _BRT),
    ("Aracaju", "Aracaju", "SE", "Nordeste", "2800308", -10.9472, -37.0731, "America/Maceio", _BRT),
    ("Palmas", "Palmas", "TO", "Norte", "1721000", -10.2491, -48.3243, "America/Araguaina", _BRT),
)
# fmt: on

BRAZIL_CAPITALS: tuple[Capital, ...] = tuple(
    {
        "city": city,
        "display_name": display_name,
        "state": state,
        "region": region,
        "ibge_code": ibge_code,
        "latitude": latitude,
        "longitude": longitude,
        "timezone": timezone,
        "utc_offset_seconds": utc_offset_seconds,
    }
    for city, display_name, state, region, ibge_code, latitude, longitude, timezone, utc_offset_seconds in _CAPITAL_ROWS
)

_BY_STATE: dict[str, Capital] = {capital["state"]: capital for capital in BRAZIL_CAPITALS}


def get_capitals(states: list[str] | None = None) -> tuple[Capital, ...]:
    if not states:
        return BRAZIL_CAPITALS
    allowed = {str(state).strip().upper() for state in states}
    unknown = sorted(allowed - set(_BY_STATE))
    if unknown:
        raise ValueError(f"unknown Brazilian UF codes: {', '.join(unknown)}")
    return tuple(capital for capital in BRAZIL_CAPITALS if capital["state"] in allowed)


def capital_by_state(state: str) -> Capital | None:
    return _BY_STATE.get(str(state).strip().upper())
