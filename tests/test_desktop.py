import json
import socket
import urllib.request

import desktop


def test_serve_responds():
    url = desktop.serve()
    assert url.startswith("http://127.0.0.1:")
    with urllib.request.urlopen(url + "/api/status", timeout=5) as r:
        assert "model" in json.load(r)


def test_serve_honours_port(monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv("SMART_EXPLORER_PORT", str(port))
    assert desktop.serve() == "http://127.0.0.1:%d" % port


def test_dropped_paths_uses_native_full_paths():
    event = {"type": "drop", "dataTransfer": {"files": [
        {"name": "Slides", "pywebviewFullPath": "/Users/me/Slides/"},
        {"name": "a.png", "pywebviewFullPath": "/Users/me/a.png"},
        {"name": "b.png"},  # dropped from a browser tab: no path
    ]}}
    assert desktop.dropped_paths(event) == ["/Users/me/Slides/", "/Users/me/a.png"]
    assert desktop.dropped_paths({"type": "drop"}) == []
