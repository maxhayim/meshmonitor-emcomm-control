import json

import mm_emcomm_control as control
from conftest import send


def test_default_mode_is_exercise():
    state = control.load_state()
    assert state["mode"] == "exercise"


def test_checkin_updates_roster(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC MIAMI-EOC BATTERY NCS")
    assert "CHECKIN W4ABC" in resp["response"]
    state = control.load_state()
    assert state["participants"]["W4ABC"]["location"] == "MIAMI-EOC"
    assert state["participants"]["W4ABC"]["power"] == "BATTERY"
    assert state["participants"]["W4ABC"]["role"] == "NCS"


def test_checkin_bad_format_does_not_touch_roster(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC")
    assert "format" in resp["response"].lower()
    state = control.load_state()
    assert state["participants"] == {}


def test_checkout_removes_participant(monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC MIAMI-EOC BATTERY NCS")
    resp = send(monkeypatch, capsys, "EMCOMM CHECKOUT W4ABC")
    assert "removed from roster" in resp["response"].lower()
    state = control.load_state()
    assert "W4ABC" not in state["participants"]


def test_checkout_unknown_callsign(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM CHECKOUT GHOST")
    assert "not on roster" in resp["response"].lower()


def test_checkout_participant_cli(capsys):
    control.set_mode("exercise")
    capsys.readouterr()
    state = control.load_state()
    state["participants"]["W4ABC"] = {"node": "N1", "location": "EOC", "power": "AC", "role": "OPS", "time": "t"}
    control.save_state(state)
    control.checkout_participant("w4abc")
    resp = json.loads(capsys.readouterr().out.strip())
    assert "removed from roster" in resp["response"].lower()
    assert "W4ABC" not in control.load_state()["participants"]


def test_sitrep_increments_counter(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM SITREP MIAMI-EOC ALL CLEAR")
    assert "SITREP #1" in resp["response"]
    state = control.load_state()
    assert state["sitreps"] == 1


def test_traffic_defaults_to_routine_precedence(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC EOC Need more water at shelter 3")
    assert "[ROUTINE]" in resp["response"]
    state = control.load_state()
    assert state["traffic_count"] == 1


def test_traffic_explicit_precedence(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC EOC IMMEDIATE Shelter roof collapse")
    assert "[IMMEDIATE]" in resp["response"]


def test_traffic_precedence_word_not_confused_with_body(monkeypatch, capsys):
    # "Routine" appearing as the first word of an ordinary message is treated as precedence,
    # by design: precedence is always the optional token immediately after <TO>.
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC EOC PRIORITY Generator fuel low")
    assert "[PRIORITY]" in resp["response"]


def test_set_prefix_blocked_in_live(monkeypatch, capsys):
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    resp = send(monkeypatch, capsys, "SET INJECT 1")
    assert "disabled" in resp["response"].lower()


def test_injects_blocked_in_live(capsys):
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    control.handle_inject(1)
    resp = json.loads(capsys.readouterr().out.strip())
    assert "blocked" in resp["response"].lower()
    state = control.load_state()
    assert state["last_inject"] == 0


def test_live_mode_requires_confirm_flag(capsys):
    control.set_mode("live", confirm_live=False)
    resp = json.loads(capsys.readouterr().out.strip())
    assert "not enabled" in resp["response"].lower()
    assert control.load_state()["mode"] == "exercise"


def test_reset_preserves_mode_but_clears_counters(monkeypatch, capsys):
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC MIAMI-EOC BATTERY NCS")
    control.reset_operation()
    capsys.readouterr()
    state = control.load_state()
    assert state["mode"] == "live"
    assert state["participants"] == {}
    assert state["events"] == 0


def test_export_bundle_creates_expected_files(monkeypatch, capsys, tmp_path):
    send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC MIAMI-EOC BATTERY NCS")
    send(monkeypatch, capsys, "EMCOMM SITREP MIAMI-EOC ALL CLEAR")
    send(monkeypatch, capsys, "EMCOMM TRAFFIC EOC PRIORITY Generator fuel low")

    out_dir = tmp_path / "export"
    result = control.export_bundle(str(out_dir))

    roster_text = (result / "roster.csv").read_text(encoding="utf-8")
    traffic_text = (result / "traffic_log.csv").read_text(encoding="utf-8")
    summary_text = (result / "summary.txt").read_text(encoding="utf-8")

    assert "W4ABC" in roster_text
    assert "MIAMI-EOC" in roster_text
    assert "PRIORITY" in traffic_text
    assert "sitrep" in traffic_text
    assert "Stations checked in: 1" in summary_text
    assert "SITREPs: 1" in summary_text
    assert "Traffic records: 1" in summary_text
