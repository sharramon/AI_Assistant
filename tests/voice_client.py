"""A TestClient for the voice service that calls it as `127.0.0.1`, the way its real clients do.

Starlette's TestClient sends `Host: testserver`, which the service refuses (it serves this
machine only: app_kit.local_guard). Shared by test_voice_service.py and test_voice_pieces.py.
"""

from fastapi.testclient import TestClient

LOCAL = "http://127.0.0.1:8765"


class LocalClient(TestClient):
    def __init__(self, app, **kwargs) -> None:
        super().__init__(app, base_url=LOCAL, **kwargs)

    def websocket_connect(self, url: str, *args, **kwargs):
        if url.startswith("/"):
            url = "ws://127.0.0.1:8765" + url
        return super().websocket_connect(url, *args, **kwargs)
