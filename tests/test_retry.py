import asyncio
import io
import urllib.error

import aiohttp
import pytest

from repligit import retry
from repligit.asyncio import retry as async_retry
from repligit.exceptions import RemoteError


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO())  # type: ignore[arg-type]


def _client_error(status: int) -> aiohttp.ClientResponseError:
    return aiohttp.ClientResponseError(None, (), status=status)  # type: ignore[arg-type]


@pytest.fixture
def sleeps(monkeypatch):
    calls: list[float] = []
    monkeypatch.setattr(retry.time, "sleep", calls.append)

    async def fake_sleep(delay):
        calls.append(delay)

    monkeypatch.setattr(async_retry.asyncio, "sleep", fake_sleep)
    return calls


class _Flaky:
    def __init__(self, errors, result="ok"):
        self.errors = list(errors)
        self.result = result
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.result

    async def acall(self):
        return self()


def test_sync_retries_then_succeeds(sleeps):
    f = _Flaky([_http_error(503), urllib.error.URLError("down"), TimeoutError()])
    assert retry.retry_sync(f, 3, "t") == "ok"
    assert f.calls == 4
    assert sleeps == [1, 2, 4]


def test_sync_exhausts_retries_and_raises(sleeps):
    f = _Flaky([_http_error(502)] * 5)
    with pytest.raises(urllib.error.HTTPError):
        retry.retry_sync(f, 2, "t")
    assert f.calls == 3


def test_sync_zero_retries_disables(sleeps):
    f = _Flaky([_http_error(503)])
    with pytest.raises(urllib.error.HTTPError):
        retry.retry_sync(f, 0, "t")
    assert f.calls == 1
    assert sleeps == []


@pytest.mark.parametrize("exc", [_http_error(404), _http_error(401), RemoteError("x")])
def test_sync_does_not_retry_permanent_errors(sleeps, exc):
    f = _Flaky([exc])
    with pytest.raises(type(exc)):
        retry.retry_sync(f, 3, "t")
    assert f.calls == 1


def test_async_retries_then_succeeds(sleeps):
    f = _Flaky([_client_error(429), aiohttp.ServerDisconnectedError(), TimeoutError()])
    assert asyncio.run(async_retry.retry_async(f.acall, 3, "t")) == "ok"
    assert f.calls == 4
    assert sleeps == [1, 2, 4]


def test_async_exhausts_retries_and_raises(sleeps):
    f = _Flaky([_client_error(504)] * 5)
    with pytest.raises(aiohttp.ClientResponseError):
        asyncio.run(async_retry.retry_async(f.acall, 2, "t"))
    assert f.calls == 3


@pytest.mark.parametrize("exc", [_client_error(404), RemoteError("x")])
def test_async_does_not_retry_permanent_errors(sleeps, exc):
    f = _Flaky([exc])
    with pytest.raises(type(exc)):
        asyncio.run(async_retry.retry_async(f.acall, 3, "t"))
    assert f.calls == 1
