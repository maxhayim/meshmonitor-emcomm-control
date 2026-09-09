#!/usr/bin/env python3
# mm_meta:
#   name: EmComm Control
#   emoji: 🚨
#   language: Python
__version__ = "2.0.1"

"""
EmComm Control for MeshMonitor.

Dual-mode emergency-communications control:
- EXERCISE mode: SET/drill traffic, simulated injects, explicit EXERCISE/SIMULATED labeling.
- LIVE mode: real-world operator-entered check-ins, SITREPs, and message logging.
- Suitable for emergency operations center (EOC) workflows at city/municipal, county/regional, and state levels.

MeshMonitor Auto Responder patterns:
  ^EMCOMM\b
  ^SET\b          # legacy/exercise alias

Runtime:
  /data/scripts/mm_emcomm_control.py

Local administration:
  mm_emcomm_control.py --mode exercise
  mm_emcomm_control.py --mode live --confirm-live
  mm_emcomm_control.py --mode status
  mm_emcomm_control.py --inject <1-8>     # exercise mode only
  mm_emcomm_control.py --announce "TEXT"  # operator-supplied announcement
  mm_emcomm_control.py --reset

Safety:
- LIVE mode can only be enabled locally, never by an inbound mesh message.
- Exercise injects are blocked in LIVE mode.
- LIVE mode never fabricates incident conditions; it only acknowledges/logs operator-supplied information.
"""

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("MM_EMCOMM_DATA_DIR", str(SCRIPT_DIR / "mm_emcomm_control_data")))
STATE_FILE = DATA_DIR / "state.json"
LOG_FILE = DATA_DIR / "traffic.jsonl"

LEGACY_DIR = SCRIPT_DIR / "mm_arrl_set_data"
LEGACY_STATE_FILE = LEGACY_DIR / "state.json"
LEGACY_LOG_FILE = LEGACY_DIR / "traffic.jsonl"

TZ_NAME = os.getenv("MM_EMCOMM_TZ", os.getenv("SET_TZ", "America/New_York"))
try:
    LOCAL_TZ = ZoneInfo(TZ_NAME)
except Exception:
    LOCAL_TZ = ZoneInfo("UTC")

EXERCISE_NAME = os.getenv("MM_EMCOMM_EXERCISE_NAME", os.getenv("SET_NAME", "Emergency Communications Exercise"))
MAX_LEN = int(os.getenv("MM_EMCOMM_MAXLEN", "190"))

EXERCISE_INJECTS = {
    1: (
        "EXERCISE EXERCISE — Communications exercise has begun. All traffic is SIMULATED. "
        "Check in: EMCOMM CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE>"
    ),
    2: (
        "EXERCISE INJECT 2 — SIMULATED commercial power failure affecting parts of the area. "
        "Report power and communications status with EMCOMM SITREP <LOCATION> <STATUS>."
    ),
    3: (
        "EXERCISE INJECT 3 — SIMULATED cellular and Internet service degradation. "
        "Use RF mesh where practical and report connectivity/relay capability."
    ),
    4: (
        "EXERCISE INJECT 4 — SIMULATED served-agency request for communications status. "
        "All participating field locations send an EMCOMM SITREP."
    ),
    5: (
        "EXERCISE INJECT 5 — SIMULATED message-traffic phase. "
        "Use EMCOMM TRAFFIC <TO> <TEXT>. Use exercise data only."
    ),
    6: (
        "EXERCISE INJECT 6 — SIMULATED formal-message phase. "
        "Practice accurate written traffic / ICS-213 procedures per the local exercise plan."
    ),
    7: (
        "EXERCISE INJECT 7 — SIMULATED partial restoration of commercial communications. "
        "Report RF path, power source, and remaining communications gaps."
    ),
    8: (
        "EXERCISE EXERCISE — End of simulated exercise traffic. "
        "Send final SITREP if requested. Exercise Control will retain counts for after-action review."
    ),
}


def now_iso():
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def mode_label(mode):
    return "LIVE" if mode == "live" else "EXERCISE"


def default_state(mode="exercise"):
    return {
        "schema": 2,
        "version": __version__,
        "mode": mode,
        "exercise": EXERCISE_NAME,
        "started": None,
        "ended": None,
        "last_inject": 0,
        "participants": {},
        "sitreps": 0,
        "traffic_count": 0,
        "events": 0,
    }


def migrate_legacy_data():
    """Best-effort one-time migration from mm_arrl_set_data."""
    if STATE_FILE.exists() or not LEGACY_STATE_FILE.exists():
        return
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(LEGACY_STATE_FILE, STATE_FILE)
        if LEGACY_LOG_FILE.exists() and not LOG_FILE.exists():
            shutil.copy2(LEGACY_LOG_FILE, LOG_FILE)
    except Exception:
        pass


def load_state():
    migrate_legacy_data()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return default_state()
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            state = json.load(f)
        base = default_state(state.get("mode", "exercise") if isinstance(state, dict) else "exercise")
        if isinstance(state, dict):
            base.update(state)
        if base.get("mode") not in {"exercise", "live"}:
            base["mode"] = "exercise"
        base["schema"] = 2
        base["version"] = __version__
        base.setdefault("participants", {})
        return base
    except Exception:
        return default_state()


def save_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state["schema"] = 2
    state["version"] = __version__
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.replace(STATE_FILE)


def log_event(kind, from_node="", message="", extra=None):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    record = {
        "time": now_iso(),
        "mode": state.get("mode", "exercise"),
        "kind": kind,
        "from_node": str(from_node),
        "message": message,
    }
    if extra:
        record.update(extra)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def split_message(text, limit=MAX_LEN):
    text = normalize(text)
    if len(text) <= limit:
        return [text]
    parts = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            parts.append(remaining)
            break
        cut = remaining.rfind(" ", 0, limit + 1)
        if cut < 60:
            cut = limit
        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return parts


def emit(text):
    parts = split_message(text)
    if len(parts) == 1:
        print(json.dumps({"response": parts[0]}, ensure_ascii=False))
    else:
        print(json.dumps({"responses": parts}, ensure_ascii=False))


def sender_id():
    return normalize(
        os.getenv("FROM_ID")
        or os.getenv("FROM_NODE_ID")
        or os.getenv("FROM_NODE")
        or os.getenv("FROM_SHORT_NAME")
        or "unknown"
    )


def strip_prefix(message):
    m = re.match(r"^(EMCOMM|SET)\s+(.+)$", message, re.I)
    if not m:
        return "", message
    return m.group(1).upper(), m.group(2).strip()


def help_text(state):
    label = mode_label(state["mode"])
    base = (
        f"{label} commands: EMCOMM CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE> | "
        "EMCOMM SITREP <LOCATION> <STATUS> | EMCOMM TRAFFIC <TO> <TEXT> | "
        "EMCOMM STATUS | EMCOMM HELP"
    )
    if state["mode"] == "exercise":
        base += " | Legacy SET prefix also accepted."
    return base


def response_prefix(state):
    return "LIVE" if state["mode"] == "live" else "EXERCISE"


def handle_checkin(body, from_node, state):
    m = re.match(r"^CHECKIN\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+(.+))?$", body, re.I)
    if not m:
        return (
            f"{response_prefix(state)} format: EMCOMM CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE>. "
            "Example: EMCOMM CHECKIN W4ABC MIAMI-EOC BATTERY NCS"
        )
    callsign = m.group(1).upper()
    location = m.group(2).upper()
    power = m.group(3).upper()
    role = normalize(m.group(4) or "OPERATOR").upper()
    state["participants"][callsign] = {
        "node": str(from_node), "location": location, "power": power,
        "role": role, "time": now_iso(),
    }
    state["events"] += 1
    save_state(state)
    log_event("checkin", from_node, body, {
        "callsign": callsign, "location": location, "power": power, "role": role,
    })
    if state["mode"] == "exercise":
        return (
            f"EXERCISE ACK CHECKIN {callsign}. {location}; {power}; {role}. "
            f"Participant #{len(state['participants'])}. SIMULATED."
        )
    return (
        f"LIVE ACK CHECKIN {callsign}. {location}; {power}; {role}. "
        f"Station #{len(state['participants'])}. Logged."
    )


def handle_sitrep(body, from_node, state):
    m = re.match(r"^SITREP\s+(\S+)\s+(.+)$", body, re.I)
    if not m:
        return (
            f"{response_prefix(state)} format: EMCOMM SITREP <LOCATION> <STATUS>. "
            "Example: EMCOMM SITREP MIAMI-EOC BATTERY POWER; RF LINK GOOD"
        )
    location = m.group(1).upper()
    status = normalize(m.group(2))
    state["sitreps"] += 1
    state["events"] += 1
    save_state(state)
    log_event("sitrep", from_node, body, {
        "location": location, "status": status, "sitrep_number": state["sitreps"],
    })
    if state["mode"] == "exercise":
        return f"EXERCISE ACK SITREP #{state['sitreps']} from {location}. Logged. SIMULATED."
    return f"LIVE ACK SITREP #{state['sitreps']} from {location}. Logged."


def handle_traffic(body, from_node, state):
    m = re.match(r"^TRAFFIC\s+(\S+)\s+(.+)$", body, re.I)
    if not m:
        caution = "Use exercise data only." if state["mode"] == "exercise" else "Avoid sensitive information on open/untrusted RF networks."
        return f"{response_prefix(state)} format: EMCOMM TRAFFIC <TO> <TEXT>. {caution}"
    destination = m.group(1).upper()
    traffic_body = normalize(m.group(2))
    state["traffic_count"] += 1
    state["events"] += 1
    traffic_id = f"EX-{state['traffic_count']:03d}" if state["mode"] == "exercise" else f"EC-{state['traffic_count']:03d}"
    save_state(state)
    log_event("traffic", from_node, body, {
        "traffic_id": traffic_id, "to": destination, "body": traffic_body,
    })
    if state["mode"] == "exercise":
        return (
            f"EXERCISE ACK {traffic_id} to {destination}. Logged for exercise review; "
            "delivery to the named recipient is not guaranteed. SIMULATED."
        )
    return (
        f"LIVE ACK {traffic_id} to {destination}. Logged; "
        "this acknowledgment does not confirm delivery to the named recipient."
    )


def handle_status(state):
    if state["mode"] == "exercise":
        return (
            f"EXERCISE STATUS — participants {len(state['participants'])}; "
            f"SITREPs {state['sitreps']}; traffic {state['traffic_count']}; "
            f"last inject {state['last_inject']}. SIMULATED."
        )
    return (
        f"LIVE STATUS — stations {len(state['participants'])}; "
        f"SITREPs {state['sitreps']}; traffic {state['traffic_count']}."
    )


def handle_message():
    message = normalize(os.getenv("MESSAGE", ""))
    from_node = sender_id()
    state = load_state()
    if not message:
        emit(f"{mode_label(state['mode'])} EmComm Control ready. No MESSAGE received.")
        return
    prefix, body = strip_prefix(message)
    if prefix == "SET" and state["mode"] == "live":
        emit("LIVE mode: SET exercise prefix is disabled. Use EMCOMM commands.")
        return
    if not prefix:
        emit(help_text(state))
        return
    if re.match(r"^HELP\b", body, re.I):
        response = help_text(state)
    elif re.match(r"^CHECKIN\b", body, re.I):
        response = handle_checkin(body, from_node, state)
    elif re.match(r"^SITREP\b", body, re.I):
        response = handle_sitrep(body, from_node, state)
    elif re.match(r"^TRAFFIC\b", body, re.I):
        response = handle_traffic(body, from_node, state)
    elif re.match(r"^STATUS\b", body, re.I):
        response = handle_status(state)
    else:
        response = help_text(state)
    emit(response)


def set_mode(mode, confirm_live=False):
    state = load_state()
    if mode == "status":
        emit(f"EmComm Control mode: {mode_label(state['mode'])}.")
        return
    if mode == "live" and not confirm_live:
        emit(
            "LIVE mode not enabled. Re-run locally with --mode live --confirm-live "
            "to acknowledge that real operational traffic may be logged/transmitted."
        )
        return
    previous = state["mode"]
    state["mode"] = mode
    state["last_inject"] = 0
    if mode == "exercise":
        state["exercise"] = EXERCISE_NAME
    save_state(state)
    log_event("mode_change", "", f"{previous} -> {mode}")
    emit(f"EmComm Control mode changed to {mode_label(mode)}.")


def handle_inject(number):
    state = load_state()
    if state["mode"] != "exercise":
        emit("LIVE mode: simulated exercise injects are blocked.")
        return
    if number not in EXERCISE_INJECTS:
        emit(f"EXERCISE ERROR: unknown inject {number}. Valid injects: 1-{max(EXERCISE_INJECTS)}.")
        return
    if number == 1 and not state["started"]:
        state["started"] = now_iso()
    if number == max(EXERCISE_INJECTS):
        state["ended"] = now_iso()
    state["last_inject"] = number
    state["events"] += 1
    save_state(state)
    log_event("inject", "", EXERCISE_INJECTS[number], {"inject": number})
    emit(EXERCISE_INJECTS[number])


def handle_announce(text):
    state = load_state()
    text = normalize(text)
    if not text:
        emit("Announcement text is empty.")
        return
    label = "LIVE" if state["mode"] == "live" else "EXERCISE"
    suffix = "" if state["mode"] == "live" else " SIMULATED."
    message = f"{label} ANNOUNCEMENT — {text}{suffix}"
    state["events"] += 1
    save_state(state)
    log_event("announcement", "", text)
    emit(message)


def reset_operation():
    old = load_state()
    mode = old.get("mode", "exercise")
    state = default_state(mode)
    save_state(state)
    log_event("reset", "", f"{mode} operation state reset.")
    emit(f"{mode_label(mode)} EmComm Control state reset.")


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--mode", choices=["exercise", "live", "status"])
    parser.add_argument("--confirm-live", action="store_true", help="Required local confirmation when enabling LIVE mode.")
    parser.add_argument("--inject", type=int, help="Send a numbered exercise inject (EXERCISE mode only).")
    parser.add_argument("--announce", help="Send an operator-supplied announcement in the current mode.")
    parser.add_argument("--reset", action="store_true", help="Reset counters/state while preserving current mode.")
    args = parser.parse_args()
    selected = sum([args.mode is not None, args.inject is not None, args.announce is not None, args.reset])
    if selected > 1:
        emit("Choose only one administrative action at a time.")
        return
    if args.mode is not None:
        set_mode(args.mode, args.confirm_live)
    elif args.inject is not None:
        handle_inject(args.inject)
    elif args.announce is not None:
        handle_announce(args.announce)
    elif args.reset:
        reset_operation()
    else:
        handle_message()


if __name__ == "__main__":
    main()
