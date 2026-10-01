#!/usr/bin/env python3
# mm_meta:
#   name: EmComm Control
#   emoji: 🚨
#   language: Python
__version__ = "2.3.0"

"""
EmComm Control for MeshMonitor.

Dual-mode emergency-communications control:
- EXERCISE mode: SET/drill traffic, simulated injects, explicit TEST/EXERCISE/SIMULATED labeling.
- LIVE mode: real-world operator-entered check-ins, SITREPs, and message logging.
- Suitable for emergency operations center (EOC) workflows at city/municipal, county/regional, and state levels.

Traffic classes:
- TACTICAL: CHECKIN, CHECKOUT, SITREP, STATUS, HELP (lightweight, unchanged).
- FORMAL:   TRAFFIC, using a compressed ICS-213-compatible field structure with
            NTS-style traffic handling (precedence, TEST marking, references,
            accurate relay). This is NOT an official FEMA ICS-213, ARRL NTS,
            or Winlink implementation; see docs/formal-traffic.md.

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
  mm_emcomm_control.py --checkout <CALLSIGN>  # local roster correction
  mm_emcomm_control.py --export [DIR]     # after-action CSV + summary export
  mm_emcomm_control.py --reset

Operator panel:
  mm_emcomm_panel.py --open

Safety:
- LIVE mode can only be enabled locally, never by an inbound mesh message.
- Exercise injects are blocked in LIVE mode.
- LIVE mode never fabricates incident conditions and never adds TEST markings;
  it only acknowledges/logs operator-supplied information.
"""

import argparse
import csv
import json
import os
import re
import shutil
from dataclasses import dataclass, field
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


def _int_env(name, default, minimum=1):
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


# Default hard limit per emitted mesh message. 133 characters is a conservative
# common limit for Meshtastic and MeshCore text workflows; networks differ, so
# it remains overridable. 120 ASCII characters is the recommended operating target.
DEFAULT_MAX_LEN = 133
DEFAULT_RECOMMENDED_LEN = 120
MAX_LEN = _int_env("MM_EMCOMM_MAXLEN", DEFAULT_MAX_LEN, minimum=60)
RECOMMENDED_LEN = _int_env("MM_EMCOMM_RECOMMENDED_LEN", DEFAULT_RECOMMENDED_LEN)

# Multipart formal traffic
MAX_PARTS = 9
PART_TIMEOUT_SECONDS = _int_env("MM_EMCOMM_PART_TIMEOUT", 1800)

# Exercise Field 7 handling: "validate" (default) rejects formal exercise traffic
# whose Field 7 does not begin with TEST MESSAGE; "auto" prepends it instead.
# Either way this only ever applies in EXERCISE mode.
TEST_PREFIX_MODE = os.getenv("MM_EMCOMM_TEST_PREFIX", "validate").strip().lower()
TEST_MESSAGE_PREFIX = "TEST MESSAGE"


# ---------------------------------------------------------------------------
# Generic exercise configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "exercise_name": "Emergency Communications Exercise",
    "exercise_id": "",
    "exercise_type": "",
    "organization": "",
    "incident_name": "",
    "start": "",
    "end": "",
    "local_instructions": "",
}

# Environment variables override the optional JSON config file.
CONFIG_ENV = {
    "exercise_name": ("MM_EMCOMM_EXERCISE_NAME", "SET_NAME"),
    "exercise_id": ("MM_EMCOMM_EXERCISE_ID",),
    "exercise_type": ("MM_EMCOMM_EXERCISE_TYPE",),
    "organization": ("MM_EMCOMM_ORGANIZATION",),
    "incident_name": ("MM_EMCOMM_INCIDENT_NAME",),
    "start": ("MM_EMCOMM_EXERCISE_START",),
    "end": ("MM_EMCOMM_EXERCISE_END",),
    "local_instructions": ("MM_EMCOMM_LOCAL_INSTRUCTIONS",),
}


def config_path():
    return Path(os.getenv("MM_EMCOMM_CONFIG", str(SCRIPT_DIR / "mm_emcomm_config.json")))


def load_config(path=None):
    """Defaults <- optional JSON config file <- environment variables."""
    cfg = dict(DEFAULT_CONFIG)
    path = Path(path) if path else config_path()
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for key in DEFAULT_CONFIG:
                    if data.get(key) is not None:
                        cfg[key] = str(data[key]).strip()
        except Exception:
            pass
    for key, names in CONFIG_ENV.items():
        for name in names:
            value = os.getenv(name)
            if value:
                cfg[key] = value.strip()
                break
    if not cfg["exercise_name"]:
        cfg["exercise_name"] = DEFAULT_CONFIG["exercise_name"]
    return cfg


CONFIG = load_config()
EXERCISE_NAME = CONFIG["exercise_name"]


# ---------------------------------------------------------------------------
# Exercise injects (EXERCISE mode only). Each entry is a list of mesh messages;
# emit() further splits any message that exceeds the configured limit.
# ---------------------------------------------------------------------------

FORMAL_EXAMPLE = "EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL"


def exercise_injects(cfg=None):
    name = (cfg or CONFIG)["exercise_name"].upper()
    return {
        1: [
            f"TEST EXERCISE INJECT 1 - {name} HAS BEGUN. ALL TRAFFIC IS SIMULATED.",
            "CHECK IN: EMCOMM CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE>",
        ],
        2: [
            "TEST EXERCISE INJECT 2 - SIMULATED COMMERCIAL POWER FAILURE IN PARTS OF THE AREA. "
            "REPORT STATUS: EMCOMM SITREP <LOCATION> <STATUS>",
        ],
        3: [
            "TEST EXERCISE INJECT 3 - SIMULATED CELL AND INTERNET DEGRADATION. "
            "USE RF MESH. REPORT CONNECTIVITY AND RELAY CAPABILITY.",
        ],
        4: [
            "TEST EXERCISE INJECT 4 - SIMULATED SERVED-AGENCY REQUEST FOR COMMS STATUS. "
            "ALL FIELD LOCATIONS SEND EMCOMM SITREP.",
        ],
        5: [
            "TEST EXERCISE INJECT 5 - SIMULATED TACTICAL TRAFFIC PHASE. "
            "SEND SHORT UPDATES WITH EMCOMM SITREP. USE EXERCISE DATA ONLY.",
        ],
        6: [
            "TEST EXERCISE INJECT 6 - FORMAL TRAFFIC PHASE. "
            "ORIGINATE AN ICS-213 / NTS-STYLE TEST MESSAGE USING FIELDS 2, 3, 4 AND 7.",
            f"FIELD 7 MUST BEGIN TEST MESSAGE. EX: {FORMAL_EXAMPLE}",
        ],
        7: [
            "TEST EXERCISE INJECT 7 - SIMULATED PARTIAL RESTORATION OF COMMERCIAL COMMS. "
            "REPORT RF PATH, POWER SOURCE, AND REMAINING GAPS.",
        ],
        8: [
            f"TEST EXERCISE INJECT 8 - END OF SIMULATED TRAFFIC FOR {name}.",
            "SEND FINAL SITREP IF REQUESTED. COUNTS RETAINED FOR AFTER-ACTION REVIEW. END TEST.",
        ],
    }


EXERCISE_INJECTS = exercise_injects()


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

def now_iso():
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def normalize(text):
    return re.sub(r"\s+", " ", (text or "").strip())


def mode_label(mode):
    return "LIVE" if mode == "live" else "EXERCISE"


def is_exercise(state):
    """Central safety check: TEST/simulated marking is only ever applied in EXERCISE mode."""
    return state.get("mode") != "live"


def default_state(mode="exercise"):
    return {
        "schema": 3,
        "version": __version__,
        "mode": mode,
        "exercise": EXERCISE_NAME,
        "started": None,
        "ended": None,
        "last_inject": 0,
        "participants": {},
        "sitreps": 0,
        "traffic_count": 0,
        "relays": 0,
        "events": 0,
        "pending_traffic": {},
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
        base["schema"] = 3
        base["version"] = __version__
        if not isinstance(base.get("participants"), dict):
            base["participants"] = {}
        if not isinstance(base.get("pending_traffic"), dict):
            base["pending_traffic"] = {}
        return base
    except Exception:
        return default_state()


def save_state(state):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state["schema"] = 3
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


def length_report(text, limit=None, recommended=None):
    """Character-count status used by the panel counter and tests."""
    limit = limit or MAX_LEN
    recommended = recommended or RECOMMENDED_LEN
    length = len(text or "")
    over_limit = length > limit
    over_recommended = length > recommended and not over_limit
    warning = ""
    if over_limit:
        warning = "Exceeds configured limit; will be sent as multipart."
    elif over_recommended:
        warning = "Recommended LoRa target exceeded."
    return {
        "length": length, "limit": limit, "recommended": recommended,
        "over_limit": over_limit, "over_recommended": over_recommended, "warning": warning,
    }


def _wrap(text, limit):
    """Split text at word boundaries into chunks no longer than limit."""
    chunks = []
    remaining = normalize(text)
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind(" ", 0, limit + 1)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return chunks


def split_message(text, limit=None):
    """Split one response into numbered parts (" [1/2]") when it exceeds the limit."""
    limit = limit or MAX_LEN
    text = normalize(text)
    if len(text) <= limit:
        return [text]
    suffix_len = len(" [9/9]")
    chunks = _wrap(text, limit - suffix_len)
    total = len(chunks)
    return [f"{chunk} [{i}/{total}]" for i, chunk in enumerate(chunks, 1)]


def emit(text):
    """Print a MeshMonitor JSON response. Accepts a string or a list of messages."""
    messages = text if isinstance(text, (list, tuple)) else [text]
    parts = []
    for message in messages:
        if normalize(message):
            parts.extend(split_message(message))
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


def read_log_records(upgrade=True):
    """Return all JSONL log records; older traffic records are upgraded in memory only."""
    rows = []
    if not LOG_FILE.exists():
        return rows
    with LOG_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if isinstance(record, dict):
                rows.append(upgrade_traffic_record(record) if upgrade else record)
    return rows


# ---------------------------------------------------------------------------
# Formal traffic: precedence
# ---------------------------------------------------------------------------

# NTS precedences (ARRL): EMERGENCY (always spelled out), PRIORITY (P),
# WELFARE (W), ROUTINE (R). Normalized internally to R / P / W / EMERGENCY.
PRECEDENCE_TOKENS = {
    "R": "R", "ROUTINE": "R",
    "P": "P", "PRIORITY": "P",
    "W": "W", "WELFARE": "W",
    "EMERGENCY": "EMERGENCY",
}
PRECEDENCE_NAMES = {"R": "ROUTINE", "P": "PRIORITY", "W": "WELFARE", "EMERGENCY": "EMERGENCY"}

# Legacy v2.2 syntax precedence words. IMMEDIATE is not an NTS precedence; it is
# mapped to P (PRIORITY) for compatibility, and the original word is logged in
# legacy_precedence. It is never mapped to EMERGENCY.
LEGACY_PRECEDENCE_MAP = {"ROUTINE": "R", "PRIORITY": "P", "IMMEDIATE": "P"}


def precedence_display(precedence, test_traffic):
    """Render precedence as it appears in a preamble, e.g. 'TEST P' or 'EMERGENCY'."""
    return f"TEST {precedence}" if test_traffic else precedence


# ---------------------------------------------------------------------------
# Formal traffic: ICS-213 field model and parsing
# ---------------------------------------------------------------------------

ICS_FIELDS = {
    "1": ("field_1_incident", "INCIDENT NAME"),
    "2": ("field_2_to", "TO"),
    "3": ("field_3_from", "FROM"),
    "4": ("field_4_subject", "SUBJECT"),
    "5": ("field_5_date", "DATE"),
    "6": ("field_6_time", "TIME"),
    "7": ("field_7_message", "MESSAGE"),
    "8": ("field_8_approved_by", "APPROVED BY"),
}
REQUIRED_FIELDS = ("2", "3", "4", "7")
FIELD_ORDER = ("RE", "1", "2", "3", "4", "5", "6", "7", "8")
TRAFFIC_ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9-]{0,15}$")
PART_RE = re.compile(r"^([1-9])/([1-9])$")
FIELD_MARKER_RE = re.compile(r"(?<!\S)(RE|[1-8]):", re.I)


class TrafficError(ValueError):
    """Operator-correctable formal traffic error (short, mesh-friendly text)."""


@dataclass
class FormalTraffic:
    precedence: str = "R"
    test_traffic: bool = False
    fields: dict = field(default_factory=dict)  # "1".."8" -> value
    reply_to: str = ""
    syntax: str = "ics213"
    legacy_precedence: str = ""


def parse_field_segments(text):
    """Split 'RE:X 2:EOC 3:FIELD1 7:TEXT 8:OP' into [(key, value), ...].

    Field 7 consumes the rest of the text so message content may contain things
    like '1:2' or '2:30'; only a trailing 8: (followed by a non-digit, so '8:00'
    stays message text) ends Field 7.
    """
    text = normalize(text)
    markers = list(FIELD_MARKER_RE.finditer(text))
    if not markers:
        raise TrafficError("NO FIELDS FOUND")
    if text[:markers[0].start()].strip(" |"):
        raise TrafficError(f"UNEXPECTED TEXT BEFORE {markers[0].group(0).upper()}")
    bounds = []
    for m in markers:
        key = m.group(1).upper()
        if bounds and bounds[-1][0] == "7":
            continue  # inside Field 7; trailing 8: handled below
        bounds.append((key, m.start(), m.end()))
    if bounds[-1][0] == "7":
        start7 = bounds[-1][2]
        field8 = [
            m for m in markers
            if m.start() > start7 and m.group(1) == "8" and not text[m.end():m.end() + 1].isdigit()
        ]
        if field8:
            last = field8[-1]
            bounds.append(("8", last.start(), last.end()))
    segments = []
    for i, (key, start, value_start) in enumerate(bounds):
        end = bounds[i + 1][1] if i + 1 < len(bounds) else len(text)
        value = text[value_start:end].strip().strip("|").strip()
        segments.append((key, value))
    return segments


def merge_segments(segment_lists):
    """Merge field segments from one or more parts; repeated keys across parts are continuations."""
    merged = {}
    for segments in segment_lists:
        seen = set()
        for key, value in segments:
            if key in seen:
                raise TrafficError(f"FIELD {key} REPEATED")
            seen.add(key)
            merged[key] = f"{merged[key]} {value}".strip() if key in merged else value
    return merged


def parse_traffic_header(tokens):
    """Parse '[TEST] <PRECEDENCE>' from the start of a token list. Returns (precedence, test, rest)."""
    test = False
    if tokens and tokens[0].upper() == "TEST":
        test = True
        tokens = tokens[1:]
    if not tokens or tokens[0].upper() not in PRECEDENCE_TOKENS:
        raise TrafficError("PRECEDENCE MUST BE R, P, W OR EMERGENCY")
    return PRECEDENCE_TOKENS[tokens[0].upper()], test, tokens[1:]


def build_formal(precedence, test, merged):
    traffic = FormalTraffic(precedence=precedence, test_traffic=test)
    reply = merged.pop("RE", "")
    if reply:
        reply = reply.upper()
        if not TRAFFIC_ID_RE.match(reply):
            raise TrafficError("RE: MUST BE ONE TRAFFIC ID, E.G. RE:EX-001")
        traffic.reply_to = reply
    traffic.fields = {k: v for k, v in merged.items() if k in ICS_FIELDS}
    return traffic


def is_structured_traffic(args):
    """True when TRAFFIC arguments use the ICS-213 / NTS-style form (vs legacy <TO> <TEXT>)."""
    tokens = args.split()
    if not tokens:
        return False
    first = tokens[0].upper()
    return bool(PART_RE.match(first)) or first == "TEST" or first in PRECEDENCE_TOKENS


def parse_structured(args):
    """Parse '[TEST] <PREC> [RE:<ID>] 2:.. 3:.. 4:.. 7:..' (single-part)."""
    precedence, test, rest = parse_traffic_header(args.split())
    if not rest:
        raise TrafficError("MISSING FIELDS 2, 3, 4 AND 7")
    return build_formal(precedence, test, merge_segments([parse_field_segments(" ".join(rest))]))


def parse_legacy(args):
    """Parse legacy v2.2 syntax '<TO> [ROUTINE|PRIORITY|IMMEDIATE] <TEXT>'."""
    m = re.match(r"^(\S+)\s+(.+)$", normalize(args))
    if not m:
        raise TrafficError("LEGACY FORMAT: EMCOMM TRAFFIC <TO> [ROUTINE|PRIORITY|IMMEDIATE] <TEXT>")
    destination = m.group(1).upper()
    rest = m.group(2)
    legacy_word = "ROUTINE"
    pm = re.match(r"^(ROUTINE|PRIORITY|IMMEDIATE)\s+(.+)$", rest, re.I)
    if pm:
        legacy_word = pm.group(1).upper()
        rest = pm.group(2)
    return FormalTraffic(
        precedence=LEGACY_PRECEDENCE_MAP[legacy_word],
        fields={"2": destination, "7": normalize(rest)},
        syntax="legacy",
        legacy_precedence=legacy_word if pm else "",
    )


def validate_formal(traffic, exercise, auto_prefix=None):
    """Validate and apply EXERCISE TEST marking. Returns a list of error strings.

    In EXERCISE mode the traffic is always flagged as TEST traffic, and Field 7
    must begin TEST MESSAGE (or is auto-prefixed when configured). In LIVE mode
    nothing is ever added; operator-supplied text is kept exactly as sent.
    """
    if auto_prefix is None:
        auto_prefix = TEST_PREFIX_MODE == "auto"
    errors = []
    if traffic.syntax != "legacy":
        missing = [k for k in REQUIRED_FIELDS if not traffic.fields.get(k)]
        if missing:
            names = ", ".join(f"{k}:{ICS_FIELDS[k][1]}" for k in missing)
            errors.append(f"MISSING {names}")
    if exercise:
        traffic.test_traffic = True
        message = traffic.fields.get("7", "")
        if traffic.syntax != "legacy" and message and not message.upper().startswith(TEST_MESSAGE_PREFIX):
            if auto_prefix:
                traffic.fields["7"] = f"{TEST_MESSAGE_PREFIX} {message}"
            else:
                errors.append("FIELD 7 MUST BEGIN TEST MESSAGE")
    return errors


# ---------------------------------------------------------------------------
# Formal traffic: serialization and multipart packing
# ---------------------------------------------------------------------------

def ordered_segments(traffic):
    segments = []
    if traffic.reply_to:
        segments.append(("RE", traffic.reply_to))
    for key in FIELD_ORDER[1:]:
        value = traffic.fields.get(key)
        if value:
            segments.append((key, value))
    return segments


def pack_segments(segments, header_fn, sep, limit):
    """Pack field segments into parts no longer than limit.

    header_fn(k, n) returns the header for part k of n (n=0 means single part).
    Non-Field-7 segments move whole to a new part when possible; long values are
    split at word boundaries and repeat their field key in the next part so the
    receiver can reconstruct every field.
    """
    single = header_fn(1, 0) + "".join(f"{sep}{k}:{v}" for k, v in segments)
    if len(single) <= limit:
        return [single]

    parts = []  # list of body strings (without headers)

    def room(k):
        return limit - len(header_fn(k, MAX_PARTS))

    cur = ""
    for key, value in segments:
        piece = f"{sep}{key}:{value}"
        k = len(parts) + 1
        if len(cur) + len(piece) <= room(k):
            cur += piece
            continue
        if key != "7" and cur and len(piece) <= room(k + 1):
            parts.append(cur)
            cur = piece
            continue
        words = value.split(" ")
        label = f"{sep}{key}:"
        if len(cur) + len(label) + len(words[0]) > room(len(parts) + 1) and cur:
            parts.append(cur)
            cur = ""
        cur += label
        first_word = True
        while words:
            word = words[0]
            joiner = "" if first_word else " "
            avail = room(len(parts) + 1)
            if len(cur) + len(joiner) + len(word) <= avail:
                cur += joiner + word
                words.pop(0)
                first_word = False
                continue
            if first_word:
                # single word longer than the remaining room: hard cut
                take = max(1, avail - len(cur))
                cur += word[:take]
                words[0] = word[take:]
            parts.append(cur)
            cur = label
            first_word = True
        # loop ends with cur holding the tail of this field
    if cur:
        parts.append(cur)
    total = len(parts)
    if total > MAX_PARTS:
        raise TrafficError(f"MESSAGE TOO LONG: MORE THAN {MAX_PARTS} PARTS")
    return [header_fn(k, total) + body for k, body in enumerate(parts, 1)]


def serialize_traffic(traffic, traffic_id, limit=None):
    """Canonical relay text, e.g. 'TEST P | EX-003 | 2:EOC | 3:FIELD1 | 4:COMMS | 7:TEST MESSAGE ...'.

    Field content is never altered; multipart output uses 'EX-003 1/2' headers.
    """
    limit = limit or MAX_LEN
    prec = precedence_display(traffic.precedence, traffic.test_traffic)

    def header(k, n):
        if n == 0:
            return f"{prec} | {traffic_id}"
        if k == 1:
            return f"{prec} | {traffic_id} {k}/{n}"
        return f"{traffic_id} {k}/{n}"

    return pack_segments(ordered_segments(traffic), header, " | ", limit)


def compose_traffic_command(traffic, prefix="EMCOMM", limit=None):
    """Build the compact mesh command(s) an operator sends, multipart when needed."""
    limit = limit or MAX_LEN
    prec = precedence_display(traffic.precedence, traffic.test_traffic)

    def header(k, n):
        if n == 0:
            return f"{prefix} TRAFFIC {prec}"
        if k == 1:
            return f"{prefix} TRAFFIC {k}/{n} {prec}"
        return f"{prefix} TRAFFIC {k}/{n}"

    return pack_segments(ordered_segments(traffic), header, " ", limit)


SERIAL_FIRST_RE = re.compile(
    r"^(?P<prec>(?:TEST\s+)?[A-Z]+)\s*\|\s*(?P<id>[A-Z0-9][A-Z0-9-]*)(?:\s+(?P<k>[1-9])/(?P<n>[1-9]))?\s*\|\s*(?P<rest>.*)$",
    re.I,
)
SERIAL_CONT_RE = re.compile(r"^(?P<id>[A-Z0-9][A-Z0-9-]*)\s+(?P<k>[1-9])/(?P<n>[1-9])\s*\|\s*(?P<rest>.*)$", re.I)


def reassemble_serialized(parts):
    """Rebuild (traffic_id, FormalTraffic) from canonical serialized part(s)."""
    parts = [normalize(p) for p in parts if normalize(p)]
    if not parts:
        raise TrafficError("NO PARTS")
    first = SERIAL_FIRST_RE.match(parts[0])
    if not first:
        raise TrafficError("UNRECOGNIZED FIRST PART")
    traffic_id = first.group("id").upper()
    total = int(first.group("n") or 1)
    if len(parts) != total:
        raise TrafficError(f"EXPECTED {total} PARTS, GOT {len(parts)}")
    precedence, test, _ = parse_traffic_header(first.group("prec").split())
    segment_lists = [parse_field_segments(first.group("rest"))]
    for index, part in enumerate(parts[1:], 2):
        m = SERIAL_CONT_RE.match(part)
        if not m or m.group("id").upper() != traffic_id or int(m.group("k")) != index or int(m.group("n")) != total:
            raise TrafficError(f"PART {index}/{total} DOES NOT MATCH {traffic_id}")
        segment_lists.append(parse_field_segments(m.group("rest")))
    return traffic_id, build_formal(precedence, test, merge_segments(segment_lists))


# ---------------------------------------------------------------------------
# Formal traffic: log records
# ---------------------------------------------------------------------------

def traffic_record(traffic, traffic_id, mode, from_node, raw_input, parts=1, reply_found=None):
    received = now_iso()
    record = {
        "record_schema": 3,
        "traffic_id": traffic_id,
        "mode": mode,
        "syntax": traffic.syntax,
        "precedence": traffic.precedence,
        "legacy_precedence": traffic.legacy_precedence,
        "test_traffic": traffic.test_traffic,
        "reply_to": traffic.reply_to,
        "from_node": str(from_node),
        "received_time": received,
        "raw_input": raw_input,
        "parts": parts,
        # v2.2 compatibility columns
        "to": traffic.fields.get("2", ""),
        "body": traffic.fields.get("7", ""),
    }
    for key, (name, _) in ICS_FIELDS.items():
        record[name] = traffic.fields.get(key, "")
    if reply_found is not None:
        record["reply_found"] = reply_found
    return record


def upgrade_traffic_record(record):
    """Map a pre-2.3 traffic record onto the structured field model (in memory only)."""
    if record.get("kind") != "traffic" or "field_2_to" in record:
        return record
    upgraded = dict(record)
    legacy_word = str(record.get("precedence") or "ROUTINE").upper()
    upgraded.update({
        "record_schema": 2,
        "syntax": "legacy",
        "precedence": LEGACY_PRECEDENCE_MAP.get(legacy_word, "R"),
        "legacy_precedence": legacy_word,
        "test_traffic": record.get("mode", "exercise") != "live",
        "reply_to": "",
        "received_time": record.get("time", ""),
        "raw_input": record.get("message", ""),
    })
    for key, (name, _) in ICS_FIELDS.items():
        upgraded[name] = ""
    upgraded["field_2_to"] = record.get("to", "")
    upgraded["field_7_message"] = record.get("body", "")
    return upgraded


def find_traffic(traffic_id):
    """Return the most recent logged traffic record with this ID (IDs restart after reset)."""
    found = None
    for record in read_log_records():
        if record.get("kind") == "traffic" and record.get("traffic_id") == traffic_id:
            found = record
    return found


def traffic_from_record(record):
    fields = {}
    for key, (name, _) in ICS_FIELDS.items():
        if record.get(name):
            fields[key] = record[name]
    return FormalTraffic(
        precedence=record.get("precedence", "R"),
        test_traffic=bool(record.get("test_traffic")),
        fields=fields,
        reply_to=record.get("reply_to", ""),
        syntax=record.get("syntax", "ics213"),
        legacy_precedence=record.get("legacy_precedence", ""),
    )


# ---------------------------------------------------------------------------
# Mesh command handlers
# ---------------------------------------------------------------------------

def help_text(state):
    """Concise, multi-message help: tactical and formal are listed separately."""
    label = mode_label(state["mode"])
    messages = [
        f"{label} TACTICAL: EMCOMM CHECKIN <CALL> <LOC> <POWER> <ROLE> | CHECKOUT <CALL> | "
        "SITREP <LOC> <STATUS> | STATUS | HELP",
    ]
    if is_exercise(state):
        messages.append(f"FORMAL: {FORMAL_EXAMPLE}")
        messages.append(
            "EXERCISE: FIELD 7 MUST BEGIN TEST MESSAGE. PREC R/P/W/EMERGENCY. "
            "OPTIONAL 1: 5: 6: 8: RE:<ID>. RELAY <ID>. SET PREFIX OK."
        )
        if CONFIG.get("local_instructions"):
            messages.append(f"LOCAL: {CONFIG['local_instructions']}")
    else:
        messages.append("FORMAL: EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:COMMS OPERATIONAL")
        messages.append("PREC R/P/W/EMERGENCY. OPTIONAL 1: 5: 6: 8: RE:<ID>. RELAY: EMCOMM RELAY <ID>")
    return messages


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
    if is_exercise(state):
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
    if is_exercise(state):
        return f"EXERCISE ACK SITREP #{state['sitreps']} from {location}. Logged. SIMULATED."
    return f"LIVE ACK SITREP #{state['sitreps']} from {location}. Logged."


def traffic_usage(state):
    if is_exercise(state):
        return "USE: EMCOMM TRAFFIC P 2:TO 3:FROM 4:SUBJ 7:TEST MESSAGE TEXT"
    return "USE: EMCOMM TRAFFIC P 2:TO 3:FROM 4:SUBJ 7:TEXT"


def traffic_label(state):
    return "TEST" if is_exercise(state) else "LIVE"


def traffic_ack(traffic, traffic_id, state, reply_found=None):
    """System receipt. Confirms logging only, never delivery to the addressee."""
    label = "TEST ACK" if is_exercise(state) else "LIVE ACK"
    ref = f" RE:{traffic.reply_to}" if traffic.reply_to else ""
    to = traffic.fields.get("2", "")
    prec = precedence_display(traffic.precedence, traffic.test_traffic)
    text = f"{label} {traffic_id}{ref} TO {to} LOGGED. PREC {prec}."
    if traffic.reply_to and reply_found is False:
        text += " REF NOT IN LOG."
    if traffic.legacy_precedence == "IMMEDIATE":
        text += " LEGACY IMMEDIATE LOGGED AS P."
    elif traffic.syntax == "legacy":
        text += " LEGACY FORMAT."
    return text + " NOT A DELIVERY CONFIRMATION."


def accept_traffic(traffic, from_node, state, raw_input, parts=1):
    """Validate, assign an internal traffic ID, log, and return the ACK text."""
    errors = validate_formal(traffic, is_exercise(state))
    if errors:
        return f"{traffic_label(state)} TRAFFIC REJECTED: {'; '.join(errors)}. {traffic_usage(state)}"
    reply_found = None
    if traffic.reply_to:
        reply_found = find_traffic(traffic.reply_to) is not None
    state["traffic_count"] += 1
    state["events"] += 1
    traffic_id = f"EX-{state['traffic_count']:03d}" if is_exercise(state) else f"EC-{state['traffic_count']:03d}"
    save_state(state)
    record = traffic_record(traffic, traffic_id, state["mode"], from_node, raw_input, parts, reply_found)
    log_event("traffic", from_node, raw_input, record)
    return traffic_ack(traffic, traffic_id, state, reply_found)


def handle_traffic_part(part_token, args, from_node, state, raw_input):
    """Buffer multipart formal traffic ('TRAFFIC 1/2 P 2:..', 'TRAFFIC 2/2 7:..') per sender."""
    m = PART_RE.match(part_token)
    k, n = int(m.group(1)), int(m.group(2))
    label = traffic_label(state)
    if k > n:
        return f"{label} TRAFFIC REJECTED: BAD PART {k}/{n}."
    pending = state.setdefault("pending_traffic", {})
    key = str(from_node)
    now = datetime.now(LOCAL_TZ)
    entry = pending.get(key)
    if entry:
        try:
            age = (now - datetime.fromisoformat(entry["started"])).total_seconds()
        except Exception:
            age = PART_TIMEOUT_SECONDS + 1
        if age > PART_TIMEOUT_SECONDS:
            entry = None
    if k == 1:
        try:
            parse_traffic_header(args.split())
        except TrafficError as exc:
            pending.pop(key, None)
            save_state(state)
            return f"{label} TRAFFIC REJECTED: {exc}. {traffic_usage(state)}"
        entry = {"total": n, "parts": {}, "started": now.isoformat(timespec="seconds"), "raw": []}
    elif not entry or entry.get("total") != n:
        pending.pop(key, None)
        save_state(state)
        return f"{label} PART {k}/{n} WITHOUT PART 1/{n}. RESEND FROM 1/{n}."
    entry["parts"][str(k)] = args
    entry["raw"].append(raw_input)
    pending[key] = entry
    if len(entry["parts"]) < n:
        save_state(state)
        waiting = ",".join(str(i) for i in range(1, n + 1) if str(i) not in entry["parts"])
        return f"{label} PART {k}/{n} RECEIVED. AWAITING {waiting}/{n}. NOT LOGGED YET."
    pending.pop(key, None)
    save_state(state)
    try:
        precedence, test, rest = parse_traffic_header(entry["parts"]["1"].split())
        segment_lists = [parse_field_segments(" ".join(rest))]
        for i in range(2, n + 1):
            segment_lists.append(parse_field_segments(entry["parts"][str(i)]))
        traffic = build_formal(precedence, test, merge_segments(segment_lists))
    except TrafficError as exc:
        return f"{label} TRAFFIC REJECTED: {exc}. {traffic_usage(state)}"
    return accept_traffic(traffic, from_node, state, " || ".join(entry["raw"]), parts=n)


def handle_traffic(body, from_node, state):
    m = re.match(r"^TRAFFIC(?:\s+(.+))?$", body, re.I)
    args = normalize(m.group(1) if m else "")
    if not args:
        return f"{traffic_label(state)} TRAFFIC FORMAT: {traffic_usage(state)[5:]}"
    raw_input = f"TRAFFIC {args}"
    tokens = args.split()
    if PART_RE.match(tokens[0]):
        return handle_traffic_part(tokens[0], " ".join(tokens[1:]), from_node, state, raw_input)
    try:
        traffic = parse_structured(args) if is_structured_traffic(args) else parse_legacy(args)
    except TrafficError as exc:
        return f"{traffic_label(state)} TRAFFIC REJECTED: {exc}. {traffic_usage(state)}"
    return accept_traffic(traffic, from_node, state, raw_input)


def handle_relay(body, from_node, state):
    """Log a relay of existing formal traffic. Original fields are never rewritten."""
    m = re.match(r"^RELAY\s+(\S+)(?:\s+VIA\s+(.+))?$", body, re.I)
    label = traffic_label(state)
    if not m:
        return f"{label} RELAY FORMAT: EMCOMM RELAY <TRAFFIC-ID> [VIA <ROUTE>]"
    traffic_id = m.group(1).upper()
    original = find_traffic(traffic_id)
    if not original:
        return f"{label} RELAY: {traffic_id} NOT IN LOG."
    relay_count = 1 + sum(
        1 for r in read_log_records()
        if r.get("kind") == "relay" and r.get("traffic_id") == traffic_id
        and r.get("time", "") >= original.get("time", "")
    )
    state["relays"] = int(state.get("relays", 0)) + 1
    state["events"] += 1
    save_state(state)
    log_event("relay", from_node, body, {
        "traffic_id": traffic_id,
        "relayed_by": str(from_node),
        "relay_time": now_iso(),
        "relay_count": relay_count,
        "relay_route": normalize(m.group(2) or ""),
    })
    try:
        text = serialize_traffic(traffic_from_record(original), traffic_id)
    except TrafficError:
        text = []
    return [f"{label} RELAY {traffic_id} #{relay_count} LOGGED. FIELDS UNCHANGED. NOT A DELIVERY CONFIRMATION."] + text


def handle_checkout(body, from_node, state):
    m = re.match(r"^CHECKOUT\s+(\S+)$", body, re.I)
    if not m:
        return f"{response_prefix(state)} format: EMCOMM CHECKOUT <CALLSIGN>."
    callsign = m.group(1).upper()
    if callsign not in state["participants"]:
        return f"{response_prefix(state)} CHECKOUT: {callsign} not on roster."
    del state["participants"][callsign]
    state["events"] += 1
    save_state(state)
    log_event("checkout", from_node, body, {"callsign": callsign})
    suffix = " SIMULATED." if is_exercise(state) else ""
    return f"{response_prefix(state)} CHECKOUT {callsign} removed from roster.{suffix}"


def handle_status(state):
    if is_exercise(state):
        return (
            f"EXERCISE STATUS - participants {len(state['participants'])}; "
            f"SITREPs {state['sitreps']}; traffic {state['traffic_count']}; "
            f"last inject {state['last_inject']}. SIMULATED."
        )
    return (
        f"LIVE STATUS - stations {len(state['participants'])}; "
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
    elif re.match(r"^CHECKOUT\b", body, re.I):
        response = handle_checkout(body, from_node, state)
    elif re.match(r"^SITREP\b", body, re.I):
        response = handle_sitrep(body, from_node, state)
    elif re.match(r"^TRAFFIC\b", body, re.I):
        response = handle_traffic(body, from_node, state)
    elif re.match(r"^RELAY\b", body, re.I):
        response = handle_relay(body, from_node, state)
    elif re.match(r"^STATUS\b", body, re.I):
        response = handle_status(state)
    else:
        response = help_text(state)
    emit(response)


# ---------------------------------------------------------------------------
# Local administration
# ---------------------------------------------------------------------------

def set_mode(mode, confirm_live=False):
    state = load_state()
    if mode == "status":
        emit(f"EmComm Control mode: {mode_label(state['mode'])}.")
        return
    if mode == "live" and not confirm_live:
        emit(
            "LIVE mode not enabled. Re-run locally with --mode live --confirm-live "
            "to confirm real traffic may be logged/sent."
        )
        return
    previous = state["mode"]
    state["mode"] = mode
    state["last_inject"] = 0
    state["pending_traffic"] = {}
    if mode == "exercise":
        state["exercise"] = EXERCISE_NAME
    save_state(state)
    log_event("mode_change", "", f"{previous} -> {mode}")
    emit(f"EmComm Control mode changed to {mode_label(mode)}.")


def handle_inject(number):
    state = load_state()
    if not is_exercise(state):
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
    messages = EXERCISE_INJECTS[number]
    log_event("inject", "", " ".join(messages), {"inject": number})
    emit(messages)


def handle_announce(text):
    state = load_state()
    text = normalize(text)
    if not text:
        emit("Announcement text is empty.")
        return
    label = mode_label(state["mode"])
    suffix = " SIMULATED." if is_exercise(state) else ""
    message = f"{label} ANNOUNCEMENT - {text}{suffix}"
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


def checkout_participant(callsign):
    state = load_state()
    callsign = normalize(callsign).upper()
    if callsign not in state["participants"]:
        emit(f"CHECKOUT: {callsign} not on roster.")
        return
    del state["participants"][callsign]
    state["events"] += 1
    save_state(state)
    log_event("checkout", "", f"Local checkout: {callsign}", {"callsign": callsign, "source": "cli"})
    emit(f"{mode_label(state['mode'])} CHECKOUT {callsign} removed from roster.")


FORMAL_TRAFFIC_FIELDS = [
    "traffic_id", "mode", "precedence", "test_traffic",
    "field_1_incident", "field_2_to", "field_3_from", "field_4_subject",
    "field_5_date", "field_6_time", "field_7_message", "field_8_approved_by",
    "reply_to", "from_node", "received_time", "raw_input",
    "syntax", "legacy_precedence", "parts", "relay_count",
]

TRAFFIC_LOG_FIELDS = [
    "time", "mode", "kind", "from_node", "callsign", "location", "power", "role",
    "status", "sitrep_number", "to", "precedence", "traffic_id", "body", "inject", "message",
    "syntax", "legacy_precedence", "test_traffic", "reply_to",
    "field_1_incident", "field_2_to", "field_3_from", "field_4_subject",
    "field_5_date", "field_6_time", "field_7_message", "field_8_approved_by",
    "received_time", "raw_input", "parts",
    "relayed_by", "relay_time", "relay_count", "relay_route",
]


def formal_traffic_rows(records=None):
    """Formal traffic records (legacy upgraded) with relay counts, for CSV export."""
    records = read_log_records() if records is None else records
    rows = []
    for record in records:
        if record.get("kind") == "traffic":
            rows.append(dict(record, relay_count=0))
        elif record.get("kind") == "relay":
            for row in reversed(rows):
                if row.get("traffic_id") == record.get("traffic_id"):
                    row["relay_count"] += 1
                    break
    return rows


def export_bundle(out_dir=None):
    """Write roster.csv, traffic_log.csv, formal_traffic.csv, and summary.txt for after-action review."""
    state = load_state()
    out = Path(out_dir) if out_dir else DATA_DIR / f"export_{datetime.now(LOCAL_TZ).strftime('%Y%m%dT%H%M%S')}"
    out.mkdir(parents=True, exist_ok=True)
    records = read_log_records()
    formal = formal_traffic_rows(records)

    with (out / "roster.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["callsign", "location", "power", "role", "node", "time"])
        for callsign, info in sorted(state.get("participants", {}).items()):
            writer.writerow([
                callsign, info.get("location", ""), info.get("power", ""),
                info.get("role", ""), info.get("node", ""), info.get("time", ""),
            ])

    with (out / "traffic_log.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRAFFIC_LOG_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record)

    with (out / "formal_traffic.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FORMAL_TRAFFIC_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in formal:
            writer.writerow(row)

    by_prec = {}
    for row in formal:
        by_prec[row.get("precedence", "")] = by_prec.get(row.get("precedence", ""), 0) + 1

    with (out / "summary.txt").open("w", encoding="utf-8") as f:
        f.write("EmComm Control after-action export\n")
        f.write(f"Generated: {now_iso()}\n")
        f.write(f"Mode: {mode_label(state.get('mode'))}\n")
        f.write(f"Exercise/operation name: {state.get('exercise', '')}\n")
        for label, key in (
            ("Exercise ID", "exercise_id"), ("Exercise type", "exercise_type"),
            ("Organization", "organization"), ("Incident name", "incident_name"),
            ("Planned start", "start"), ("Planned end", "end"),
        ):
            if CONFIG.get(key):
                f.write(f"{label}: {CONFIG[key]}\n")
        f.write(f"Started: {state.get('started') or 'n/a'}\n")
        f.write(f"Ended: {state.get('ended') or 'n/a'}\n")
        f.write(f"Stations checked in: {len(state.get('participants', {}))}\n")
        f.write(f"SITREPs: {state.get('sitreps', 0)}\n")
        f.write(f"Traffic records: {state.get('traffic_count', 0)}\n")
        f.write(f"Relays logged: {state.get('relays', 0)}\n")
        f.write(f"Total logged events: {state.get('events', 0)}\n")
        if by_prec:
            f.write("Formal traffic by precedence (all logged): "
                    + ", ".join(f"{k or '?'}={v}" for k, v in sorted(by_prec.items())) + "\n")
        f.write(
            "Note: traffic IDs (EX-/EC-) are internal EmComm Control identifiers, not NTS message numbers. "
            "ACKs confirm logging by EmComm Control, not delivery to the addressee.\n"
        )

    return out


def main():
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--mode", choices=["exercise", "live", "status"])
    parser.add_argument("--confirm-live", action="store_true", help="Required local confirmation when enabling LIVE mode.")
    parser.add_argument("--inject", type=int, help="Send a numbered exercise inject (EXERCISE mode only).")
    parser.add_argument("--announce", help="Send an operator-supplied announcement in the current mode.")
    parser.add_argument("--reset", action="store_true", help="Reset counters/state while preserving current mode.")
    parser.add_argument("--checkout", help="Remove a callsign from the roster (local correction).")
    parser.add_argument(
        "--export", nargs="?", const="", metavar="DIR",
        help="Export roster/traffic CSV + summary for after-action review. Optional output directory.",
    )
    args = parser.parse_args()
    selected = sum([
        args.mode is not None, args.inject is not None, args.announce is not None,
        args.reset, args.checkout is not None, args.export is not None,
    ])
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
    elif args.checkout is not None:
        checkout_participant(args.checkout)
    elif args.export is not None:
        out = export_bundle(args.export or None)
        log_event("export", "", f"After-action export written to {out}")
        emit(f"After-action export written to {out}")
    else:
        handle_message()


if __name__ == "__main__":
    main()
