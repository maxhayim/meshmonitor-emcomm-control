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
  "local_instructions": "NCS ON MESH. CHECK IN FIRST. FORMAL TRAFFIC AFTER INJECT 6."
}
```

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
TEST EXERCISE INJECT 6 - FORMAL TRAFFIC PHASE. ORIGINATE AN ICS-213 / NTS-STYLE TEST MESSAGE USING FIELDS 2, 3, 4 AND 7.
FIELD 7 MUST BEGIN TEST MESSAGE. EX: EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL
```

A field station sends a request, with the incident name in Field 1:

```text
EMCOMM TRAFFIC P 1:SET 2:NCS 3:SHELTER1 4:WATER 6:1105 7:TEST MESSAGE REQUEST 20 CASES WATER
→ TEST ACK EX-007 TO NCS LOGGED. PREC TEST P. NOT A DELIVERY CONFIRMATION.
```

A station passes the message toward Net Control; the original fields are unchanged:

```text
EMCOMM RELAY EX-007 VIA MESHCORE-REPEATER
→ TEST RELAY EX-007 #1 LOGGED. FIELDS UNCHANGED. NOT A DELIVERY CONFIRMATION.
→ TEST P | EX-007 | 1:SET | 2:NCS | 3:SHELTER1 | 4:WATER | 6:1105 | 7:TEST MESSAGE REQUEST 20 CASES WATER
```

Net Control replies with a new message that references the original:

```text
EMCOMM TRAFFIC R RE:EX-007 1:SET 2:SHELTER1 3:NCS 4:WATER 7:TEST MESSAGE REQUEST APPROVED 8:NCS1
→ TEST ACK EX-008 RE:EX-007 TO SHELTER1 LOGGED. PREC TEST R. NOT A DELIVERY CONFIRMATION.
```

Remember that the system ACK confirms **logging only**. Confirm delivery to the addressee under your own net procedure.

After the exercise:

```bash
/data/scripts/mm_emcomm_control.py --export
```

This writes `roster.csv`, `traffic_log.csv`, `formal_traffic.csv`, and `summary.txt` for the after-action review.

If real emergency traffic occurs during the SET, stop treating it as exercise traffic and handle it as real-world traffic under your local operating procedure. See [Real-world traffic during an exercise](../formal-traffic.md#real-world-traffic-during-an-exercise).
