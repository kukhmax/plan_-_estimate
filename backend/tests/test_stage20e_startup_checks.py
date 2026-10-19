"""Stage 20E finding F3 -- production refuses to start with a weak session secret, a wrong bot token, mock sign-in or debug on."""
import pytest

from app.core.config import Settings
from tests.conftest import fresh_kek
from app.core.startup_checks import ensure_production_configuration, production_problems

GOOD = dict(
    APP_ENV="production", ENVIRONMENT="production", DEBUG=False, MOCK_TELEGRAM_AUTH=False,
    JWT_SECRET_KEY="9f2c1a7e5b3d48aa90c6e1f7d2b4a8c3e5f60718293a4b5c6d7e8f9012a3b4c5",
    TELEGRAM_BOT_TOKEN="7654321098:AAFxyzABCdefGHIjklMNOpqrSTUvwxyz012",
)


def settings(**over) -> Settings:
    return Settings(_env_file=None, **(GOOD | over))


def test_a_good_production_configuration_goes_on():
    assert production_problems(settings()) == []
    ensure_production_configuration(settings())


@pytest.mark.parametrize("secret", ["", "short", "CHANGE_ME", "insecure-dev-secret-change-in-production", "change-this-secret-in-production-0123456789", "x" * 31, "my-example-secret-key-0123456789abcdefghijk"])
def test_a_weak_or_placeholder_session_secret_stops_the_start(secret):
    problems = production_problems(settings(JWT_SECRET_KEY=secret))
    assert len(problems) == 1 and problems[0].startswith("JWT_SECRET_KEY")


@pytest.mark.parametrize("token", ["", "CHANGE_ME", "123456789:short", "no-colon-at-all-0123456789abcdefghijklmnop", "abc:AAFxyzABCdefGHIjklMNOpqrSTUvwxyz012"])
def test_an_empty_or_wrong_bot_token_stops_the_start(token):
    problems = production_problems(settings(TELEGRAM_BOT_TOKEN=token))
    assert len(problems) == 1 and problems[0].startswith("TELEGRAM_BOT_TOKEN")


def test_mock_sign_in_and_debug_stop_the_start_and_all_problems_are_named_together():
    with pytest.raises(RuntimeError) as caught:
        ensure_production_configuration(settings(MOCK_TELEGRAM_AUTH=True, DEBUG=True, JWT_SECRET_KEY="CHANGE_ME"))
    message = str(caught.value)
    assert "JWT_SECRET_KEY" in message and "MOCK_TELEGRAM_AUTH" in message and "DEBUG" in message


def test_the_message_never_shows_a_value():
    secret, token = "CHANGE_ME_visible_value", "visible:token-value-0123456789"
    with pytest.raises(RuntimeError) as caught:
        ensure_production_configuration(settings(JWT_SECRET_KEY=secret, TELEGRAM_BOT_TOKEN=token))
    assert secret not in str(caught.value) and token not in str(caught.value)


def test_development_is_not_checked():
    assert production_problems(settings(APP_ENV="development", ENVIRONMENT="development", JWT_SECRET_KEY="", TELEGRAM_BOT_TOKEN="", MOCK_TELEGRAM_AUTH=True, DEBUG=True)) == []


def test_the_startup_of_the_application_runs_the_check():
    import inspect

    import app.main as main

    assert "ensure_production_configuration(settings)" in inspect.getsource(main.lifespan)


async def test_the_application_itself_refuses_to_start_in_production_with_a_weak_secret(monkeypatch):
    from app.core.config import settings as live
    from app.main import app, lifespan

    monkeypatch.setattr(live, "APP_ENV", "production")
    monkeypatch.setattr(live, "ENVIRONMENT", "production")
    monkeypatch.setattr(live, "DEBUG", False)
    monkeypatch.setattr(live, "MOCK_TELEGRAM_AUTH", False)
    monkeypatch.setattr(live, "JWT_SECRET_KEY", "CHANGE_ME")
    monkeypatch.setattr(live, "DATA_KEK", fresh_kek())  # the key of the server is checked first; here it is fine
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        async with lifespan(app):
            pass
