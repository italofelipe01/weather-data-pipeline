from shared import secrets


class FakeSsm:
    def __init__(self, value: str) -> None:
        self.value = value
        self.calls = 0

    def get_parameter(self, **kwargs):
        self.calls += 1
        assert kwargs["WithDecryption"] is True
        return {"Parameter": {"Value": self.value}}


def test_get_openweather_api_key_caches_success(monkeypatch) -> None:
    secrets.reset_api_key_cache()
    fake = FakeSsm("secret")
    monkeypatch.setenv("API_KEY_CACHE_TTL_SECONDS", "300")
    assert secrets.get_openweather_api_key(fake, "/param") == "secret"
    assert secrets.get_openweather_api_key(fake, "/param") == "secret"
    assert fake.calls == 1


def test_get_openweather_api_key_rejects_empty_value() -> None:
    secrets.reset_api_key_cache()
    fake = FakeSsm("")
    try:
        secrets.get_openweather_api_key(fake, "/param")
    except RuntimeError as exc:
        assert "empty" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
