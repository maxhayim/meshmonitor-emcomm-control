"""Issue #4: configurable exercise markers (standard TEST vs SET-safe)."""
import json
import re

import pytest

import mm_emcomm_control as control
import mm_emcomm_panel as panel
from conftest import send

TEST_WORD = re.compile(r"\btest\b", re.I)


@pytest.fixture
def set_safe(monkeypatch):
    monkeypatch.setitem(control.CONFIG, "exercise_style", "set-safe")


def texts(resp):
    return resp["responses"] if "responses" in resp else [resp["response"]]


def all_outputs(monkeypatch, capsys, messages, from_id="!f1"):
    out = []
    for message in messages:
        out += texts(send(monkeypatch, capsys, message, from_id=from_id))
    return out


# --- profile selection -------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("standard", "standard"), ("set-safe", "set-safe"), ("SET", "set-safe"), ("set_safe", "set-safe"),
    ("", "standard"), ("bogus", "standard"), (None, "standard"),
])
def test_style_resolution(raw, expected):
    assert control.exercise_style({"exercise_style": raw})["name"] == expected


def test_style_from_env_and_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MM_EMCOMM_EXERCISE_STYLE", raising=False)
    cfg_file = tmp_path / "c.json"
    cfg_file.write_text(json.dumps({"exercise_style": "set-safe"}), encoding="utf-8")
    assert control.exercise_style(control.load_config(cfg_file))["name"] == "set-safe"
    monkeypatch.setenv("MM_EMCOMM_EXERCISE_STYLE", "standard")
    assert control.exercise_style(control.load_config(cfg_file))["name"] == "standard"


# --- default behavior unchanged ------------------------------------------------

def test_default_standard_behavior_unchanged(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL")
    assert resp["response"] == "TEST ACK EX-001 TO EOC LOGGED. PREC TEST P. NOT A DELIVERY CONFIRMATION."
    assert control.find_traffic("EX-001")["exercise_marker"] == "TEST"
    control.handle_inject(6)
    assert json.loads(capsys.readouterr().out)["responses"][0].startswith("TEST EXERCISE INJECT 6")


# --- SET-safe formal traffic ----------------------------------------------------

@pytest.mark.parametrize("prec,expected", [("R", "SET R"), ("W", "SET W"), ("P", "SET P"), ("EMERGENCY", "SET EMERGENCY")])
def test_set_safe_precedence_stays_variable(set_safe, monkeypatch, capsys, prec, expected):
    resp = send(monkeypatch, capsys, f"EMCOMM TRAFFIC {prec} 2:MIKE 3:CHARLIE 4:WATER 7:EXERCISE REQUEST 20 CASES WATER")
    assert resp["response"] == f"EXERCISE ACK EX-001 TO MIKE LOGGED. PREC {expected}. NOT A DELIVERY CONFIRMATION."
    record = control.find_traffic("EX-001")
    assert record["precedence"] == ("EMERGENCY" if prec == "EMERGENCY" else prec)
    assert record["exercise_marker"] == "SET"
    assert record["test_traffic"] is True


def test_set_safe_requires_exercise_marker(set_safe, monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC R 2:MIKE 3:CHARLIE 4:WATER 7:REQUEST WATER")
    assert resp["response"].startswith("EXERCISE TRAFFIC REJECTED: FIELD 7 MUST BEGIN EXERCISE.")
    assert "7:EXERCISE TEXT" in resp["response"]
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC R 2:MIKE 3:CHARLIE 4:WATER 7:TEST MESSAGE REQUEST WATER")
    assert "MUST BEGIN EXERCISE" in resp["response"]  # TEST wording is not accepted in set-safe style
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC R 2:MIKE 3:CHARLIE 4:WATER 7:EXERCISES ARE FUN")
    assert "MUST BEGIN EXERCISE" in resp["response"]  # whole-word marker
    assert control.load_state()["traffic_count"] == 0


def test_set_safe_auto_prefix():
    t = control.parse_structured("R 2:MIKE 3:CHARLIE 4:WATER 7:REQUEST WATER")
    style = control.EXERCISE_STYLES["set-safe"]
    assert control.validate_formal(t, exercise=True, auto_prefix=True, style=style) == []
    assert t.fields["7"] == "EXERCISE REQUEST WATER"
    assert t.marker == "SET"


def test_set_safe_accepts_set_or_test_marker_on_input(set_safe, monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM TRAFFIC SET R 2:MIKE 3:CHARLIE 4:WATER 7:EXERCISE A")
    send(monkeypatch, capsys, "EMCOMM TRAFFIC TEST R 2:MIKE 3:CHARLIE 4:WATER 7:EXERCISE B")
    assert control.find_traffic("EX-001")["exercise_marker"] == "SET"
    assert control.find_traffic("EX-002")["exercise_marker"] == "SET"  # output follows the active style


def test_set_safe_relay_format_matches_issue(set_safe, monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM TRAFFIC R 2:MIKE 3:CHARLIE 4:WATER 7:EXERCISE REQUEST 20 CASES WATER")
    out = texts(send(monkeypatch, capsys, "EMCOMM RELAY EX-001", from_id="!rpt"))
    assert out[0].startswith("EXERCISE RELAY EX-001 #1 LOGGED")
    assert out[1] == "SET R | EX-001 | 2:MIKE | 3:CHARLIE | 4:WATER | 7:EXERCISE REQUEST 20 CASES WATER"


def test_set_safe_multipart_compose_and_reassembly(set_safe, monkeypatch, capsys):
    t = control.FormalTraffic(precedence="W", fields={
        "2": "SHELTER MANAGER", "3": "WELFARE DESK", "4": "FAMILY INQUIRY",
        "7": "EXERCISE INQUIRY FOR RESIDENTS OF 100 BLOCK ELM STREET PLEASE CONFIRM ALL FOUR "
             "FAMILY MEMBERS SAFE AND WHERE THEY ARE CURRENTLY SHELTERED REPLY VIA NET CONTROL",
    })
    assert control.validate_formal(t, exercise=True) == []
    commands = control.compose_traffic_command(t)
    assert len(commands) > 1
    assert commands[0].startswith(f"EMCOMM TRAFFIC 1/{len(commands)} SET W ")
    for cmd in commands:
        assert len(cmd) <= control.MAX_LEN and not TEST_WORD.search(cmd)
        resp = send(monkeypatch, capsys, cmd)
    assert resp["response"].startswith("EXERCISE ACK EX-001")
    parts = control.serialize_traffic(t, "EX-001")
    assert parts[0].startswith("SET W | EX-001 1/")
    _, rebuilt = control.reassemble_serialized(parts)
    assert rebuilt.fields == t.fields and rebuilt.marker == "SET"


def test_relayed_set_line_does_not_trigger_help(set_safe, monkeypatch, capsys):
    # 'SET R | EX-001 | ...' matches the ^SET Auto Responder rule; it must be ignored silently.
    monkeypatch.setenv("MESSAGE", "SET R | EX-001 | 2:MIKE | 3:CHARLIE | 4:WATER | 7:EXERCISE REQUEST")
    monkeypatch.setenv("FROM_ID", "!other")
    control.handle_message()
    assert capsys.readouterr().out == ""
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    control.handle_message()
    assert capsys.readouterr().out == ""


# --- no TEST anywhere in SET-safe exercise output -------------------------------

def test_set_safe_emits_no_test_word_anywhere(set_safe, monkeypatch, capsys):
    out = all_outputs(monkeypatch, capsys, [
        "EMCOMM HELP",
        "SET HELP",
        "EMCOMM CHECKIN W4ABC SHELTER1 BATTERY OPS",
        "EMCOMM SITREP SHELTER1 POWER OUT",
        "EMCOMM STATUS",
        "EMCOMM TRAFFIC R 2:MIKE 3:CHARLIE 4:WATER 7:EXERCISE REQUEST 20 CASES WATER",
        "EMCOMM TRAFFIC R 2:MIKE 3:CHARLIE 4:WATER 7:REQUEST WATER",          # rejection
        "EMCOMM TRAFFIC",                                                     # usage
        "EMCOMM TRAFFIC 1/2 P 2:EOC 3:A 4:B 7:EXERCISE PART ONE",
        "EMCOMM TRAFFIC 2/2 7:PART TWO",
        "EMCOMM TRAFFIC 2/3 7:ORPHAN",
        "EMCOMM TRAFFIC EOC IMMEDIATE legacy request",                          # legacy syntax
        "EMCOMM TRAFFIC R RE:EX-001 2:CHARLIE 3:MIKE 4:WATER 7:EXERCISE APPROVED",
        "EMCOMM RELAY EX-001 VIA HILL",
        "EMCOMM RCVD EX-001",
        "EMCOMM TRACK EX-001",
        "EMCOMM CHECKOUT W4ABC",
    ])
    for n in range(1, 9):
        control.handle_inject(n)
        out += texts(json.loads(capsys.readouterr().out))
    control.handle_announce("NCS requests check-ins")
    out += texts(json.loads(capsys.readouterr().out))
    offenders = [t for t in out if TEST_WORD.search(t)]
    assert offenders == []
    assert all(len(t) <= control.MAX_LEN for t in out)
    injects = control.exercise_injects()
    assert all(msgs[0].startswith(f"EXERCISE INJECT {n}") for n, msgs in injects.items())
    assert "FIELD 7 MUST BEGIN EXERCISE" in " ".join(injects[6])
    assert "SIMULATED" in injects[1][0]


def test_set_safe_help_text(set_safe, monkeypatch, capsys):
    out = texts(send(monkeypatch, capsys, "EMCOMM HELP"))
    assert out[1].startswith("FORMAL: EMCOMM TRAFFIC R 2:EOC 3:FIELD1 4:STATUS 7:EXERCISE COMMS OPERATIONAL")
    assert out[2].startswith("EXERCISE: FIELD 7 MUST BEGIN EXERCISE.")


# --- LIVE mode unaffected -------------------------------------------------------

@pytest.mark.parametrize("style", ["standard", "set-safe"])
def test_live_mode_unaffected_by_style(monkeypatch, capsys, style):
    monkeypatch.setitem(control.CONFIG, "exercise_style", style)
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:COMMS OPERATIONAL")
    assert resp["response"] == "LIVE ACK EC-001 TO EOC LOGGED. PREC P. NOT A DELIVERY CONFIRMATION."
    record = control.find_traffic("EC-001")
    assert record["exercise_marker"] == "" and record["field_7_message"] == "COMMS OPERATIONAL"
    out = texts(send(monkeypatch, capsys, "EMCOMM RELAY EC-001"))
    assert out[1] == "P | EC-001 | 2:EOC | 3:FIELD1 | 4:STATUS | 7:COMMS OPERATIONAL"
    help_out = " ".join(texts(send(monkeypatch, capsys, "EMCOMM HELP")))
    assert "EXERCISE" not in help_out and not TEST_WORD.search(help_out)


def test_switching_style_keeps_historic_marker(monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 3:F 4:S 7:TEST MESSAGE OLD")
    monkeypatch.setitem(control.CONFIG, "exercise_style", "set-safe")
    out = texts(send(monkeypatch, capsys, "EMCOMM RELAY EX-001"))
    assert out[1].startswith("TEST P | EX-001")  # recorded marker preserved; content never rewritten


# --- panel ----------------------------------------------------------------------

def test_panel_compose_set_safe(set_safe):
    form = {"precedence": "W", "to": "MIKE", "from": "CHARLIE", "subject": "WATER", "message": "EXERCISE REQUEST WATER"}
    result = panel.compose_from_form(form, "exercise")
    assert result["errors"] == []
    assert result["commands"][0]["text"] == "EMCOMM TRAFFIC SET W 2:MIKE 3:CHARLIE 4:WATER 7:EXERCISE REQUEST WATER"
    bad = panel.compose_from_form(dict(form, message="TEST MESSAGE REQUEST"), "exercise")
    assert any("MUST BEGIN EXERCISE" in e for e in bad["errors"])


def test_panel_page_set_safe(set_safe):
    server, thread, port = _run_server()
    try:
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        body = conn.getresponse().read().decode("utf-8")
        assert "EXERCISE / SET-SAFE MODE" in body
        assert "Field 7 must begin EXERCISE" in body
        assert 'data-marker="SET"' in body
        assert "set-safe style" in body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _run_server():
    import threading
    from test_panel import _free_port
    port = _free_port()
    server = panel.PanelServer(("127.0.0.1", port), panel.Handler, token="")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port
