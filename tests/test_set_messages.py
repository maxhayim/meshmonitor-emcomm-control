"""SET start/end messages: per-message switches, channel selection, once-only, post-SET lock, logging."""
import copy
import json
from datetime import datetime, timedelta

import pytest

import mm_emcomm_control as control
import mm_emcomm_panel as panel
from test_net_control import END, SOUTH_DADE_NC, START, TZ, _FixedDatetime, _server

SET_START = "SET START | NET OPEN | ALL STATIONS PLEASE USE THE SET MESSAGE TEMPLATE | NET CONTROL ACTIVE"
SET_END = ("SET COMPLETE | NET CLOSED | THANK YOU TO ALL STATIONS FOR PARTICIPATING | "
           "RETURNING CHANNEL TO NORMAL TRAFFIC")


def config(start_on=True, end_on=True, channels=None, extra=True):
    nc = copy.deepcopy(SOUTH_DADE_NC)
    if not extra:  # only the SET start/end messages
        nc["announcements"] = {"enabled": True}
    nc["announcements"]["set_start"] = {"enabled": start_on, "message": SET_START}
    nc["announcements"]["set_end"] = {"enabled": end_on, "message": SET_END}
    if channels is not None:
        nc["channels"] = channels
    return nc


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for name in ("MESHCORE_SOURCE_ID", "CHANNEL", "TIMER_ID", "MESSAGE", "IS_DIRECT", "PACKET_ID"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def apply(monkeypatch):
    # Pin the clock to mid-SET so results never depend on the real date
    # (START/END are fixed 2026 times); individual tests may move it.
    monkeypatch.setattr(control, "datetime", _FixedDatetime)
    monkeypatch.setattr(_FixedDatetime, "value", START + timedelta(minutes=30))

    def _apply(nc):
        monkeypatch.setitem(control.CONFIG, "net_control", nc)
        monkeypatch.setitem(control.CONFIG, "start", START.isoformat())
        monkeypatch.setitem(control.CONFIG, "end", END.isoformat())
        monkeypatch.setitem(control.CONFIG, "exercise_style", "set-safe")
    return _apply


def run(minutes_from, minutes_to, target="t"):
    out, moment = [], minutes_from
    while moment <= minutes_to:
        out += [(moment.strftime("%H:%M"), m) for m in control.run_schedule_check(now=moment, target=target)]
        moment += timedelta(minutes=1)
    return out


def test_start_and_end_messages_sent_only_at_start_and_end(apply):
    apply(config(extra=False))
    sent = run(START - timedelta(hours=2), END + timedelta(hours=1))
    assert sent == [("09:00", SET_START), ("12:00", SET_END)]


def test_order_with_other_same_minute_announcements(apply):
    apply(config())
    sent = run(START - timedelta(hours=2), END + timedelta(hours=1))
    at_start = [m for t, m in sent if t == "09:00"]
    at_end = [m for t, m in sent if t == "12:00"]
    assert at_start[0] == SET_START            # net opens first
    assert at_end[-1] == SET_END               # net closes last


@pytest.mark.parametrize("start_on,end_on,expected", [
    (True, False, [SET_START]), (False, True, [SET_END]), (False, False, []),
])
def test_each_message_enabled_independently(apply, start_on, end_on, expected):
    apply(config(start_on, end_on, extra=False))
    assert [m for _, m in run(START - timedelta(minutes=5), END + timedelta(minutes=5))] == expected


def test_enabled_without_message_is_not_sent(apply):
    nc = config(extra=False)
    nc["announcements"]["set_start"]["message"] = ""
    apply(nc)
    _, warnings = control.net_control_config()
    assert any("set_start is enabled but has no message" in w for w in warnings)
    assert control.run_schedule_check(now=START, target="t") == []


def test_no_duplicates_across_restart(apply):
    apply(config(extra=False))
    assert control.run_schedule_check(now=START, target="t") == [SET_START]
    # A restarted scheduler (fresh process) reads the same automation.json.
    data = json.loads((control.DATA_DIR / "automation.json").read_text())
    assert data["fired"][control.schedule_id()]["t"]["set-start"]["status"] == "sent"
    assert control.run_schedule_check(now=START + timedelta(seconds=40), target="t") == []
    assert control.run_schedule_check(now=START + timedelta(minutes=3), target="t") == []
    assert control.run_schedule_check(now=END, target="t") == [SET_END]
    assert control.run_schedule_check(now=END + timedelta(minutes=1), target="t") == []


def test_late_scheduler_does_not_send_start_after_grace(apply):
    apply(config(extra=False))
    assert control.run_schedule_check(now=START + timedelta(minutes=30), target="t") == []
    assert control.automation_rows()[-1]["reason"].startswith("missed")


# --- channel selection --------------------------------------------------------------

def test_sent_only_on_selected_channels(apply, monkeypatch):
    apply(config(extra=False, channels=["meshtastic:0", "meshcore:0"]))
    monkeypatch.setenv("CHANNEL", "0")
    assert control.run_schedule_check(now=START, target="mt-ch0") == [SET_START]
    monkeypatch.setenv("CHANNEL", "2")
    assert control.run_schedule_check(now=START, target="mt-ch2") == []
    assert "not selected" in control.automation_rows()[-1]["reason"]
    monkeypatch.setenv("MESHCORE_SOURCE_ID", "mc1")
    monkeypatch.setenv("CHANNEL", "0")
    assert control.run_schedule_check(now=START, target="mc-ch0") == [SET_START]


def test_unknown_channel_is_refused_when_channels_selected(apply):
    apply(config(extra=False, channels=["0"]))
    assert control.run_schedule_check(now=START, target="t") == []
    assert "--channel" in control.automation_rows()[-1]["reason"]


def test_channel_cli_argument_for_meshtastic_timed_events(apply, monkeypatch, capsys):
    apply(config(extra=False, channels=["meshtastic:0"]))
    monkeypatch.setattr(control, "datetime", _FixedDatetime)
    monkeypatch.setattr(_FixedDatetime, "value", START)
    monkeypatch.setattr("sys.argv", ["x", "--schedule-check", "--channel", "0", "--target", "mt"])
    control.main()
    assert json.loads(capsys.readouterr().out)["response"] == SET_START
    monkeypatch.setattr("sys.argv", ["x", "--schedule-check", "--channel", "abc"])
    control.main()
    assert "response" not in json.loads(capsys.readouterr().out)


def test_no_channel_selection_means_unrestricted(apply, monkeypatch):
    apply(config(extra=False))
    monkeypatch.setenv("CHANNEL", "5")
    assert control.run_schedule_check(now=START, target="t") == [SET_START]


def test_checkin_ack_respects_channel_selection(apply, monkeypatch):
    nc = config(channels=["meshtastic:0"])
    apply(nc)
    msg = "SET R | NET CONTROL | WRWJ781 | CHECKIN | FROM CORAL SPRINGS"
    monkeypatch.setenv("CHANNEL", "3")
    assert control.handle_net_checkin(msg, control.load_state(), now=START + timedelta(minutes=5)) is None
    assert "not selected" in control.automation_rows()[-1]["reason"]
    monkeypatch.setenv("CHANNEL", "0")
    assert control.handle_net_checkin(msg, control.load_state(), now=START + timedelta(minutes=6))


@pytest.mark.parametrize("raw,ok", [("0", "0"), (3, "3"), ("MeshCore:1", "meshcore:1"), ("meshtastic:07", "meshtastic:7"),
                                    ("lora:1", None), ("", None), (True, None), ("123", None)])
def test_channel_normalization(raw, ok):
    assert control.normalize_channel(raw) == ok


# --- system-generated logging ---------------------------------------------------------

def test_logged_as_system_generated(apply, tmp_path):
    apply(config(extra=False))
    control.run_schedule_check(now=START, target="t")
    row = [r for r in control.automation_rows() if r["event"] == "AUTO ANNOUNCEMENT"][-1]
    assert row["schedule_event"] == "set-start" and row["outgoing"] == SET_START and row["system_generated"] is True
    out = control.export_bundle(str(tmp_path / "x"))
    header = (out / "automation_log.csv").read_text().splitlines()[0]
    assert header.endswith("system_generated")


# --- echo safety ------------------------------------------------------------------------

@pytest.mark.parametrize("text", [SET_START, SET_END, "SET END | NET CLOSED"])
def test_echoed_set_line_never_answered(apply, monkeypatch, capsys, text):
    apply(config())
    monkeypatch.setenv("MESSAGE", text)
    monkeypatch.setenv("FROM_ID", "!other")
    control.handle_message()
    assert capsys.readouterr().out == ""


def test_echo_flagged_in_capture(apply, monkeypatch, capsys):
    apply(config())
    monkeypatch.setenv("MESSAGE", "net open, copy")
    assert control.SYSTEM_ECHO_RE.match(SET_START) and control.SYSTEM_ECHO_RE.match(SET_END)


# --- panel editing and post-SET lock -------------------------------------------------------

def test_panel_edits_messages_and_switches(apply):
    apply(config())
    ok, msg = control.update_automation_overrides({
        "set_start_message": "SET START | NET OPEN | USE THE TEMPLATE", "set_start_enabled": True,
        "set_end_message": SET_END, "set_end_enabled": False, "channels": "meshtastic:0, meshcore:0"})
    assert ok, msg
    nc, _ = control.net_control_config()
    assert nc["announcements"]["set_start"] == {"enabled": True, "message": "SET START | NET OPEN | USE THE TEMPLATE"}
    assert nc["announcements"]["set_end"]["enabled"] is False
    assert nc["channels"] == ["meshtastic:0", "meshcore:0"]


@pytest.mark.parametrize("values,error", [
    ({"set_start_message": "", "set_start_enabled": True}, "enabled but empty"),
    ({"set_start_message": "X" * 140, "set_start_enabled": True}, "limit is 133"),
    ({"set_end_message": "SET END | THIS IS A TEST", "set_end_enabled": True}, "TEST"),
    ({"channels": "zero"}, "Channels must look like"),
])
def test_panel_validation(apply, values, error):
    apply(config())
    ok, msg = control.update_automation_overrides(values)
    assert not ok and error in msg


def test_panel_page_has_editors(apply):
    apply(config())
    import http.client
    server, port = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        body = conn.getresponse().read().decode("utf-8")
        assert 'name="set_start_message"' in body and 'name="set_end_enabled"' in body
        assert 'name="set_fields" value="1"' in body and "SET channels" in body
        conn.request("POST", "/automation/settings",
                     body="form=1&enabled=1&set_fields=1&set_start_enabled=1&set_start_message=SET+START+%7C+NET+OPEN&set_end_message=&channels=0",
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert conn.getresponse().status == 303
        nc, _ = control.net_control_config()
        assert nc["announcements"]["set_start"]["message"] == "SET START | NET OPEN"
        assert nc["announcements"]["set_end"]["enabled"] is False and nc["channels"] == ["0"]
    finally:
        server.shutdown()
        server.server_close()


def test_after_set_ends_controls_are_closed(apply, monkeypatch):
    apply(config())
    monkeypatch.setattr(control, "datetime", _FixedDatetime)
    monkeypatch.setattr(_FixedDatetime, "value", END + timedelta(hours=1))
    ok, msg = control.update_automation_overrides({"set_start_message": SET_START, "set_start_enabled": True})
    assert not ok and "has ended" in msg
    ok, _ = control.update_automation_overrides({"name": "NET CONTROL"})  # identity edits still allowed
    assert ok
    assert control.queue_manual_announcement("set-end", now=END + timedelta(hours=1))[0] is False
    assert control.run_schedule_check(now=END + timedelta(hours=1), target="t") == []
    import http.client
    server, port = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        body = conn.getresponse().read().decode("utf-8")
        assert "This SET has ended" in body
        assert 'name="set_fields"' not in body
        assert "Preview announcement" not in body
        assert "Exercise completed — no scheduled announcements remaining." in body
    finally:
        server.shutdown()
        server.server_close()


def test_live_mode_blocks_set_messages(apply, capsys):
    apply(config(extra=False))
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    assert control.run_schedule_check(now=START, target="t") == []
    assert "LIVE" in control.automation_rows()[-1]["reason"]


def test_absent_set_messages_keep_v260_behavior(apply):
    apply(copy.deepcopy(SOUTH_DADE_NC))
    keys = [i["key"] for i in control.build_schedule(control.net_control_config()[0])[0]]
    assert "set-start" not in keys and "set-end" not in keys


def test_example_config_contains_requested_messages():
    from pathlib import Path
    cfg = json.loads((Path(control.__file__).parent / "docs/examples/south-dade-set-2026.config.json").read_text())
    nc, warnings = control.parse_net_control(cfg["net_control"])
    assert warnings == []
    assert nc["announcements"]["set_start"] == {"enabled": True, "message": SET_START}
    assert nc["announcements"]["set_end"] == {"enabled": True, "message": SET_END}
    assert nc["channels"] == ["meshtastic:0", "meshcore:0"]
