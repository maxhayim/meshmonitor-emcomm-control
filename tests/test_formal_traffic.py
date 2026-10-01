import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import mm_emcomm_control as control
from conftest import send

REPO_ROOT = Path(__file__).resolve().parents[1]
STRUCTURED = "EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL"


def go_live(capsys):
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()


def response_texts(resp):
    return resp["responses"] if "responses" in resp else [resp["response"]]


# --- parsing --------------------------------------------------------------

def test_parse_required_fields():
    t = control.parse_structured("P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL")
    assert t.precedence == "P"
    assert t.fields == {"2": "EOC", "3": "FIELD1", "4": "STATUS", "7": "TEST MESSAGE COMMS OPERATIONAL"}


def test_parse_optional_fields_and_field8_after_message():
    t = control.parse_structured(
        "P 1:SET 2:EOC 3:SHELTER1 4:WATER 5:10/03/26 6:0930 7:TEST MESSAGE REQUEST 20 CASES WATER 8:OPERATOR1"
    )
    assert t.fields["1"] == "SET"
    assert t.fields["5"] == "10/03/26"
    assert t.fields["6"] == "0930"
    assert t.fields["7"] == "TEST MESSAGE REQUEST 20 CASES WATER"
    assert t.fields["8"] == "OPERATOR1"


def test_field7_may_contain_marker_like_text():
    t = control.parse_structured("R 2:EOC 3:F1 4:MEET 7:TEST MESSAGE RATIO 1:2 MEET AT 2:30 OR 8:00")
    assert t.fields["7"] == "TEST MESSAGE RATIO 1:2 MEET AT 2:30 OR 8:00"
    assert "8" not in t.fields


def test_field_content_case_preserved():
    t = control.parse_structured("R 2:Eoc Planning 3:Field 1 4:Status 7:TEST MESSAGE all good")
    assert t.fields["2"] == "Eoc Planning"
    assert t.fields["7"] == "TEST MESSAGE all good"


def test_duplicate_field_rejected():
    with pytest.raises(control.TrafficError):
        control.parse_structured("R 2:EOC 2:OPS 3:F 4:S 7:TEST MESSAGE X")


def test_text_before_first_field_rejected():
    with pytest.raises(control.TrafficError):
        control.parse_structured("R EOC 2:EOC 3:F 4:S 7:TEST MESSAGE X")


@pytest.mark.parametrize("token,expected", [
    ("R", "R"), ("ROUTINE", "R"), ("p", "P"), ("PRIORITY", "P"),
    ("W", "W"), ("WELFARE", "W"), ("EMERGENCY", "EMERGENCY"),
])
def test_precedence_normalization(token, expected):
    t = control.parse_structured(f"{token} 2:EOC 3:F 4:S 7:TEST MESSAGE X")
    assert t.precedence == expected


@pytest.mark.parametrize("token", ["E", "IMMEDIATE", "URGENT", "FLASH"])
def test_non_nts_precedence_rejected_in_structured_form(token):
    with pytest.raises(control.TrafficError):
        control.parse_traffic_header([token])


def test_structured_vs_legacy_detection():
    assert control.is_structured_traffic("P 2:EOC 3:F 4:S 7:X")
    assert control.is_structured_traffic("TEST P 2:EOC")
    assert control.is_structured_traffic("1/2 P 2:EOC")
    assert not control.is_structured_traffic("EOC MEET AT 2:30")
    assert not control.is_structured_traffic("EOC PRIORITY Generator low")


# --- validation & TEST marking -------------------------------------------

def test_required_field_validation(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 4:STATUS 7:TEST MESSAGE X")
    assert "REJECTED" in resp["response"]
    assert "3:FROM" in resp["response"]
    assert control.load_state()["traffic_count"] == 0


def test_exercise_requires_test_message(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:COMMS OPERATIONAL")
    assert resp["response"].startswith("TEST TRAFFIC REJECTED")
    assert "FIELD 7 MUST BEGIN TEST MESSAGE" in resp["response"]
    assert control.load_state()["traffic_count"] == 0


def test_exercise_auto_prefix_mode():
    t = control.parse_structured("P 2:EOC 3:F 4:S 7:COMMS OPERATIONAL")
    assert control.validate_formal(t, exercise=True, auto_prefix=True) == []
    assert t.fields["7"] == "TEST MESSAGE COMMS OPERATIONAL"
    assert t.test_traffic is True


def test_live_never_auto_prefixes():
    t = control.parse_structured("P 2:EOC 3:F 4:S 7:COMMS OPERATIONAL")
    assert control.validate_formal(t, exercise=False, auto_prefix=True) == []
    assert t.fields["7"] == "COMMS OPERATIONAL"
    assert t.test_traffic is False


def test_exercise_structured_ack_uses_test_precedence(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, STRUCTURED)
    text = resp["response"]
    assert text.startswith("TEST ACK EX-001 TO EOC LOGGED")
    assert "PREC TEST P" in text
    assert "NOT A DELIVERY CONFIRMATION" in text
    assert "DELIVERED" not in text.replace("NOT A DELIVERY", "")


def test_live_traffic_has_no_test_marking(monkeypatch, capsys):
    go_live(capsys)
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:COMMS OPERATIONAL")
    text = resp["response"]
    assert text.startswith("LIVE ACK EC-001 TO EOC LOGGED")
    assert "TEST" not in text
    record = control.find_traffic("EC-001")
    assert record["test_traffic"] is False
    assert record["field_7_message"] == "COMMS OPERATIONAL"
    assert control.serialize_traffic(control.traffic_from_record(record), "EC-001")[0].startswith("P | EC-001")


def test_test_emergency_rendering():
    t = control.parse_structured("EMERGENCY 2:EOC 3:F 4:S 7:TEST MESSAGE X")
    control.validate_formal(t, exercise=True)
    assert control.serialize_traffic(t, "EX-009")[0].startswith("TEST EMERGENCY | EX-009")


# --- structured logging / export -----------------------------------------

def test_structured_log_record(monkeypatch, capsys):
    send(monkeypatch, capsys,
         "EMCOMM TRAFFIC P 1:SET 2:EOC 3:SHELTER1 4:WATER 5:10/03/26 6:0930 "
         "7:TEST MESSAGE REQUEST 20 CASES WATER 8:OPERATOR1", from_id="!abcd")
    record = control.find_traffic("EX-001")
    expected = {
        "traffic_id": "EX-001", "mode": "exercise", "precedence": "P", "test_traffic": True,
        "field_1_incident": "SET", "field_2_to": "EOC", "field_3_from": "SHELTER1",
        "field_4_subject": "WATER", "field_5_date": "10/03/26", "field_6_time": "0930",
        "field_7_message": "TEST MESSAGE REQUEST 20 CASES WATER", "field_8_approved_by": "OPERATOR1",
        "reply_to": "", "from_node": "!abcd", "syntax": "ics213",
    }
    for key, value in expected.items():
        assert record[key] == value, key
    assert record["received_time"]
    assert record["raw_input"].startswith("TRAFFIC P 1:SET")


def test_csv_export_includes_formal_fields(monkeypatch, capsys, tmp_path):
    send(monkeypatch, capsys, STRUCTURED)
    send(monkeypatch, capsys, "EMCOMM RELAY EX-001")
    out = control.export_bundle(str(tmp_path / "export"))
    with (out / "formal_traffic.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["traffic_id"] == "EX-001"
    assert rows[0]["field_4_subject"] == "STATUS"
    assert rows[0]["test_traffic"] == "True"
    assert rows[0]["relay_count"] == "1"
    header = (out / "traffic_log.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    for col in ("field_2_to", "field_7_message", "reply_to", "relayed_by", "to", "body"):
        assert col in header
    summary = (out / "summary.txt").read_text(encoding="utf-8")
    assert "not NTS message numbers" in summary


def test_legacy_log_records_upgraded_on_read(tmp_path):
    control.DATA_DIR.mkdir(parents=True, exist_ok=True)
    old = {
        "time": "2026-09-09T10:00:00-04:00", "mode": "exercise", "kind": "traffic",
        "from_node": "N1", "message": "TRAFFIC EOC IMMEDIATE Roof", "traffic_id": "EX-001",
        "to": "EOC", "precedence": "IMMEDIATE", "body": "Roof",
    }
    control.LOG_FILE.write_text(json.dumps(old) + "\n", encoding="utf-8")
    record = control.read_log_records()[0]
    assert record["field_2_to"] == "EOC"
    assert record["field_7_message"] == "Roof"
    assert record["precedence"] == "P"
    assert record["legacy_precedence"] == "IMMEDIATE"
    assert record["syntax"] == "legacy"
    # on-disk record is untouched
    assert json.loads(control.LOG_FILE.read_text(encoding="utf-8")) == old
    out = control.export_bundle(str(tmp_path / "x"))
    assert "Roof" in (out / "formal_traffic.csv").read_text(encoding="utf-8")


def test_old_state_without_new_keys_loads():
    control.DATA_DIR.mkdir(parents=True, exist_ok=True)
    control.STATE_FILE.write_text(json.dumps({"schema": 2, "mode": "live", "traffic_count": 4}), encoding="utf-8")
    state = control.load_state()
    assert state["mode"] == "live"
    assert state["traffic_count"] == 4
    assert state["pending_traffic"] == {}
    assert state["relays"] == 0


# --- replies & relays ----------------------------------------------------

def test_reply_is_new_message_referencing_original(monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 3:SHELTER1 4:WATER 7:TEST MESSAGE REQUEST 20 CASES WATER")
    resp = send(monkeypatch, capsys,
                "EMCOMM TRAFFIC R RE:EX-001 2:SHELTER1 3:EOC 4:WATER 7:TEST MESSAGE REQUEST APPROVED")
    assert resp["response"].startswith("TEST ACK EX-002 RE:EX-001 TO SHELTER1")
    original = control.find_traffic("EX-001")
    reply = control.find_traffic("EX-002")
    assert original["field_7_message"] == "TEST MESSAGE REQUEST 20 CASES WATER"
    assert original["reply_to"] == ""
    assert reply["reply_to"] == "EX-001"
    assert reply["reply_found"] is True


def test_reply_to_unknown_id_is_flagged(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC R RE:EX-099 2:A 3:B 4:C 7:TEST MESSAGE X")
    assert "REF NOT IN LOG" in resp["response"]


def test_relay_preserves_original_fields(monkeypatch, capsys):
    send(monkeypatch, capsys, STRUCTURED, from_id="!orig")
    before = control.find_traffic("EX-001")
    resp = send(monkeypatch, capsys, "EMCOMM RELAY EX-001 VIA RPT1,RPT2", from_id="!relay")
    texts = response_texts(resp)
    assert texts[0].startswith("TEST RELAY EX-001 #1 LOGGED")
    assert texts[1] == "TEST P | EX-001 | 2:EOC | 3:FIELD1 | 4:STATUS | 7:TEST MESSAGE COMMS OPERATIONAL"
    after = control.find_traffic("EX-001")
    assert after == before
    relays = [r for r in control.read_log_records() if r["kind"] == "relay"]
    assert relays[0]["relayed_by"] == "!relay"
    assert relays[0]["relay_route"] == "RPT1,RPT2"
    assert relays[0]["relay_count"] == 1
    send(monkeypatch, capsys, "EMCOMM RELAY EX-001", from_id="!relay2")
    assert [r for r in control.read_log_records() if r["kind"] == "relay"][1]["relay_count"] == 2


def test_relay_unknown_id(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM RELAY EX-404")
    assert "NOT IN LOG" in resp["response"]


# --- multipart -----------------------------------------------------------

LONG_MESSAGE = (
    "TEST MESSAGE SHELTER 1 REQUESTS 40 COTS 80 BLANKETS 20 CASES WATER AND 2 GENERATORS "
    "DELIVER TO NORTH ENTRANCE BEFORE 1600 CONTACT SHELTER MANAGER ON ARRIVAL"
)


def long_traffic():
    t = control.FormalTraffic(precedence="P", fields={
        "1": "SET", "2": "EOC LOGISTICS", "3": "SHELTER1 MANAGER", "4": "SUPPLY REQUEST",
        "7": LONG_MESSAGE, "8": "OPERATOR1",
    })
    control.validate_formal(t, exercise=True)
    return t


def test_serialize_multipart_roundtrip():
    t = long_traffic()
    parts = control.serialize_traffic(t, "EX-003")
    assert len(parts) > 1
    assert all(len(p) <= control.MAX_LEN for p in parts)
    assert parts[0].startswith(f"TEST P | EX-003 1/{len(parts)} |")
    for i, part in enumerate(parts[1:], 2):
        assert part.startswith(f"EX-003 {i}/{len(parts)} |")
    traffic_id, rebuilt = control.reassemble_serialized(parts)
    assert traffic_id == "EX-003"
    assert rebuilt.fields == t.fields
    assert rebuilt.precedence == "P" and rebuilt.test_traffic


def test_reassemble_rejects_mismatched_parts():
    parts = control.serialize_traffic(long_traffic(), "EX-003")
    bad = [parts[0], parts[1].replace("EX-003", "EX-004")] + parts[2:]
    with pytest.raises(control.TrafficError):
        control.reassemble_serialized(bad)
    with pytest.raises(control.TrafficError):
        control.reassemble_serialized(parts[:1])


@pytest.mark.parametrize("limit", [80, 100, 133, 200])
def test_compose_command_parts_fit_limit_and_are_accepted(monkeypatch, capsys, limit):
    t = long_traffic()
    commands = control.compose_traffic_command(t, limit=limit)
    assert all(len(c) <= limit for c in commands)
    if len(commands) > 1:
        assert commands[0].startswith(f"EMCOMM TRAFFIC 1/{len(commands)} TEST P ")
    for cmd in commands:
        resp = send(monkeypatch, capsys, cmd, from_id="!multi")
    assert resp["response"].startswith("TEST ACK EX-001")
    record = control.find_traffic("EX-001")
    assert record["field_7_message"] == LONG_MESSAGE
    assert record["field_8_approved_by"] == "OPERATOR1"
    assert record["parts"] == len(commands)


def test_inbound_multipart_out_of_order_rejected(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC 2/2 7:MORE TEXT")
    assert "WITHOUT PART 1/2" in resp["response"]
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC 1/2 P 2:EOC 3:F 4:S 7:TEST MESSAGE PART ONE")
    assert "AWAITING 2/2" in resp["response"]
    assert control.load_state()["traffic_count"] == 0


def test_inbound_multipart_is_per_sender(monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM TRAFFIC 1/2 P 2:EOC 3:F 4:S 7:TEST MESSAGE A", from_id="!one")
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC 2/2 7:B", from_id="!two")
    assert "WITHOUT PART 1/2" in resp["response"]
    resp = send(monkeypatch, capsys, "EMCOMM TRAFFIC 2/2 7:B", from_id="!one")
    assert resp["response"].startswith("TEST ACK EX-001")
    assert control.find_traffic("EX-001")["field_7_message"] == "TEST MESSAGE A B"


# --- message length ------------------------------------------------------

def test_default_max_len_is_133():
    assert control.DEFAULT_MAX_LEN == 133
    assert control.DEFAULT_RECOMMENDED_LEN == 120


def _import_max_len(env_value):
    env = dict(os.environ)
    env.pop("MM_EMCOMM_MAXLEN", None)
    if env_value is not None:
        env["MM_EMCOMM_MAXLEN"] = env_value
    out = subprocess.run(
        [sys.executable, "-c", "import mm_emcomm_control as c; print(c.MAX_LEN)"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=True,
    )
    return int(out.stdout.strip())


def test_max_len_env_override():
    assert _import_max_len(None) == 133
    assert _import_max_len("200") == 200
    assert _import_max_len("garbage") == 133
    assert _import_max_len("10") == 133  # below the safe minimum falls back to default


def test_length_report_warning_logic():
    assert control.length_report("x" * 104)["warning"] == ""
    rep = control.length_report("x" * 121)
    assert rep["over_recommended"] and rep["warning"] == "Recommended LoRa target exceeded."
    rep = control.length_report("x" * 134)
    assert rep["over_limit"] and not rep["over_recommended"]
    # a custom higher limit is honored, not blocked
    rep = control.length_report("x" * 180, limit=200)
    assert not rep["over_limit"] and rep["over_recommended"]


def test_split_message_numbers_parts():
    parts = control.split_message("word " * 60)
    assert len(parts) > 1
    assert all(len(p) <= control.MAX_LEN for p in parts)
    assert parts[0].endswith(f"[1/{len(parts)}]")


# --- help, injects, generic configuration --------------------------------

def test_help_separates_tactical_and_formal(monkeypatch, capsys):
    resp = send(monkeypatch, capsys, "EMCOMM HELP")
    texts = response_texts(resp)
    assert texts[0].startswith("EXERCISE TACTICAL:")
    assert any(t.startswith("FORMAL: EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE") for t in texts)
    assert any("FIELD 7 MUST BEGIN TEST MESSAGE" for t in texts)
    assert all(len(t) <= control.MAX_LEN for t in texts)
    assert len(texts) <= 4


def test_live_help_has_no_test_marking(monkeypatch, capsys):
    go_live(capsys)
    texts = response_texts(send(monkeypatch, capsys, "EMCOMM HELP"))
    assert texts[0].startswith("LIVE TACTICAL:")
    assert not any("TEST" in t for t in texts)


def test_inject6_starts_formal_phase(capsys):
    control.handle_inject(6)
    texts = response_texts(json.loads(capsys.readouterr().out))
    assert texts[0].startswith("TEST EXERCISE INJECT 6 - FORMAL TRAFFIC PHASE")
    joined = " ".join(texts)
    assert "ICS-213 / NTS-STYLE" in joined
    assert "FIELDS 2, 3, 4 AND 7" in joined
    assert "FIELD 7 MUST BEGIN TEST MESSAGE" in joined
    assert all(len(t) <= control.MAX_LEN for t in texts)


def test_all_injects_identify_as_test_and_fit_limit():
    for number, messages in control.EXERCISE_INJECTS.items():
        assert messages[0].startswith(f"TEST EXERCISE INJECT {number}")
        for message in messages:
            assert len(message) <= control.MAX_LEN, (number, message)
            assert message.isascii()


def test_tactical_commands_unchanged(monkeypatch, capsys):
    assert send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC EOC AC NCS")["response"].startswith("EXERCISE ACK CHECKIN W4ABC")
    assert send(monkeypatch, capsys, "EMCOMM SITREP EOC ALL GOOD")["response"].startswith("EXERCISE ACK SITREP #1")
    assert send(monkeypatch, capsys, "EMCOMM STATUS")["response"].startswith("EXERCISE STATUS")
    assert send(monkeypatch, capsys, "SET CHECKOUT W4ABC")["response"].startswith("EXERCISE CHECKOUT W4ABC")
    assert control.load_state()["traffic_count"] == 0


def test_generic_config_file_and_env(tmp_path, monkeypatch):
    cfg_file = tmp_path / "cfg.json"
    cfg_file.write_text(json.dumps({
        "exercise_name": "County Hurricane Drill", "organization": "Example ARES",
        "incident_name": "HURREX", "start": "2027-05-01T09:00", "unknown_key": "ignored",
    }), encoding="utf-8")
    monkeypatch.delenv("MM_EMCOMM_EXERCISE_NAME", raising=False)
    monkeypatch.delenv("SET_NAME", raising=False)
    monkeypatch.setenv("MM_EMCOMM_ORGANIZATION", "Env Override Club")
    cfg = control.load_config(cfg_file)
    assert cfg["exercise_name"] == "County Hurricane Drill"
    assert cfg["organization"] == "Env Override Club"
    assert cfg["incident_name"] == "HURREX"
    assert "unknown_key" not in cfg
    injects = control.exercise_injects(cfg)
    assert "COUNTY HURRICANE DRILL" in injects[1][0]


def test_default_config_is_generic(tmp_path, monkeypatch):
    for names in control.CONFIG_ENV.values():
        for name in names:
            monkeypatch.delenv(name, raising=False)
    cfg = control.load_config(tmp_path / "missing.json")
    assert cfg["exercise_name"] == "Emergency Communications Exercise"
    assert all(v == "" for k, v in cfg.items() if k != "exercise_name")


def test_no_hard_coded_example_deployment_in_code():
    banned = ["south dade", "gmrs", "october 3", "10/03/26", "2026-10-03", "910.525", "mediumfast"]
    for name in ("mm_emcomm_control.py", "mm_emcomm_panel.py"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8").lower()
        for word in banned:
            assert word not in text, (name, word)
