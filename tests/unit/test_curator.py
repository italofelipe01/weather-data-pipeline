import json

from curator import handler


class FakeBody:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeS3:
    def __init__(self, objects: dict[str, dict]) -> None:
        self.objects = objects
        self.put_calls = []

    def list_objects_v2(self, **kwargs):
        prefix = kwargs["Prefix"]
        contents = [{"Key": key} for key in self.objects if key.startswith(prefix)]
        return {"Contents": contents, "IsTruncated": False}

    def get_object(self, **kwargs):
        return {"Body": FakeBody(self.objects[kwargs["Key"]])}

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        return {}


def test_curate_hour_reads_raw_and_writes_curated(monkeypatch) -> None:
    raw_key = (
        "raw/source=openweather-free-plan/product=current_weather/year=2026/month=06/day=25/hour=12/"
        "state=sp/city=sao-paulo/openweather_current_weather_sp_sao-paulo_20260625T1210Z.json"
    )
    fake_s3 = FakeS3(
        {
            raw_key: {
                "job": {
                    "product": "current_weather",
                    "city": "Sao Paulo",
                    "state": "SP",
                    "ibge_code": "3550308",
                    "latitude": -23.5505,
                    "longitude": -46.6333,
                    "snapshot_at": "2026-06-25T12:10:00Z",
                },
                "response": {
                    "dt": 1782390000,
                    "main": {"temp": 22.0, "temp_min": 21.5, "temp_max": 23.0, "feels_like": 22.4, "humidity": 70, "pressure": 1012},
                    "wind": {"speed": 3.2},
                    "clouds": {"all": 40},
                },
            }
        }
    )
    monkeypatch.setenv("RAW_DATA_BUCKET_NAME", "bucket")
    monkeypatch.setattr(handler, "_get_s3_client", lambda: fake_s3)
    result = handler.curate_hour("2026-06-25T12:00:00Z")
    assert result["records"] == 1
    assert fake_s3.put_calls[0]["Key"].endswith("weather_hourly_observations_20260625T1200Z.csv")
    assert "temperature_avg" in fake_s3.put_calls[0]["Body"].decode("utf-8")
