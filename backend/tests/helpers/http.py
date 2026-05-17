from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx

_DUMMY_REQUEST = httpx.Request("GET", "http://test")


def json_response(data: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code, content=json.dumps(data).encode(), request=_DUMMY_REQUEST
    )


def mock_response(content: bytes, status_code: int = 200) -> MagicMock:
    resp = MagicMock(status_code=status_code)
    resp.content = content
    return resp


def error_response(status: int = 500) -> MagicMock:
    resp = MagicMock(status_code=status)
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        f"{status}", request=MagicMock(), response=resp
    )
    return resp


def async_client(**methods: object) -> AsyncMock:
    client = AsyncMock()
    for method, response in methods.items():
        call = getattr(client, method)
        if isinstance(response, (BaseException, list)):
            call.side_effect = response
        else:
            call.return_value = response
    return client
