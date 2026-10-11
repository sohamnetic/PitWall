from fastapi.testclient import TestClient
from typer.testing import CliRunner

from f1p.api.main import app as api
from f1p.config import regulation_era
from f1p.pipeline.cli import app as cli


def test_health():
    resp = TestClient(api).get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_cli_help():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "train", "predict", "score", "backtest"):
        assert cmd in result.output


def test_regulation_era():
    assert regulation_era(2014) == "hybrid-v1"
    assert regulation_era(2021) == "hybrid-wide"
    assert regulation_era(2025) == "ground-effect"
    assert regulation_era(2026) == "active-aero"
