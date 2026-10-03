"""Net Control automation: identity, location, check-in ACKs, loop/dedup, schedule, mode safety."""
import copy
import json
import re
from datetime import datetime, timedelta

import pytest

import mm_emcomm_control as control
import mm_emcomm_panel as panel
from conftest import send

TZ = control.LOCAL_TZ
START = datetime(2026, 10, 3, 9, 0, tzinfo=TZ)
END = datetime(2026, 10, 3, 12, 0, tzinfo=TZ)
CHECKIN = "SET R | NET CONTROL | WRWJ781 | CHECKIN | FROM CORAL SPRINGS, FLORIDA"
TEST_WORD = re.compile(r"\btest\b", re.I)

SOUTH_DADE_NC = {
    "enabled": True,
    "name": "NET CONTROL",
    "operator_name": "",
    "callsign": "KI4SDC",
    "location": {"mode": "auto", "override": "DORAL, FLORIDA"},
    "auto_checkin_ack": True,
    "announcements": {
        "enabled": True,
        "before_start": [
            {"minutes_before": 60, "message": "WARNING: SET EXERCISE BEGINS IN 1 HOUR. MESHTASTIC + MESHCORE USERS WELCOME."},
            {"minutes_before": 15, "message": "WARNING: SET EXERCISE BEGINS IN 15 MINUTES. PREPARE FOR EXERCISE TRAFFIC."},
        ],
        "at_start": {"message": "WARNING: SET EXERCISE IS NOW IN PROGRESS. SIMULATED TRAFFIC ONLY."},
        "during": {"interval_minutes": 60, "message": "WARNING: SET EXERCISE IN PROGRESS UNTIL 12PM. SIMULATED TRAFFIC ONLY."},
        "before_end": [{"minutes_before": 15, "message": "SET EXERCISE ENDS IN 15 MINUTES. FINAL TRAFFIC AND CHECKOUTS MAY BE SENT."}],
        "at_end": {"message": "SET EXERCISE COMPLETE. THANK YOU FOR PARTICIPATING."},
    },
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("MESHCORE_SOURCE_ID", "PACKET_ID", "CHANNEL", "FROM_NODE", "FROM_LONG_NAME", "IS_DIRECT",
                 "TIMER_ID", "MM_LAT", "MM_LON", "MESSAGE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def nc_config(monkeypatch):
    """South Dade-style config, window around the real clock so handle_message paths are 'during'."""
    def apply(nc=None, start=None, end=None, style="set-safe"):
        now = datetime.now(TZ)
        monkeypatch.setitem(control.CONFIG, "net_control", copy.deepcopy(SOUTH_DADE_NC if nc is None else nc))
        monkeypatch.setitem(control.CONFIG, "start", (start or now - timedelta(hours=1)).isoformat())
        monkeypatch.setitem(control.CONFIG, "end", (end or now + timedelta(hours=1)).isoformat())
        monkeypatch.setitem(control.CONFIG, "exercise_style", style)
    apply()
    return apply


@pytest.fixture
def sd_window(nc_config):
    nc_config(start=START, end=END)


def checkin(monkeypatch, capsys, text=CHECKIN, packet=None, from_id="!p1", **env):
    if packet is not None:
        monkeypatch.setenv("PACKET_ID", str(packet))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MESSAGE", text)
    monkeypatch.setenv("FROM_ID", from_id)
    control.handle_message()
    out = capsys.readouterr().out.strip()
    return json.loads(out)["response"] if out else None


def automation_events():
    return [r["event"] for r in control.automation_rows()]


def nc_with(**changes):
    nc = copy.deepcopy(SOUTH_DADE_NC)
    nc.update(changes)
    return nc


# --- CONFIG -------------------------------------------------------------------

def test_config_without_net_control_unchanged(monkeypatch, capsys):
    monkeypatch.delitem(control.CONFIG, "net_control", raising=False)
    assert control.net_control_config()[0] is None
    assert checkin(monkeypatch, capsys) is None  # silent, as before
    assert control.run_schedule_check(now=START) == []
    assert automation_events() == []
    assert send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC EOC AC NCS")["response"].startswith("EXERCISE ACK CHECKIN")


def test_config_file_loads_net_control(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"net_control": SOUTH_DADE_NC}), encoding="utf-8")
    nc, warnings = control.parse_net_control(control.load_config(path)["net_control"])
    assert warnings == [] and nc["callsign"] == "KI4SDC"


def test_disabled_net_control_means_no_automation(nc_config, monkeypatch, capsys):
    nc_config(nc_with(enabled=False))
    assert checkin(monkeypatch, capsys) is None
    assert control.run_schedule_check(now=datetime.now(TZ)) == []
    events = automation_events()
    assert events[0] == "AUTO ACK SKIPPED"
    assert "AUTO CHECKIN ACK" not in events and "AUTO ANNOUNCEMENT" not in events


def test_switches_default_off():
    nc, _ = control.parse_net_control({"callsign": "KI4SDC"})
    assert (nc["enabled"], nc["auto_checkin_ack"], nc["announcements"]["enabled"]) == (False, False, False)


@pytest.mark.parametrize("fields,expected", [
    ({"name": "NET CONTROL"}, "NET CONTROL"),
    ({"callsign": "KI4SDC"}, "KI4SDC"),
    ({"name": "NET CONTROL", "callsign": "KI4SDC"}, "NET CONTROL KI4SDC"),
    ({"operator_name": "ERIC", "callsign": "KI4SDC", "name": "NET CONTROL"}, "ERIC KI4SDC"),
    ({"operator_name": "Eric"}, "ERIC"),
    ({}, "NET CONTROL"),
])
def test_identity(fields, expected):
    nc, _ = control.parse_net_control(fields)
    assert control.net_control_identity(nc) == expected


def test_invalid_config_values_warn_and_are_ignored():
    nc, warnings = control.parse_net_control({
        "enabled": "yes", "callsign": "KI4|SDC", "location": {"mode": "gps", "override": "25.8123, -80.3456"},
        "announcements": {"before_start": [{"minutes_before": -5, "message": "X"}, {"minutes_before": 15}],
                          "during": {"interval_minutes": 1, "message": "Y"}},
    })
    assert nc["enabled"] is False and nc["callsign"] == ""
    assert nc["location"] == {"mode": "auto", "override": ""}
    assert nc["announcements"]["before_start"] == [] and nc["announcements"]["during"] is None
    text = " ".join(warnings)
    for fragment in ("enabled must be true or false", "callsign", "location.mode", "GPS coordinates",
                     "minutes_before", "message must be non-empty", "interval_minutes"):
        assert fragment in text, fragment
    assert control.parse_net_control("nope")[0] is None


def test_location_override_takes_precedence(sd_window, monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM CHECKIN KI4SDC MIAMI-DADE-EOC AC NCS")
    nc, _ = control.net_control_config()
    assert control.resolve_location(nc) == ("DORAL, FLORIDA", "override")


def test_auto_location_from_net_control_checkin(nc_config, monkeypatch, capsys):
    nc_config(nc_with(location={"mode": "auto", "override": ""}))
    send(monkeypatch, capsys, "EMCOMM CHECKIN KI4SDC MIAMI-DADE-EOC AC NCS")
    nc, _ = control.net_control_config()
    assert control.resolve_location(nc) == ("MIAMI DADE EOC", "roster")
    assert checkin(monkeypatch, capsys).endswith("RECEIVED HERE IN MIAMI DADE EOC")


def test_no_location_produces_short_ack(nc_config, monkeypatch, capsys):
    nc_config(nc_with(location={"mode": "auto", "override": ""}))
    monkeypatch.setenv("MM_LAT", "25.81")  # coordinates alone are never used or sent
    monkeypatch.setenv("MM_LON", "-80.35")
    assert checkin(monkeypatch, capsys) == "SET R | WRWJ781 | NET CONTROL KI4SDC | CHECKIN ACK | RECEIVED"


def test_location_mode_none(nc_config, monkeypatch, capsys):
    nc_config(nc_with(location={"mode": "none", "override": "DORAL, FLORIDA"}))
    assert checkin(monkeypatch, capsys).endswith("| CHECKIN ACK | RECEIVED")


# --- CHECK-IN PARSING ---------------------------------------------------------

def parse(text, nc=None):
    return control.parse_checkin_line(text, control.parse_net_control(nc or SOUTH_DADE_NC)[0])


def test_canonical_checkin_parsing():
    p = parse(CHECKIN)
    assert p["participant"] == "WRWJ781" and p["precedence"] == "R" and p["layout"] == "preferred"
    assert p["reported_location"] == "CORAL SPRINGS, FLORIDA"


def test_name_and_callsign_participant():
    assert parse("SET R | NET CONTROL | ERIC WRZU598 | CHECKIN | FROM CORAL SPRINGS, FLORIDA")["participant"] == "ERIC WRZU598"


def test_alternate_layout_normalized():
    p = parse("SET R | WRWJ781 | NET CONTROL | CHECKIN | FROM CORAL SPRINGS, FLORIDA")
    assert p["participant"] == "WRWJ781" and p["layout"] == "alternate"


@pytest.mark.parametrize("text", [
    "SET R | WRWJ781 | NET CONTROL KI4SDC | CHECKIN ACK | RECEIVED HERE IN DORAL, FLORIDA",
    "SET R | NET CONTROL | WRWJ781 | CHECKIN NOW | FROM X",
    "SET R | NET CONTROL | WRWJ781 | CHECK-IN | FROM X",
    "SET R | NET CONTROL | WRWJ781",
    "SET R | EOC | WRWJ781 | CHECKIN | FROM X",
    "SET X | NET CONTROL | WRWJ781 | CHECKIN | FROM X",
    "NET CONTROL | WRWJ781 | CHECKIN",
    "checkin with net control please",
    "SET R | NET CONTROL |  | CHECKIN | FROM X",
])
def test_non_checkins_do_not_match(text):
    assert parse(text) is None


def test_exact_subject_match_is_case_insensitive():
    assert parse("set r | net control | wrwj781 | checkin | from x")["participant"] == "WRWJ781"


@pytest.mark.parametrize("sender", ["NET CONTROL", "NET CONTROL KI4SDC", "KI4SDC", "ERIC KI4SDC"])
def test_net_control_sender_does_not_trigger(nc_config, monkeypatch, capsys, sender):
    nc_config(nc_with(operator_name="ERIC"))
    text = f"SET R | NET CONTROL | {sender} | CHECKIN | FROM DORAL"
    assert checkin(monkeypatch, capsys, text) is None
    rows = control.automation_rows()
    assert rows and rows[-1]["event"] == "AUTO ACK SKIPPED" and "loop" in rows[-1]["reason"]


# --- ACK OUTPUT ---------------------------------------------------------------

def test_ki4sdc_ack_output(nc_config, monkeypatch, capsys):
    assert checkin(monkeypatch, capsys) == \
        "SET R | WRWJ781 | NET CONTROL KI4SDC | CHECKIN ACK | RECEIVED HERE IN DORAL, FLORIDA"
    assert checkin(monkeypatch, capsys, "SET R | NET CONTROL | ERIC WRZU598 | CHECKIN | FROM CORAL SPRINGS, FLORIDA") == \
        "SET R | ERIC WRZU598 | NET CONTROL KI4SDC | CHECKIN ACK | RECEIVED HERE IN DORAL, FLORIDA"


def test_dynamic_identity_and_precedence(nc_config, monkeypatch, capsys):
    nc_config(nc_with(operator_name="ERIC"))
    assert checkin(monkeypatch, capsys, "SET P | NET CONTROL | KJ5ABC | CHECKIN | FROM HOMESTEAD") == \
        "SET P | KJ5ABC | ERIC KI4SDC | CHECKIN ACK | RECEIVED HERE IN DORAL, FLORIDA"


def test_checkin_registers_on_roster(nc_config, monkeypatch, capsys):
    checkin(monkeypatch, capsys)
    entry = control.load_state()["participants"]["WRWJ781"]
    assert entry["location"] == "CORAL SPRINGS, FLORIDA" and entry["source"] == "net_control_checkin"


def test_set_safe_ack_contains_no_test(nc_config, monkeypatch, capsys):
    ack = checkin(monkeypatch, capsys)
    assert not TEST_WORD.search(ack)


def test_standard_style_ack_uses_test_marker(nc_config, monkeypatch, capsys):
    nc_config(style="standard")
    ack = checkin(monkeypatch, capsys, "TEST R | NET CONTROL | WRWJ781 | CHECKIN | FROM CORAL SPRINGS")
    assert ack.startswith("TEST R | WRWJ781 | NET CONTROL KI4SDC | CHECKIN ACK")


def test_long_location_is_omitted_not_truncated(nc_config, monkeypatch, capsys):
    nc_config(nc_with(location={"mode": "override", "override": "A" * 55 + " FL"}))
    who = "ERIC WRZU598 MOBILE UNIT"
    ack = checkin(monkeypatch, capsys, f"SET R | NET CONTROL | {who} | CHECKIN | FROM X")
    assert ack == f"SET R | {who} | NET CONTROL KI4SDC | CHECKIN ACK | RECEIVED"
    assert len(ack) <= control.MAX_LEN
    assert "location omitted" in control.automation_rows()[-1]["reason"]


def test_ack_over_limit_is_not_sent():
    nc = control.parse_net_control(nc_with(name="N" * 40))[0]
    parsed = {"participant": "P" * 40, "precedence": "R"}
    ack, note = control.build_checkin_ack(parsed, nc, "", limit=60)
    assert ack is None and "not sent" in note


# --- LOOP / DEDUP -------------------------------------------------------------

def test_own_reply_does_not_trigger(nc_config, monkeypatch, capsys):
    ack = checkin(monkeypatch, capsys)
    assert checkin(monkeypatch, capsys, ack, from_id="!ncs") is None
    assert automation_events().count("AUTO CHECKIN ACK") == 1


def test_duplicate_suppressed_by_packet_id(nc_config, monkeypatch, capsys):
    assert checkin(monkeypatch, capsys, packet=4242) is not None
    assert checkin(monkeypatch, capsys, packet=4242) is None
    assert automation_events()[-1] == "AUTO DUPLICATE SUPPRESSED"
    assert checkin(monkeypatch, capsys, packet=4243) is not None  # a genuine resend is a new packet


def test_duplicate_suppressed_by_text_on_meshcore(nc_config, monkeypatch, capsys):
    env = {"MESHCORE_SOURCE_ID": "mc1", "FROM_LONG_NAME": "Field 2", "IS_DIRECT": "false", "CHANNEL": "0"}
    assert checkin(monkeypatch, capsys, **env) is not None
    assert checkin(monkeypatch, capsys, **env) is None


def test_dedup_survives_restart(nc_config, monkeypatch, capsys):
    checkin(monkeypatch, capsys, packet=1)
    assert (control.DATA_DIR / "automation.json").exists()
    data = json.loads((control.DATA_DIR / "automation.json").read_text())
    assert any(k.startswith("pkt:") for k in data["dedup"])


def test_different_messages_same_sender_work(nc_config, monkeypatch, capsys):
    assert checkin(monkeypatch, capsys) is not None
    assert checkin(monkeypatch, capsys, CHECKIN.replace("CORAL SPRINGS", "PARKLAND")) is not None


def test_same_text_on_different_channel_or_network(nc_config, monkeypatch, capsys):
    assert checkin(monkeypatch, capsys, CHANNEL="0") is not None
    assert checkin(monkeypatch, capsys, CHANNEL="1") is not None
    assert checkin(monkeypatch, capsys, CHANNEL="1", MESHCORE_SOURCE_ID="mc1") is not None


def test_dedup_window_expires(sd_window):
    state = control.load_state()
    now = datetime(2026, 10, 3, 10, 0, tzinfo=TZ)
    assert control.handle_net_checkin(CHECKIN, state, now=now)
    assert control.handle_net_checkin(CHECKIN, control.load_state(), now=now + timedelta(minutes=1)) is None
    assert control.handle_net_checkin(CHECKIN, control.load_state(), now=now + timedelta(minutes=5))


# --- MODE ---------------------------------------------------------------------

def test_live_blocks_auto_ack(nc_config, monkeypatch, capsys):
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    assert checkin(monkeypatch, capsys) is None
    assert automation_events()[-1] == "AUTO ACK BLOCKED LIVE MODE"
    assert "WRWJ781" not in control.load_state()["participants"]


def test_live_blocks_announcements(sd_window, capsys):
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    assert control.run_schedule_check(now=START, target="t") == []
    rows = control.automation_rows()
    assert rows[-1]["event"] == "AUTO ANNOUNCEMENT SKIPPED" and "LIVE" in rows[-1]["reason"]
    assert control.send_announcement("during-60", now=START + timedelta(hours=1), target="t")[0] == []


def test_switching_to_live_stops_pending(sd_window, capsys):
    assert control.run_schedule_check(now=START, target="t")  # start fires in EXERCISE
    ok, _ = control.queue_manual_announcement("during-60", now=START + timedelta(minutes=5))
    assert ok
    control.set_mode("live", confirm_live=True)
    capsys.readouterr()
    assert control.load_automation()["manual_queue"] == []
    assert control.run_schedule_check(now=START + timedelta(hours=1), target="t") == []
    assert control.schedule_overview(START + timedelta(hours=1))["status"] == "PAUSED (LIVE MODE)"


# --- TIME WINDOW --------------------------------------------------------------

@pytest.mark.parametrize("moment,allowed,event", [
    (START - timedelta(minutes=1), False, "AUTO ACK BLOCKED OUTSIDE WINDOW"),
    (START, True, "AUTO CHECKIN ACK"),
    (END - timedelta(minutes=1), True, "AUTO CHECKIN ACK"),
    (END, False, "AUTO ACK BLOCKED OUTSIDE WINDOW"),
])
def test_ack_window(sd_window, moment, allowed, event):
    ack = control.handle_net_checkin(CHECKIN, control.load_state(), now=moment)
    assert bool(ack) is allowed
    assert automation_events()[-1] == event


def test_window_always_option(nc_config):
    nc_config(nc_with(checkin_ack_window="always"), start=START, end=END)
    assert control.handle_net_checkin(CHECKIN, control.load_state(), now=START - timedelta(hours=2))


# --- SCHEDULE -----------------------------------------------------------------

def run_minutes(start, end, target="t"):
    fired = []
    moment = start
    while moment <= end:
        for message in control.run_schedule_check(now=moment, target=target):
            fired.append((moment.strftime("%H:%M"), message))
        moment += timedelta(minutes=1)
    return fired


def test_full_south_dade_schedule(sd_window):
    fired = run_minutes(datetime(2026, 10, 3, 7, 0, tzinfo=TZ), datetime(2026, 10, 3, 13, 0, tzinfo=TZ))
    assert [t for t, _ in fired] == ["08:00", "08:45", "09:00", "10:00", "11:00", "11:45", "12:00"]
    assert fired[0][1].startswith("WARNING: SET EXERCISE BEGINS IN 1 HOUR")
    assert fired[1][1].startswith("WARNING: SET EXERCISE BEGINS IN 15 MINUTES")
    assert fired[2][1].startswith("WARNING: SET EXERCISE IS NOW IN PROGRESS")
    assert fired[3][1] == fired[4][1] and "IN PROGRESS UNTIL 12PM" in fired[3][1]
    assert fired[5][1].startswith("SET EXERCISE ENDS IN 15 MINUTES")
    assert fired[6][1] == "SET EXERCISE COMPLETE. THANK YOU FOR PARTICIPATING."
    assert "AUTO SCHEDULE COMPLETED" in automation_events()


def test_no_periodic_warning_at_end(sd_window):
    items, _ = control.build_schedule(control.net_control_config()[0])
    assert [i["key"] for i in items if i["kind"] == "during"] == ["during-60", "during-120"]


def test_periodic_warning_not_stacked_on_explicit_item(nc_config):
    nc = copy.deepcopy(SOUTH_DADE_NC)
    nc["announcements"]["before_end"] = [{"minutes_before": 60, "message": "ENDS IN 1 HOUR. EXERCISE."}]
    nc_config(nc, start=START, end=END)
    items, _ = control.build_schedule(control.net_control_config()[0])
    at_11 = [i["key"] for i in items if i["time"] == START + timedelta(hours=2)]
    assert at_11 == ["preend-60"]


def test_no_duplicate_firing_and_per_target(sd_window):
    assert control.run_schedule_check(now=START, target="meshtastic") != []
    assert control.run_schedule_check(now=START + timedelta(seconds=30), target="meshtastic") == []
    assert control.run_schedule_check(now=START + timedelta(minutes=1), target="meshcore") != []


def test_no_events_after_end(sd_window):
    run_minutes(START, END)
    assert run_minutes(END + timedelta(minutes=1), END + timedelta(hours=3)) == []
    assert control.send_announcement("end", now=END + timedelta(hours=1), target="t")[0] == []


def test_fired_event_removed_from_upcoming_and_completed(sd_window):
    before = control.schedule_overview(datetime(2026, 10, 3, 7, 30, tzinfo=TZ))
    assert [i["key"] for i in before["upcoming"]] == [
        "prestart-60", "prestart-15", "start", "during-60", "during-120", "preend-15", "end"]
    assert before["status"] == "SCHEDULED"
    run_minutes(datetime(2026, 10, 3, 7, 30, tzinfo=TZ), datetime(2026, 10, 3, 10, 5, tzinfo=TZ))
    mid = control.schedule_overview(datetime(2026, 10, 3, 10, 5, tzinfo=TZ))
    assert [i["key"] for i in mid["upcoming"]] == ["during-120", "preend-15", "end"]
    assert mid["status"] == "ACTIVE"
    run_minutes(datetime(2026, 10, 3, 10, 6, tzinfo=TZ), END)
    done = control.schedule_overview(END + timedelta(minutes=1))
    assert done["upcoming"] == [] and done["status"] == "COMPLETED"
    # History is retained.
    assert automation_events().count("AUTO ANNOUNCEMENT") == 7


def test_missed_items_are_logged_not_sent_late(sd_window):
    assert control.run_schedule_check(now=datetime(2026, 10, 3, 10, 8, tzinfo=TZ), target="late") == ["WARNING: SET EXERCISE IN PROGRESS UNTIL 12PM. SIMULATED TRAFFIC ONLY."]
    reasons = [r["reason"] for r in control.automation_rows() if r["event"] == "AUTO ANNOUNCEMENT SKIPPED"]
    assert len(reasons) == 3 and all(r.startswith("missed") for r in reasons)


def test_reset_does_not_rearm_fired_announcements(sd_window, capsys):
    control.run_schedule_check(now=START, target="t")
    control.reset_operation()
    capsys.readouterr()
    assert control.run_schedule_check(now=START + timedelta(minutes=2), target="t") == []


def test_announcements_need_start_and_end(nc_config, monkeypatch):
    monkeypatch.setitem(control.CONFIG, "start", "")
    items, warnings = control.build_schedule(control.net_control_config()[0])
    assert items == [] and "start" in warnings[0]


def test_send_announcement_cli(sd_window, monkeypatch, capsys):
    monkeypatch.setattr(control, "datetime", _FixedDatetime)
    monkeypatch.setattr("sys.argv", ["x", "--announcement", "START", "--target", "cli"])
    control.main()
    assert json.loads(capsys.readouterr().out)["response"].startswith("WARNING: SET EXERCISE IS NOW IN PROGRESS")
    monkeypatch.setattr("sys.argv", ["x", "--announcement", "nope"])
    control.main()
    out = json.loads(capsys.readouterr().out)
    assert "response" not in out and "unknown announcement" in out["status"]


def test_schedule_check_cli_silent_when_nothing_due(sd_window, monkeypatch, capsys):
    monkeypatch.setattr(control, "datetime", _FixedDatetime)
    _FixedDatetime.value = START + timedelta(minutes=30)
    monkeypatch.setattr("sys.argv", ["x", "--schedule-check"])
    control.main()
    assert capsys.readouterr().out == ""
    _FixedDatetime.value = START


class _FixedDatetime(datetime):
    value = START

    @classmethod
    def now(cls, tz=None):
        return cls.value if tz is None else cls.value.astimezone(tz)


# --- MESSAGE LENGTH -----------------------------------------------------------

def test_length_rules():
    assert control.length_report("x" * 120)["warning"] == ""
    assert control.length_report("x" * 121)["warning"] == "Recommended LoRa target exceeded."
    assert control.length_report("x" * 134)["over_limit"]


def test_over_limit_announcement_rejected_not_truncated(nc_config):
    long_text = "EXERCISE " + "W" * 140
    nc = copy.deepcopy(SOUTH_DADE_NC)
    nc["announcements"]["at_start"] = {"message": long_text}
    nc_config(nc, start=START, end=END)
    _, warnings = control.net_control_config()
    assert any("exceeds the 133-character limit" in w for w in warnings)
    assert control.run_schedule_check(now=START, target="t") == []
    assert "limit is 133" in control.automation_rows()[-1]["reason"]


def test_over_limit_allowed_explicitly_is_split_not_cut(nc_config, monkeypatch, capsys):
    long_text = "EXERCISE " + " ".join(["WORD"] * 40)
    nc = copy.deepcopy(SOUTH_DADE_NC)
    nc["allow_long_messages"] = True
    nc["announcements"]["at_start"] = {"message": long_text}
    nc_config(nc, start=START, end=END)
    messages = control.run_schedule_check(now=START, target="t")
    assert messages == [long_text]
    control.emit(messages)
    parts = json.loads(capsys.readouterr().out)["responses"]
    assert all(len(p) <= control.MAX_LEN for p in parts)
    assert " ".join(re.sub(r" \[\d/\d\]$", "", p) for p in parts) == long_text


def test_set_safe_blocks_test_word_in_announcement(nc_config):
    nc = copy.deepcopy(SOUTH_DADE_NC)
    nc["announcements"]["at_start"] = {"message": "THIS IS A TEST OF THE NET"}
    nc_config(nc, start=START, end=END)
    assert control.run_schedule_check(now=START, target="t") == []
    assert "TEST" in control.automation_rows()[-1]["reason"]


# --- PANEL --------------------------------------------------------------------

def test_panel_overrides_validate_and_apply(nc_config):
    ok, _ = control.update_automation_overrides({"operator_name": "Eric", "location_override": "Broward EOC",
                                                 "enabled": True, "auto_checkin_ack": False, "announcements_enabled": True})
    assert ok
    nc, _ = control.net_control_config()
    assert control.net_control_identity(nc) == "ERIC KI4SDC"
    assert nc["location"]["override"] == "BROWARD EOC" and nc["auto_checkin_ack"] is False
    ok, msg = control.update_automation_overrides({"location_override": "25.7617, -80.1918"})
    assert not ok and "coordinates" in msg
    ok, msg = control.update_automation_overrides({"callsign": "KI4|SDC"})
    assert not ok
    control.clear_automation_overrides()
    assert control.net_control_identity(control.net_control_config()[0]) == "NET CONTROL KI4SDC"


def test_inbound_mesh_cannot_change_settings(nc_config, monkeypatch, capsys):
    checkin(monkeypatch, capsys, "SET R | NET CONTROL | WRWJ781 | CHECKIN | callsign=HACKED enabled=false")
    assert control.load_automation()["overrides"] == {}


def test_manual_queue_sent_by_schedule_check(sd_window):
    moment = START + timedelta(minutes=20)
    ok, msg = control.queue_manual_announcement("during-60", now=moment)
    assert ok and "Queued" in msg
    out = control.run_schedule_check(now=moment + timedelta(minutes=1), target="a")
    assert out == ["WARNING: SET EXERCISE IN PROGRESS UNTIL 12PM. SIMULATED TRAFFIC ONLY."]
    assert control.run_schedule_check(now=moment + timedelta(minutes=2), target="a") == []
    assert control.run_schedule_check(now=moment + timedelta(minutes=2), target="b") == out
    assert control.run_schedule_check(now=moment + timedelta(minutes=30), target="c") == []  # expired
    assert control.queue_manual_announcement("end", now=END + timedelta(hours=1))[0] is False


def _server():
    import threading
    from test_panel import _free_port
    port = _free_port()
    server = panel.PanelServer(("127.0.0.1", port), panel.Handler, token="")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def test_panel_section_and_preview(sd_window, monkeypatch):
    import http.client
    monkeypatch.setattr(control, "datetime", _FixedDatetime)
    monkeypatch.setattr(_FixedDatetime, "value", END + timedelta(hours=1))
    server, port = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        body = conn.getresponse().read().decode("utf-8")
        for text in ("Net Control Automation", "NET CONTROL KI4SDC", "DORAL, FLORIDA", "Upcoming Automatic Messages",
                     "Schedule Status", "Exercise completed — no scheduled announcements remaining."):
            assert text in body, text
        conn.request("POST", "/automation/preview", body="key=start",
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        preview = conn.getresponse().read().decode("utf-8")
        for text in ("Event Name", "Character Count", "SET-safe", "Mode", "Exercise completed; no announcements"):
            assert text in preview, text
        assert "queue this announcement" not in preview
        conn.request("POST", "/automation/settings", body="form=1&enabled=1&name=NET+CONTROL&callsign=KI4SDC&operator_name=ERIC&location_override=DORAL",
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        assert conn.getresponse().status == 303
        assert control.net_control_identity(control.net_control_config()[0]) == "ERIC KI4SDC"
        conn.request("GET", "/export/automation_log.csv")
        assert conn.getresponse().read().decode("utf-8").startswith("time,mode,event")
    finally:
        server.shutdown()
        server.server_close()


def test_panel_without_net_control(monkeypatch):
    monkeypatch.delitem(control.CONFIG, "net_control", raising=False)
    import http.client
    server, port = _server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        assert "Net Control Automation: OFF" in conn.getresponse().read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()


# --- REGRESSION / EXPORTS -----------------------------------------------------

def test_existing_commands_unaffected(nc_config, monkeypatch, capsys):
    assert send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC EOC AC NCS")["response"].startswith("EXERCISE ACK CHECKIN")
    assert send(monkeypatch, capsys, "EMCOMM TRAFFIC R 2:MIKE 3:CHARLIE 4:WATER 7:EXERCISE REQUEST")["response"].startswith("EXERCISE ACK EX-001")
    assert send(monkeypatch, capsys, "SET STATUS")["response"].startswith("EXERCISE STATUS")
    monkeypatch.setenv("MESSAGE", "SET R | EX-001 | 2:MIKE | 3:CHARLIE | 4:WATER | 7:EXERCISE REQUEST")
    control.handle_message()
    assert capsys.readouterr().out == ""  # relayed formal line still silent
    control.handle_inject(6)
    assert json.loads(capsys.readouterr().out)["responses"][0].startswith("EXERCISE INJECT 6")


def test_export_includes_automation_log(nc_config, monkeypatch, capsys, tmp_path):
    checkin(monkeypatch, capsys)
    out = control.export_bundle(str(tmp_path / "x"))
    text = (out / "automation_log.csv").read_text(encoding="utf-8")
    assert "AUTO CHECKIN ACK" in text and "DORAL, FLORIDA" in text
    assert "Net Control automation: AUTO CHECKIN ACK=1" in (out / "summary.txt").read_text(encoding="utf-8")
    header = (out / "formal_traffic.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("traffic_id,mode,precedence,test_traffic,field_1_incident")


def test_no_south_dade_values_in_code():
    from pathlib import Path
    root = Path(control.__file__).parent
    for name in ("mm_emcomm_control.py", "mm_emcomm_panel.py"):
        text = (root / name).read_text(encoding="utf-8").upper()
        for word in ("KI4SDC", "DORAL", "WRWJ781", "WRZU598", "CORAL SPRINGS"):
            assert word not in text, (name, word)
