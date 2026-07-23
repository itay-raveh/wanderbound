from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from app.core.http import http_client

if TYPE_CHECKING:
    import pytest


async def test_post_retries_can_be_enabled_for_token_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ReadTimeout("temporary timeout", request=request)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(
        "app.core.http._TimeoutTransport",
        lambda _timeout, _limits: httpx.MockTransport(handler),
    )

    async with http_client(
        cache=False,
        retry_allowed_methods={"POST"},
    ) as client:
        response = await client.post("https://oauth2.googleapis.com/token")

    assert response.status_code == 200
    assert attempts == 3
