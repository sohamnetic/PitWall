"""Production server: API mounted under /api, SPA fallback, safe static file serving."""

from fastapi.testclient import TestClient

from f1p.api.server import create_app


def _site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>app</html>")
    (tmp_path / "assets" / "app-123.js").write_text("console.log(1)")
    (tmp_path / "sw.js").write_text("// sw")
    (tmp_path.parent / "secret.txt").write_text("do not serve")
    return TestClient(create_app(tmp_path))


def test_api_is_mounted_under_api(tmp_path):
    client = _site(tmp_path)
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/docs").status_code == 200


def test_static_files_and_cache_headers(tmp_path):
    client = _site(tmp_path)
    asset = client.get("/assets/app-123.js")
    assert asset.text == "console.log(1)" and "immutable" in asset.headers["cache-control"]
    sw = client.get("/sw.js")
    assert sw.text == "// sw" and sw.headers["cache-control"] == "no-cache"


def test_unknown_paths_fall_back_to_the_app(tmp_path):
    client = _site(tmp_path)
    for path in ("/", "/races/2026-17", "/play"):
        r = client.get(path)
        assert r.status_code == 200 and r.text == "<html>app</html>"


def test_no_path_traversal(tmp_path):
    client = _site(tmp_path)
    r = client.get("/..%2Fsecret.txt")
    assert "do not serve" not in r.text
    r = client.get("/assets/../../secret.txt")
    assert "do not serve" not in r.text


def test_missing_build_gives_clear_message(tmp_path):
    client = TestClient(create_app(tmp_path / "nope"))
    r = client.get("/")
    assert r.status_code == 503 and "npm" in r.text
