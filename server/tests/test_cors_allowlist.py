"""GAP M2: CORS allowlist is config-driven and parsed safely (server/api.py).

The dashboard origin allowlist comes from REDDIAL_CORS_ORIGINS (comma-separated).
The audit flagged this as untested. These tests pin the parsing contract:
  * comma-split into multiple origins
  * surrounding whitespace is trimmed per origin
  * empty / blank / unset env falls back to the default (http://localhost:5173)
  * no wildcard "*" sneaks in from a blank value

We exercise the real module-load path: set the env, importlib.reload(api), then
introspect the configured CORSMiddleware's allow_origins. Module state is always
restored (reload with env cleared) so the rest of the suite sees the default.

Everything is hermetic — importing api builds a FastAPI app in-process; no
network, Twilio, Cekura, or NVIDIA calls happen.
"""

import importlib

import pytest

import api


def _cors_origins_after_reload():
    """Reload api and return the allow_origins list the CORSMiddleware was
    configured with, by introspecting the Starlette middleware stack."""
    importlib.reload(api)
    from starlette.middleware.cors import CORSMiddleware

    for mw in api.app.user_middleware:
        if mw.cls is CORSMiddleware:
            # Starlette stores middleware kwargs on the Middleware wrapper.
            return list(mw.kwargs["allow_origins"])
    raise AssertionError("CORSMiddleware not found on app.user_middleware")


@pytest.fixture(autouse=True)
def _restore_api_module():
    # After each test, clear the env override and reload so api.app returns to
    # its default CORS config for any other test importing `api`.
    yield
    import os

    os.environ.pop("REDDIAL_CORS_ORIGINS", None)
    importlib.reload(api)


def test_cors_default_when_env_unset(monkeypatch):
    monkeypatch.delenv("REDDIAL_CORS_ORIGINS", raising=False)
    origins = _cors_origins_after_reload()
    assert origins == ["http://localhost:5173"]
    assert origins == api.DEFAULT_CORS_ORIGINS


def test_cors_empty_string_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("REDDIAL_CORS_ORIGINS", "")
    origins = _cors_origins_after_reload()
    assert origins == api.DEFAULT_CORS_ORIGINS


def test_cors_blank_and_whitespace_only_falls_back_to_default(monkeypatch):
    # A value of only commas/whitespace yields no real origins -> default.
    monkeypatch.setenv("REDDIAL_CORS_ORIGINS", "  ,  , ")
    origins = _cors_origins_after_reload()
    assert origins == api.DEFAULT_CORS_ORIGINS
    # Must NOT collapse to a wildcard.
    assert "*" not in origins


def test_cors_comma_split_into_multiple_origins(monkeypatch):
    monkeypatch.setenv(
        "REDDIAL_CORS_ORIGINS",
        "https://dash.example.com,https://admin.example.com",
    )
    origins = _cors_origins_after_reload()
    assert origins == [
        "https://dash.example.com",
        "https://admin.example.com",
    ]


def test_cors_trims_whitespace_around_each_origin(monkeypatch):
    monkeypatch.setenv(
        "REDDIAL_CORS_ORIGINS",
        "  https://a.example.com ,\thttps://b.example.com\t",
    )
    origins = _cors_origins_after_reload()
    assert origins == ["https://a.example.com", "https://b.example.com"]


def test_cors_drops_empty_segments_but_keeps_real_ones(monkeypatch):
    # Trailing/duplicate commas produce empty segments that must be dropped,
    # not turned into "" origins (which would be an allowlist hole).
    monkeypatch.setenv(
        "REDDIAL_CORS_ORIGINS",
        "https://only.example.com,,  ,",
    )
    origins = _cors_origins_after_reload()
    assert origins == ["https://only.example.com"]
    assert "" not in origins
