#!/usr/bin/env python3
# mm_meta:
#   name: ARRL SET Exercise Control
#   emoji: 🚨
#   language: Python
__version__ = "1.0.0"

"""
ARRL SET Exercise Control bot for MeshMonitor.

Install:
  /data/scripts/mm_arrl_set.py

Auto Responder:
  Pattern: ^SET\b
  Response type: Script
  Script: /data/scripts/mm_arrl_set.py

Timed Events:
  Script: /data/scripts/mm_arrl_set.py
  Arguments: --inject <number>

All exercise-generated radio traffic is explicitly marked SIMULATED/EXERCISE.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "mm_arrl_set_data"
STATE_FILE = DATA_DIR / "state.json"
LOG_FILE = DATA_DIR / "traffic.jsonl"

TZ_NAME = os.getenv("SET_TZ", "America/New_York")
try:
    LOCAL_TZ = ZoneInfo(TZ_NAME)
except Exception:
    LOCAL_TZ = ZoneInfo("UTC")

EXERCISE_NAME = os.getenv("SET_NAME", "ARRL SET 2026")
MAX_LEN = 190

INJECTS = {
    1: (
        "EXERCISE EXERCISE — ARRL SET has begun. "
        "All traffic is SIMULATED. Check in: SET CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE>"
    ),
    2: (
        "EXERCISE INJECT 2 — SIMULATED commercial power failure affecting parts of the area. "
        "Stations: report EPOWER/BATTERY/GENERATOR using SET SITREP <LOCATION> <STATUS>."
    ),
    3: (
        "EXERCISE INJECT 3 — SIMULATED cellular and Internet service is degraded. "
        "Use RF mesh only where practical. Report connectivity and relay capability with SET SITREP."
    ),
    4: (
        "EXERCISE INJECT 4 — SIMULATED served agency requests communications status from all field locations. "
        "Send SET SITREP <LOCATION> <STATUS>."
    ),
    5: (
        "EXERCISE INJECT 5 — SIMULATED welfare/message traffic is now being accepted. "
        "Use SET TRAFFIC <TO> <TEXT>. Do not transmit real personal or medical information."
    ),
    6: (
        "EXERCISE INJECT 6 — SIMULATED formal-message phase. "
        "Operators should practice accurate written traffic/ICS-213 procedures per local SET plan."
    ),
    7: (
        "EXERCISE INJECT 7 — SIMULATED partial restoration of commercial communications. "
        "Report current RF path, power source, and any remaining communications gaps."
    ),
    8: (
        "EXERCISE EXERCISE — End of SET traffic. Send final SITREP if requested. "
        "Thank you. Exercise Control will retain check-in and traffic counts for the after-action review."
    ),
}


def now_iso():
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def default_state():
    return {
        "exercise": EXERCISE_NAME,
        "started": None,
        "ended": None,
        "last_inject": 0,
        "participants": {},
        "sitreps": 0,
        "traffic_count": 0,
        "events": 0,
    }


def load_state():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return default_state()
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            state = json.load(f)
        base = default_state()
        base.update(state)
        return base
    except Exception:
        return default_state()


def save_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    tmp.replace(STATE_FILE)


def log_event(kind, from_node="", message="", extra=None):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "time": now_iso(),
        "kind": kind,
        "from_node": str(from_node),
        "message": message,
    }
    if extra:
        record.update(extra)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def split_message(text, limit=MAX_LEN):
    """Split long text into MeshMonitor-safe response chunks."""
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


def cmd_help():
    return (
        "EXERCISE commands: SET CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE> | "
        "SET SITREP <LOCATION> <STATUS> | SET TRAFFIC <TO> <TEXT> | SET STATUS | SET HELP"
    )


def handle_checkin(message, from_node, state):
    # Location is one token by design; use hyphens, e.g. MIAMI-EOC or SHELTER-12.
    m = re.match(
        r"^SET\s+CHECKIN\s+(\S+)\s+(\S+)\s+(\S+)(?:\s+(.+))?$",
        message,
        re.I,
    )
    if not m:
        return (
            "EXERCISE format: SET CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE>. "
            "Example: SET CHECKIN W4ABC MIAMI-EOC BATTERY NCS"
        )

    callsign = m.group(1).upper()
    location = m.group(2).upper()
    power = m.group(3).upper()
    role = normalize(m.group(4) or "OPERATOR").upper()

    state["participants"][callsign] = {
        "node": str(from_node),
        "location": location,
        "power": power,
        "role": role,
        "time": now_iso(),
    }
    state["events"] += 1
    save_state(state)
    log_event(
        "checkin",
        from_node,
        message,
        {"callsign": callsign, "location": location, "power": power, "role": role},
    )

    return (
        f"EXERCISE ACK CHECKIN {callsign}. Location {location}; power {power}; role {role}. "
        f"Participant #{len(state['participants'])}. SIMULATED TRAFFIC."
    )


def handle_sitrep(message, from_node, state):
    m = re.match(r"^SET\s+SITREP\s+(\S+)\s+(.+)$", message, re.I)
    if not m:
        return (
            "EXERCISE format: SET SITREP <LOCATION> <STATUS>. "
            "Example: SET SITREP MIAMI-EOC BATTERY POWER; RF LINK GOOD; INTERNET DOWN"
        )

    location = m.group(1).upper()
    status = normalize(m.group(2))

    state["sitreps"] += 1
    state["events"] += 1
    save_state(state)
    log_event(
        "sitrep",
        from_node,
        message,
        {"location": location, "status": status, "sitrep_number": state["sitreps"]},
    )

    return f"EXERCISE ACK SITREP #{state['sitreps']} from {location}. Logged by Exercise Control. SIMULATED."


def handle_traffic(message, from_node, state):
    m = re.match(r"^SET\s+TRAFFIC\s+(\S+)\s+(.+)$", message, re.I)
    if not m:
        return (
            "EXERCISE format: SET TRAFFIC <TO> <TEXT>. "
            "Use simulated content only; do not send real PII, medical, or emergency information."
        )

    destination = m.group(1).upper()
    body = normalize(m.group(2))

    state["traffic_count"] += 1
    state["events"] += 1
    traffic_id = f"SET-{state['traffic_count']:03d}"
    save_state(state)

    log_event(
        "traffic",
        from_node,
        message,
        {"traffic_id": traffic_id, "to": destination, "body": body},
    )

    return (
        f"EXERCISE ACK {traffic_id} to {destination}. Logged for exercise review; "
        "this bot does not guarantee delivery to the named recipient. SIMULATED."
    )


def handle_status(state):
    return (
        f"EXERCISE STATUS — participants {len(state['participants'])}; "
        f"SITREPs {state['sitreps']}; traffic {state['traffic_count']}; "
        f"last inject {state['last_inject']}. SIMULATED."
    )


def handle_message():
    message = normalize(os.getenv("MESSAGE", ""))
    from_node = os.getenv("FROM_NODE", "unknown")
    state = load_state()

    if not message:
        emit("EXERCISE script ready. No MESSAGE received.")
        return

    if re.match(r"^SET\s+HELP\b", message, re.I):
        response = cmd_help()
    elif re.match(r"^SET\s+CHECKIN\b", message, re.I):
        response = handle_checkin(message, from_node, state)
    elif re.match(r"^SET\s+SITREP\b", message, re.I):
        response = handle_sitrep(message, from_node, state)
    elif re.match(r"^SET\s+TRAFFIC\b", message, re.I):
        response = handle_traffic(message, from_node, state)
    elif re.match(r"^SET\s+STATUS\b", message, re.I):
        response = handle_status(state)
    else:
        response = cmd_help()

    emit(response)


def handle_inject(number):
    state = load_state()

    if number not in INJECTS:
        emit(f"EXERCISE ERROR: unknown inject {number}. Valid injects: 1-{max(INJECTS)}.")
        return

    if number == 1 and not state["started"]:
        state["started"] = now_iso()
    if number == max(INJECTS):
        state["ended"] = now_iso()

    state["last_inject"] = number
    state["events"] += 1
    save_state(state)
    log_event("inject", "", INJECTS[number], {"inject": number})

    emit(INJECTS[number])


def reset_exercise():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = default_state()
    save_state(state)
    log_event("reset", "", "Exercise state reset.")
    emit("EXERCISE CONTROL: SET state reset. Ready for a new simulated exercise.")


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--inject", type=int, help="Transmit a numbered SET exercise inject.")
    parser.add_argument("--reset", action="store_true", help="Reset exercise counters/state.")
    args = parser.parse_args()

    if args.reset:
        reset_exercise()
    elif args.inject is not None:
        handle_inject(args.inject)
    else:
        handle_message()


if __name__ == "__main__":
    main()
