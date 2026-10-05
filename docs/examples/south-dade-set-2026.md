# Example Exercise Scenario: South Dade GMRS — Simulated Emergency Test (SET), October 3, 2026

> **This is an example deployment of EmComm Control.** Other clubs and organizations should substitute their own exercise plan, radio settings, incident name, schedule, and participants.
>
> Nothing on this page is built into EmComm Control. The software is organization-neutral, and its defaults stay generic ("Emergency Communications Exercise"). The radio settings below are **local exercise settings for this example only**, not recommended defaults.

---

## Example SET Configuration

| Item | Example value |
|---|---|
| Exercise | Simulated Emergency Test (SET) |
| Date | Saturday, October 3, 2026 |
| Operating period | 9:00 AM–12:00 PM (local time) |
| Technologies | Meshtastic and MeshCore |
| Purpose | Off-grid communications, formal message handling, relay testing, coverage evaluation, message acknowledgment, interoperability testing |

### EmComm Control configuration (no code changes)

Copy [`south-dade-set-2026.config.json`](south-dade-set-2026.config.json) to the MeshMonitor scripts directory as `/data/scripts/mm_emcomm_config.json`, or point to it with `MM_EMCOMM_CONFIG`:

```json
{
  "exercise_name": "Simulated Emergency Test (SET)",
  "exercise_id": "SET-2026",
  "exercise_type": "Simulated Emergency Test",
  "organization": "South Dade GMRS Club",
  "incident_name": "SET",
  "start": "2026-10-03T09:00",
  "end": "2026-10-03T12:00",
  "local_instructions": "NCS ON MESH. CHECK IN FIRST. FORMAL TRAFFIC AFTER INJECT 6.",
  "exercise_style": "set-safe",
  "net_control": {
    "enabled": true,
    "name": "NET CONTROL",
    "operator_name": "",
    "callsign": "KI4SDC",
    "location": {
      "mode": "auto",
      "override": "DORAL, FLORIDA"
    },
    "auto_checkin_ack": true,
    "checkin_ack_window": "exercise",
    "announcements": {
      "enabled": true,
      "before_start": [
        {
          "minutes_before": 60,
          "message": "WARNING: SET EXERCISE BEGINS IN 1 HOUR. MESHTASTIC + MESHCORE USERS WELCOME."
        },
        {
          "minutes_before": 15,
          "message": "WARNING: SET EXERCISE BEGINS IN 15 MINUTES. PREPARE FOR EXERCISE TRAFFIC."
        }
      ],
      "at_start": {
        "message": "WARNING: SET EXERCISE IS NOW IN PROGRESS. SIMULATED TRAFFIC ONLY."
      },
      "during": {
        "interval_minutes": 60,
        "message": "WARNING: SET EXERCISE IN PROGRESS UNTIL 12PM. SIMULATED TRAFFIC ONLY."
      },
      "before_end": [
        {
          "minutes_before": 15,
          "message": "SET EXERCISE ENDS IN 15 MINUTES. FINAL TRAFFIC AND CHECKOUTS MAY BE SENT."
        }
      ],
      "at_end": {
        "message": "SET EXERCISE COMPLETE. THANK YOU FOR PARTICIPATING."
      }
    }
  }
}
```

This example uses the **SET-safe** exercise style. Bots on the shared local mesh auto-reply to the word `TEST` and cannot be changed for this exercise, so formal traffic is marked `SET R` / `SET P` and Field 7 begins `EXERCISE`. Clubs without that problem can leave `exercise_style` at `standard`.

This example also enables **Net Control automation** (see [docs/net-control.md](../net-control.md)):

- **Identity:** Net Control replies as `NET CONTROL KI4SDC`. Add an `operator_name` (for example `ERIC`) to reply as `ERIC KI4SDC`.
- **Location:** replies say `RECEIVED HERE IN DORAL, FLORIDA`. Doral is this exercise's override, not an application default.
- **Check-in ACKs** run only from 09:00 until before 12:00, and only in EXERCISE mode.

Environment variables override the file, for example `MM_EMCOMM_EXERCISE_NAME` or `MM_EMCOMM_ORGANIZATION`. If you run the operator panel, restart it after changing the config.

Before the exercise starts:

```bash
/data/scripts/mm_emcomm_control.py --mode exercise
/data/scripts/mm_emcomm_control.py --reset
```

---

## Example radio settings (local to this exercise)

### Meshtastic

| Setting | Example value |
|---|---|
| Region | US |
| Modem preset | MediumFast |
| Frequency slot | 45 |
| Primary channel name | *(blank)* |
| Key | `AQ==` |
| Uplink | ON |
| Downlink | ON |
| Position sharing | Optional |

### MeshCore

| Setting | Example value |
|---|---|
| Region | Canada, USA |
| Frequency | 910.525 MHz |
| Bandwidth | 62.5 kHz |
| Spreading factor | SF7 |
| Coding rate | CR8 |
| Channel | Public Channel |
| Path hash | 2-byte |
| Fixed location | Optional |

These are **example/local exercise settings**. Use the settings your own exercise plan and local mesh community specify, and follow the radio-service rules that apply to you.

---

## Net Control automation: example schedule

Automation is limited to the SET channels `meshtastic:0` (primary channel) and `meshcore:0` (Public). Set up one MeshMonitor **Timed Event** per network, running every minute (`* * * * *`) on that channel:

- **Meshtastic:** arguments `--schedule-check --channel 0`. Meshtastic Timed Events don't pass the channel.
- **MeshCore:** arguments `--schedule-check`.

The config above then sends:

| Time | Announcement |
|---|---|
| 08:00 | WARNING: SET EXERCISE BEGINS IN 1 HOUR. MESHTASTIC + MESHCORE USERS WELCOME. |
| 08:45 | WARNING: SET EXERCISE BEGINS IN 15 MINUTES. PREPARE FOR EXERCISE TRAFFIC. |
| 09:00 | SET START \| NET OPEN \| ALL STATIONS PLEASE USE THE SET MESSAGE TEMPLATE \| NET CONTROL ACTIVE |
| 09:00 | WARNING: SET EXERCISE IS NOW IN PROGRESS. SIMULATED TRAFFIC ONLY. |
| 10:00 | WARNING: SET EXERCISE IN PROGRESS UNTIL 12PM. SIMULATED TRAFFIC ONLY. |
| 11:00 | WARNING: SET EXERCISE IN PROGRESS UNTIL 12PM. SIMULATED TRAFFIC ONLY. |
| 11:45 | SET EXERCISE ENDS IN 15 MINUTES. FINAL TRAFFIC AND CHECKOUTS MAY BE SENT. |
| 12:00 | SET EXERCISE COMPLETE. THANK YOU FOR PARTICIPATING. |
| 12:00 | SET COMPLETE \| NET CLOSED \| THANK YOU TO ALL STATIONS FOR PARTICIPATING \| RETURNING CHANNEL TO NORMAL TRAFFIC |

- **No 12:00 periodic warning:** the hourly warning stops before the end.
- **After 12:00:** no announcements are sent, the panel's Upcoming list is empty, and status is **COMPLETED**.
- **If you switch to LIVE,** exercise announcements stop immediately.

### Automatic check-ins (09:00–12:00)

The existing `^SET\b` Auto Responder rule delivers these to EmComm Control; replies go back on the same network and channel.

```text
SET R | NET CONTROL | WRWJ781 | CHECKIN | FROM CORAL SPRINGS, FLORIDA
→ SET R | WRWJ781 | NET CONTROL KI4SDC | CHECKIN ACK | RECEIVED HERE IN DORAL, FLORIDA

SET R | NET CONTROL | ERIC WRZU598 | CHECKIN | FROM CORAL SPRINGS, FLORIDA
→ SET R | ERIC WRZU598 | NET CONTROL KI4SDC | CHECKIN ACK | RECEIVED HERE IN DORAL, FLORIDA
```

- The ACK confirms reception by the Net Control automation only, not delivery or handling of any formal traffic.
- Duplicates and Net Control's own replies are never acknowledged.
- Check-ins before 09:00 or from 12:00 on are logged but not answered.
- `--export` includes everything in `automation_log.csv`.

## Example timeline

Timed Events in MeshMonitor run `mm_emcomm_control.py --inject N`:

| Time | Inject | Phase |
|---|---|---|
| 09:00 | 1 | Exercise begins; check-ins (`EMCOMM CHECKIN`) |
| 09:15 | 2 | Simulated commercial power failure; SITREPs |
| 09:30 | 3 | Simulated cell/Internet degradation; relay capability |
| 10:00 | 4 | Simulated served-agency request for comms status |
| 10:30 | 5 | Tactical traffic phase (SITREPs) |
| 11:00 | 6 | **Formal traffic phase**: ICS-213 / NTS-style TEST messages |
| 11:30 | 7 | Simulated partial restoration |
| 12:00 | 8 | End of exercise; final SITREPs; after-action export |

---

## Example South Dade SET workflow

Inject 6 begins the formal-message phase:

```text
EXERCISE INJECT 6 - FORMAL TRAFFIC PHASE. ORIGINATE AN ICS-213 / NTS-STYLE EXERCISE MESSAGE USING FIELDS 2, 3, 4 AND 7.
FIELD 7 MUST BEGIN EXERCISE. EX: EMCOMM TRAFFIC R 2:EOC 3:FIELD1 4:STATUS 7:EXERCISE COMMS OPERATIONAL
```

A field station sends a request, with the incident name in Field 1:

```text
EMCOMM TRAFFIC P 1:SET 2:NCS 3:SHELTER1 4:WATER 6:1105 7:EXERCISE REQUEST 20 CASES WATER
→ EXERCISE ACK EX-007 TO NCS LOGGED. PREC SET P. NOT A DELIVERY CONFIRMATION.
```

A station passes the message toward Net Control; the original fields are unchanged:

```text
EMCOMM RELAY EX-007 VIA MESHCORE-REPEATER
→ EXERCISE RELAY EX-007 #1 LOGGED. FIELDS UNCHANGED. NOT A DELIVERY CONFIRMATION.
→ SET P | EX-007 | 1:SET | 2:NCS | 3:SHELTER1 | 4:WATER | 6:1105 | 7:EXERCISE REQUEST 20 CASES WATER
```

Net Control replies with a new message that references the original:

```text
EMCOMM TRAFFIC R RE:EX-007 1:SET 2:SHELTER1 3:NCS 4:WATER 7:EXERCISE REQUEST APPROVED 8:NCS1
→ EXERCISE ACK EX-008 RE:EX-007 TO SHELTER1 LOGGED. PREC SET R. NOT A DELIVERY CONFIRMATION.
```

Once the request reaches Net Control, the NCS station confirms delivery:

```text
EMCOMM RCVD EX-007
→ EXERCISE RCVD EX-007 DELIVERY CONFIRMED BY NCS1 AT 11:10. LOGGED.
```

Any station can check status:

```text
EMCOMM TRACK EX-007
→ EXERCISE TRACK EX-007 PREC SET P TO NCS: LOGGED 11:05 | RELAYED 1X (LAST 11:07) | DELIVERED 11:10 BY NCS1 (5.0 MIN)
```

The system ACK confirms **logging only**. A receipt (`RCVD`) is operator-reported delivery.

### Optional: capture all exercise-channel traffic

To include ordinary chat in the after-action review, add the silent capture rule from [docs/tracking.md](../tracking.md):

- trigger `.*`, script `mm_emcomm_control.py`, arguments `--capture`
- scoped to the exercise channel
- on Meshtastic, ordered after the `EMCOMM` / `SET` rules

After the exercise:

```bash
/data/scripts/mm_emcomm_control.py --export
```

This writes `roster.csv`, `traffic_log.csv`, `formal_traffic.csv` (with delivery status), `stations.csv` (per-station activity and SNR/hop coverage), `captured_messages.csv`, and `summary.txt` for the after-action review.

If real emergency traffic occurs during the SET, stop treating it as exercise traffic and handle it as real-world traffic under your local operating procedure. See [Real-world traffic during an exercise](../formal-traffic.md#real-world-traffic-during-an-exercise).
