import json
from pathlib import Path

import pytest

from workstation.cli import main


def test_cli_round_trip(tmp_path, capsys):
    source = Path(__file__).parents[1] / "examples" / "financials.csv"
    (tmp_path / "ws.toml").write_text(
        f'data_file = "{source.as_posix()}"\nmax_data_age_days = 36500\n'
    )

    def call(*args):
        main(["--root", str(tmp_path), "--mock", *args])
        return json.loads(capsys.readouterr().out)

    analyst = call("analyze", "DEMO")[0]["id"]
    risk = call("review", analyst)["id"]
    pm = call("propose", risk)["id"]
    for pid in (analyst, risk, pm):
        assert call("approve", pid)["status"] == "approved"
    assert call("execute", pm)["mode"] == "paper"
    assert len(call("status")["ledger"]) == 1
    assert call("halt")["halted"]


def test_cli_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--root", str(tmp_path), "execute", "unknown"])
    assert exc.value.code == 1
    assert "Unknown proposal" in capsys.readouterr().err
