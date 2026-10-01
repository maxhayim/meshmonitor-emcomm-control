import csv
import json

import pytest

import mm_emcomm_control as control
from conftest import send

TRAFFIC = "EMCOMM TRAFFIC P 2:EOC 3:SHELTER1 4:WATER 7:TEST MESSAGE REQUEST 20 CASES WATER"

MESHTASTIC_ENV = {
    "FROM_LONG_NAME": "Shelter One", "FROM_SHORT_NAME": "SH1", "SNR": "6.25", "RSSI": "-95",
    "HOPS": "2", "CHANNEL": "0", "IS_DIRECT": "false", "VIA_MQTT": "false", "PACKET_ID": "123",
}


@pytest.fixture(autouse=True)
def clean_rx_env(monkeypatch):
    for name in list(MESHTASTIC_ENV) + ["MESHCORE_SOURCE_ID", "FROM_NODE", "FROM_ID"]:
        monkeypatch.delenv(name, raising=False)


def texts(resp):
    return resp["responses"] if "responses" in resp else [resp["response"]]


def capture(monkeypatch, capsys, message, **env):
    monkeypatch.setenv("MESSAGE", message)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    control.handle_capture()
    return capsys.readouterr().out


# --- delivery receipts ------------------------------------------------------

def test_rcvd_confirms_delivery(monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM CHECKIN KN4EOC EOC AC NCS", from_id="!eoc")
    send(monkeypatch, capsys, TRAFFIC, from_id="!sh1")
    resp = send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="!eoc")
    assert resp["response"].startswith("TEST RCVD EX-001 DELIVERY CONFIRMED BY KN4EOC AT ")
    record = [r for r in control.read_log_records() if r["kind"] == "delivery"][0]
    assert record["traffic_id"] == "EX-001"
    assert record["delivered_by"] == "KN4EOC"
    assert record["self_confirmed"] is False
    assert control.load_state()["deliveries"] == 1
    # the original message is untouched
    assert control.find_traffic("EX-001")["field_7_message"] == "TEST MESSAGE REQUEST 20 CASES WATER"


def test_delivered_alias_and_unknown_id(monkeypatch, capsys):
    assert "NOT IN LOG" in send(monkeypatch, capsys, "EMCOMM RCVD EX-404")["response"]
    send(monkeypatch, capsys, TRAFFIC, from_id="!sh1")
    assert "DELIVERY CONFIRMED" in send(monkeypatch, capsys, "EMCOMM DELIVERED ex-001", from_id="!eoc")["response"]


def test_rcvd_by_originator_is_flagged(monkeypatch, capsys):
    send(monkeypatch, capsys, TRAFFIC, from_id="!sh1")
    resp = send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="!sh1")
    assert "SENT BY ORIGINATING NODE" in resp["response"]


def test_second_receipt_reports_first(monkeypatch, capsys):
    send(monkeypatch, capsys, TRAFFIC, from_id="!sh1")
    send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="!eoc")
    resp = send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="!ops")
    assert "FIRST CONFIRMED BY !eoc" in resp["response"]
    row = control.formal_traffic_rows()[0]
    assert row["delivered_by"] == "!eoc"
    assert row["receipt_count"] == 2


def test_live_rcvd_has_no_test_marking(monkeypatch, capsys):
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 3:F1 4:S 7:COMMS UP", from_id="!f1")
    resp = send(monkeypatch, capsys, "EMCOMM RCVD EC-001", from_id="!eoc")
    assert resp["response"].startswith("LIVE RCVD EC-001")
    assert "TEST" not in resp["response"]


def test_receipts_after_reset_do_not_attach_to_old_message(monkeypatch, capsys):
    send(monkeypatch, capsys, TRAFFIC, from_id="!sh1")
    send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="!eoc")
    control.reset_operation()
    capsys.readouterr()
    send(monkeypatch, capsys, TRAFFIC, from_id="!sh1")  # new EX-001
    original, relays, receipts = control.traffic_history("EX-001")
    assert receipts == []
    assert "DELIVERY NOT YET CONFIRMED" in send(monkeypatch, capsys, "EMCOMM TRACK EX-001")["response"]


# --- tracking ---------------------------------------------------------------

def test_track_reports_lifecycle(monkeypatch, capsys):
    send(monkeypatch, capsys, TRAFFIC, from_id="!sh1")
    resp = send(monkeypatch, capsys, "EMCOMM TRACK EX-001")
    assert resp["response"].startswith("TEST TRACK EX-001 PREC TEST P TO EOC: LOGGED ")
    assert "DELIVERY NOT YET CONFIRMED" in resp["response"]
    send(monkeypatch, capsys, "EMCOMM RELAY EX-001 VIA HILL", from_id="!rpt")
    send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="!eoc")
    text = " ".join(texts(send(monkeypatch, capsys, "EMCOMM TRACK EX-001")))
    assert "RELAYED 1X" in text
    assert "DELIVERED" in text and "BY !eoc" in text
    assert all(len(t) <= control.MAX_LEN for t in texts(send(monkeypatch, capsys, "EMCOMM TRACK EX-001")))


def test_formal_rows_status_progression(monkeypatch, capsys):
    send(monkeypatch, capsys, TRAFFIC, from_id="!sh1")
    assert control.formal_traffic_rows()[0]["status"] == "logged"
    send(monkeypatch, capsys, "EMCOMM RELAY EX-001", from_id="!rpt")
    assert control.formal_traffic_rows()[0]["status"] == "relayed"
    send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="!eoc")
    row = control.formal_traffic_rows()[0]
    assert row["status"] == "delivered"
    assert row["relay_count"] == 1
    assert row["delivery_minutes"] != ""


def test_help_lists_followup_commands_within_limit(monkeypatch, capsys):
    for mode in ("exercise", "live"):
        if mode == "live":
            control.set_mode("live", confirm_live=True)
            capsys.readouterr()
        out = texts(send(monkeypatch, capsys, "EMCOMM HELP"))
        assert any("RELAY/RCVD/TRACK <ID>" in t for t in out)
        assert all(len(t) <= control.MAX_LEN for t in out)


# --- receive metadata & station identity ------------------------------------

def test_receive_metadata_logged_with_commands(monkeypatch, capsys):
    for key, value in MESHTASTIC_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("FROM_NODE", "1001")
    send(monkeypatch, capsys, TRAFFIC, from_id="1001")
    record = control.find_traffic("EX-001")
    assert record["snr"] == "6.25"
    assert record["hops"] == "2"
    assert record["from_name"] == "Shelter One"
    assert record["network"] == "meshtastic"


def test_meshcore_channel_sender_identified_by_name(monkeypatch):
    monkeypatch.setenv("MESHCORE_SOURCE_ID", "mc1")
    monkeypatch.setenv("FROM_NODE", "synthetic-channel-id")
    monkeypatch.setenv("FROM_LONG_NAME", "Field Team 2")
    monkeypatch.setenv("IS_DIRECT", "false")
    assert control.sender_id() == "Field Team 2"
    monkeypatch.setenv("IS_DIRECT", "true")
    assert control.sender_id() == "synthetic-channel-id"


def test_meshcore_multipart_buffers_per_named_sender(monkeypatch, capsys):
    monkeypatch.setenv("MESHCORE_SOURCE_ID", "mc1")
    monkeypatch.setenv("IS_DIRECT", "false")
    monkeypatch.setenv("FROM_NODE", "synthetic")
    monkeypatch.setenv("MESSAGE", "EMCOMM TRAFFIC 1/2 P 2:EOC 3:A 4:S 7:TEST MESSAGE ONE")
    monkeypatch.setenv("FROM_LONG_NAME", "Alpha")
    control.handle_message()
    monkeypatch.setenv("MESSAGE", "EMCOMM TRAFFIC 2/2 7:TWO")
    monkeypatch.setenv("FROM_LONG_NAME", "Bravo")
    control.handle_message()
    assert "WITHOUT PART 1/2" in json.loads(capsys.readouterr().out.splitlines()[-1])["response"]


# --- silent capture -----------------------------------------------------------

def test_capture_is_silent_and_logged(monkeypatch, capsys):
    out = capture(monkeypatch, capsys, "anyone hear me on the north side?", FROM_NODE="3003", **MESHTASTIC_ENV)
    assert out == ""
    rows = control.captured_rows()
    assert rows[0]["message"] == "anyone hear me on the north side?"
    assert rows[0]["snr"] == "6.25"
    assert rows[0]["possible_echo"] is False
    assert control.load_state()["captured"] == 1
    assert control.load_state()["events"] == 0


def test_capture_skips_commands_on_meshcore(monkeypatch, capsys):
    out = capture(monkeypatch, capsys, "EMCOMM STATUS", MESHCORE_SOURCE_ID="mc1", FROM_LONG_NAME="Alpha")
    assert out == ""
    assert control.captured_rows() == []


def test_capture_processes_commands_on_meshtastic_if_rule_misordered(monkeypatch, capsys):
    out = capture(monkeypatch, capsys, "EMCOMM STATUS", FROM_NODE="3003")
    assert json.loads(out)["response"].startswith("EXERCISE STATUS")
    assert control.captured_rows() == []


def test_capture_flags_possible_system_echo(monkeypatch, capsys):
    capture(monkeypatch, capsys, "TEST ACK EX-001 TO EOC LOGGED. PREC TEST P.", MESHCORE_SOURCE_ID="mc1",
            FROM_LONG_NAME="EOC Node")
    assert control.captured_rows()[0]["possible_echo"] is True
    assert control.station_rows() == []  # echoes are not counted as station activity


def test_capture_cli_flag_never_combines_with_admin(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["x", "--capture", "--reset"])
    control.main()
    assert "cannot be combined" in json.loads(capsys.readouterr().out)["response"]


def test_capture_cli_flag_is_silent(monkeypatch, capsys):
    monkeypatch.setenv("MESSAGE", "hello mesh")
    monkeypatch.setenv("FROM_NODE", "42")
    monkeypatch.setattr("sys.argv", ["x", "--capture"])
    control.main()
    assert capsys.readouterr().out == ""
    assert control.captured_rows()[0]["message"] == "hello mesh"


# --- per-station summary & exports ------------------------------------------

def test_station_rows_group_by_callsign(monkeypatch, capsys):
    for key, value in MESHTASTIC_ENV.items():
        monkeypatch.setenv(key, value)
    send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC SHELTER1 BATTERY OPS", from_id="1001")
    send(monkeypatch, capsys, TRAFFIC, from_id="1001")
    send(monkeypatch, capsys, "EMCOMM SITREP SHELTER1 ALL GOOD", from_id="1001")
    capture(monkeypatch, capsys, "radio check", FROM_ID="1001")
    for key in MESHTASTIC_ENV:
        monkeypatch.delenv(key)
    send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="2002")
    rows = {r["station"]: r for r in control.station_rows()}
    w4 = rows["W4ABC"]
    assert (w4["checkins"], w4["traffic_sent"], w4["sitreps"], w4["captured_messages"]) == (1, 1, 1, 1)
    assert w4["messages_total"] == 4
    assert w4["avg_snr"] == pytest.approx(6.25, abs=0.06)
    assert w4["min_hops"] == 2
    assert rows["2002"]["deliveries_confirmed"] == 1


def test_export_includes_new_files_and_summary(monkeypatch, capsys, tmp_path):
    send(monkeypatch, capsys, "EMCOMM CHECKIN KN4EOC EOC AC NCS", from_id="!eoc")
    send(monkeypatch, capsys, TRAFFIC, from_id="!sh1")
    send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="!eoc")
    capture(monkeypatch, capsys, "hello", FROM_ID="!walker")
    out = control.export_bundle(str(tmp_path / "x"))
    for name in ("roster.csv", "traffic_log.csv", "formal_traffic.csv", "stations.csv",
                 "captured_messages.csv", "summary.txt"):
        assert (out / name).exists(), name
    with (out / "formal_traffic.csv").open(encoding="utf-8") as f:
        row = next(csv.DictReader(f))
    assert row["status"] == "delivered" and row["delivered_by"] == "KN4EOC"
    summary = (out / "summary.txt").read_text(encoding="utf-8")
    assert "1 of 1 confirmed delivered" in summary
    assert "Captured mesh messages: 1" in summary
    assert "Most active stations:" in summary
    assert "operator-reported" in summary


def test_delivery_stats_median():
    rows = [{"status": "delivered", "delivery_minutes": m} for m in (2, 4, 10)] + [{"status": "logged"}]
    stats = control.delivery_stats(rows)
    assert stats == {"total": 4, "delivered": 3, "relayed": 0, "median_minutes": 4.0, "max_minutes": 10.0}
