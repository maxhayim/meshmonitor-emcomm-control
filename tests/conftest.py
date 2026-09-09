import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import mm_emcomm_control as control  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Point the runtime's state/log files at a throwaway directory per test."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(control, "DATA_DIR", data_dir)
    monkeypatch.setattr(control, "STATE_FILE", data_dir / "state.json")
    monkeypatch.setattr(control, "LOG_FILE", data_dir / "traffic.jsonl")
    legacy_dir = tmp_path / "legacy"
    monkeypatch.setattr(control, "LEGACY_DIR", legacy_dir)
    monkeypatch.setattr(control, "LEGACY_STATE_FILE", legacy_dir / "state.json")
    monkeypatch.setattr(control, "LEGACY_LOG_FILE", legacy_dir / "traffic.jsonl")
    yield data_dir


def send(monkeypatch, capsys, message, from_id="N1"):
    """Simulate an inbound mesh message and return the parsed JSON response."""
    import json

    monkeypatch.setenv("MESSAGE", message)
    monkeypatch.setenv("FROM_ID", from_id)
    control.handle_message()
    out = capsys.readouterr().out.strip()
    return json.loads(out)
