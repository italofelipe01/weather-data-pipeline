from __future__ import annotations

from typing import TypedDict


class Capital(TypedDict):
    city: str
    state: str
    ibge_code: str
    latitude: float
    longitude: float
    timezone: str


BRAZIL_CAPITALS: tuple[Capital, ...] = (
    {
        "city": "Rio Branco",
        "state": "AC",
        "ibge_code": "1200401",
        "latitude": -9.97499,
        "longitude": -67.8243,
        "timezone": "America/Rio_Branco",
    },
    {
        "city": "Maceio",
        "state": "AL",
        "ibge_code": "2704302",
        "latitude": -9.66599,
        "longitude": -35.735,
        "timezone": "America/Maceio",
    },
    {
        "city": "Macapa",
        "state": "AP",
        "ibge_code": "1600303",
        "latitude": 0.034934,
        "longitude": -51.0694,
        "timezone": "America/Belem",
    },
    {
        "city": "Manaus",
        "state": "AM",
        "ibge_code": "1302603",
        "latitude": -3.10194,
        "longitude": -60.025,
        "timezone": "America/Manaus",
    },
    {
        "city": "Salvador",
        "state": "BA",
        "ibge_code": "2927408",
        "latitude": -12.9714,
        "longitude": -38.5014,
        "timezone": "America/Bahia",
    },
    {
        "city": "Fortaleza",
        "state": "CE",
        "ibge_code": "2304400",
        "latitude": -3.71722,
        "longitude": -38.5433,
        "timezone": "America/Fortaleza",
    },
    {
        "city": "Brasilia",
        "state": "DF",
        "ibge_code": "5300108",
        "latitude": -15.7939,
        "longitude": -47.8828,
        "timezone": "America/Sao_Paulo",
    },
    {
        "city": "Vitoria",
        "state": "ES",
        "ibge_code": "3205309",
        "latitude": -20.3155,
        "longitude": -40.3128,
        "timezone": "America/Sao_Paulo",
    },
    {
        "city": "Goiania",
        "state": "GO",
        "ibge_code": "5208707",
        "latitude": -16.6869,
        "longitude": -49.2648,
        "timezone": "America/Sao_Paulo",
    },
    {
        "city": "Sao Luis",
        "state": "MA",
        "ibge_code": "2111300",
        "latitude": -2.53073,
        "longitude": -44.3068,
        "timezone": "America/Fortaleza",
    },
    {
        "city": "Cuiaba",
        "state": "MT",
        "ibge_code": "5103403",
        "latitude": -15.601,
        "longitude": -56.0974,
        "timezone": "America/Cuiaba",
    },
    {
        "city": "Campo Grande",
        "state": "MS",
        "ibge_code": "5002704",
        "latitude": -20.4697,
        "longitude": -54.6201,
        "timezone": "America/Campo_Grande",
    },
    {
        "city": "Belo Horizonte",
        "state": "MG",
        "ibge_code": "3106200",
        "latitude": -19.9167,
        "longitude": -43.9345,
        "timezone": "America/Sao_Paulo",
    },
    {
        "city": "Belem",
        "state": "PA",
        "ibge_code": "1501402",
        "latitude": -1.45583,
        "longitude": -48.5044,
        "timezone": "America/Belem",
    },
    {
        "city": "Joao Pessoa",
        "state": "PB",
        "ibge_code": "2507507",
        "latitude": -7.11509,
        "longitude": -34.8641,
        "timezone": "America/Fortaleza",
    },
    {
        "city": "Curitiba",
        "state": "PR",
        "ibge_code": "4106902",
        "latitude": -25.4284,
        "longitude": -49.2733,
        "timezone": "America/Sao_Paulo",
    },
    {
        "city": "Recife",
        "state": "PE",
        "ibge_code": "2611606",
        "latitude": -8.04756,
        "longitude": -34.877,
        "timezone": "America/Recife",
    },
    {
        "city": "Teresina",
        "state": "PI",
        "ibge_code": "2211001",
        "latitude": -5.08921,
        "longitude": -42.8016,
        "timezone": "America/Fortaleza",
    },
    {
        "city": "Rio de Janeiro",
        "state": "RJ",
        "ibge_code": "3304557",
        "latitude": -22.9068,
        "longitude": -43.1729,
        "timezone": "America/Sao_Paulo",
    },
    {
        "city": "Natal",
        "state": "RN",
        "ibge_code": "2408102",
        "latitude": -5.79448,
        "longitude": -35.211,
        "timezone": "America/Fortaleza",
    },
    {
        "city": "Porto Alegre",
        "state": "RS",
        "ibge_code": "4314902",
        "latitude": -30.0346,
        "longitude": -51.2177,
        "timezone": "America/Sao_Paulo",
    },
    {
        "city": "Porto Velho",
        "state": "RO",
        "ibge_code": "1100205",
        "latitude": -8.76194,
        "longitude": -63.9039,
        "timezone": "America/Porto_Velho",
    },
    {
        "city": "Boa Vista",
        "state": "RR",
        "ibge_code": "1400100",
        "latitude": 2.82384,
        "longitude": -60.6753,
        "timezone": "America/Boa_Vista",
    },
    {
        "city": "Florianopolis",
        "state": "SC",
        "ibge_code": "4205407",
        "latitude": -27.5954,
        "longitude": -48.548,
        "timezone": "America/Sao_Paulo",
    },
    {
        "city": "Sao Paulo",
        "state": "SP",
        "ibge_code": "3550308",
        "latitude": -23.5505,
        "longitude": -46.6333,
        "timezone": "America/Sao_Paulo",
    },
    {
        "city": "Aracaju",
        "state": "SE",
        "ibge_code": "2800308",
        "latitude": -10.9472,
        "longitude": -37.0731,
        "timezone": "America/Maceio",
    },
    {
        "city": "Palmas",
        "state": "TO",
        "ibge_code": "1721000",
        "latitude": -10.2491,
        "longitude": -48.3243,
        "timezone": "America/Araguaina",
    },
)


def get_capitals(states: list[str] | None = None) -> tuple[Capital, ...]:
    if not states:
        return BRAZIL_CAPITALS
    allowed = {state.upper() for state in states}
    return tuple(capital for capital in BRAZIL_CAPITALS if capital["state"] in allowed)
