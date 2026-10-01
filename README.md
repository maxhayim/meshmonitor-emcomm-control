<p align="center">
  <img src="docs/assets/logo.png" alt="EmComm Control Logo" width="200"/>
</p>
<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.9%2B-blue" alt="Python Version">
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
  </a>
</p>

# 🚨 EmComm Control

Emergency communications control script for [**MeshMonitor**](https://github.com/Yeraze/MeshMonitor), supporting both **real-world operations** and **simulated exercises** over [**Meshtastic**](https://meshtastic.org/), [**MeshCore**](https://meshcore.co.uk/), or any other mesh network MeshMonitor supports. EmComm Control can support emergency operations center (EOC) workflows for cities and municipalities, counties and regions, and state-level operations.

The project provides one runtime with two deliberately separated operating modes:

- **LIVE** — operator-entered real-world check-ins, SITREPs, traffic logging, status, and announcements
- **EXERCISE** — drills and simulated incidents, including ARRL® Simulated Emergency Test (SET) use and timed exercise injects

Traffic is split into two classes:

- **Tactical** — lightweight `CHECKIN`, `CHECKOUT`, `SITREP`, `STATUS`, `HELP`
- **Formal** — `TRAFFIC`, using a **compressed ICS-213-compatible field structure with NTS-style traffic handling** (precedence, TEST marking, references/replies, accurate relay, structured logging). See [docs/formal-traffic.md](docs/formal-traffic.md).

> This software provides an ICS-213 / NTS-style workflow for training and communications support. It is not an official FEMA ICS-213, ARRL NTS, Winlink, ARES, RACES, or government message-management system, and it does not replace the official ICS-213 form, Winlink forms, NTS radiogram software, or agency message-management systems.

This repository contains:
- **mm_emcomm_control.py** — the actual MeshMonitor Auto Responder / Timed Event script (runtime)
- **mm_emcomm_panel.py** — optional browser-based operator control panel for LIVE / EXERCISE mode and status
- **docs/** — GitHub Pages documentation (display only)

---

## What this does

EmComm Control allows operators to:

- Check in with callsign, location, power source, and role
- Submit and log SITREPs
- Originate formal ICS-213 / NTS-style traffic (Fields 1–8, R/P/W/EMERGENCY precedence, TEST marking in exercises)
- Log formal traffic structurally with internal traffic IDs, replies (`RE:`), relays, and multipart reassembly
- Track each formal message from logged → relayed → **delivered** (`EMCOMM RCVD`) and query status over the mesh (`EMCOMM TRACK`)
- Optionally capture ordinary mesh traffic silently, with SNR, hops, and channel, for after-action review
- Summarize activity per station: check-ins, SITREPs, traffic, relays, receipts, captured messages, and signal/hop coverage
- Request current operational statistics
- Send operator-supplied announcements
- Run timed **simulated** exercise injects while in EXERCISE mode
- Retain JSON / JSONL state and traffic logs for operational review or after-action review
- Operate over Meshtastic, MeshCore, or other networks supported by MeshMonitor
- Support EOC workflows at city/municipal, county/regional, and state levels
- Provide optional one-click browser controls so EOC operators do not need terminal access to switch modes

Design goals:
- One tool for drills and real activations
- Explicit separation between LIVE and EXERCISE traffic
- No simulated incident generation while LIVE
- Local-only activation of LIVE mode
- No external Python dependencies
- Backwards compatibility with the original `SET` exercise command prefix

---

## Emergency Operations Center (EOC) use

EmComm Control can be deployed as a MeshMonitor communications-control layer in an **Emergency Operations Center (EOC)** or supporting communications room. It is suitable for:

- **City / municipal EOCs** — local incident coordination, field-team check-ins, SITREPs, and message logging
- **County / regional EOCs** — coordination across municipalities, shelters, facilities, field teams, and regional communications resources
- **State EOCs** — statewide communications coordination, regional status collection, and operator-entered message tracking

The same installation can remain in **EXERCISE** mode for drills and SET activities, then be deliberately switched locally to **LIVE** mode for a real activation. EmComm Control is a communications-support and logging tool; it does not replace an agency's incident-management system, dispatch system, records policy, or approved emergency communications plan.

---

## Operator Control Panel

Starting with **v2.1.0**, EmComm Control includes an optional local web panel so operators do not need to run command-line flags to change modes.

The panel provides:

### Operator view at a glance

**🟡 EXERCISE**

`[ 🟢 ACTIVATE LIVE ]` `[ 🟡 EXERCISE MODE ]` `[ 🔵 STATUS ]`

The mode indicator makes it immediately clear whether the system is in **EXERCISE** or **LIVE** operation, while the three primary controls give operators one-click access to mode switching and current status.

- **Activate LIVE** button with a second confirmation screen
- **Switch to EXERCISE** button
- **Refresh Status**
- **Reset Operation** with confirmation
- Current station/check-in, SITREP, traffic, delivery, captured-message, and event counts
- **Formal traffic log** with logged / relayed / delivered status, **Station activity** summary, and **Captured mesh messages** table
- Clear **EXERCISE / TEST** or **LIVE** banner
- **Formal traffic composer** with structured ICS-213 fields (Incident Name, Precedence, To, From, Subject, Date, Time, Message, Approved By, Reply To) that generates the compact `EMCOMM TRAFFIC` command — multipart when needed — with a live `current / maximum` character counter and a soft warning above 120 characters. The panel only generates commands; send them from your Meshtastic or MeshCore client.
- Formal traffic log table and `formal_traffic.csv` download
- Checked-in station table
- Recent operational-log view

The panel modifies the same state used by `mm_emcomm_control.py`; there is no separate mode database.

### Local computer

Place `mm_emcomm_panel.py` next to `mm_emcomm_control.py` in `/data/scripts/`, then run:

```bash
python3 /data/scripts/mm_emcomm_panel.py --open
```

The default address is:

```text
http://127.0.0.1:8787
```

By default the server listens only on localhost.

### EOC / LAN access

To make the panel reachable from authorized workstations on an EOC management LAN, **an access token is required**:

```bash
MM_EMCOMM_PANEL_TOKEN='use-a-long-random-token' \
python3 /data/scripts/mm_emcomm_panel.py --host 0.0.0.0 --port 8787
```

The panel intentionally refuses a non-loopback bind if no token is configured. For production EOC use, keep it on a trusted management network and preferably place it behind an authenticated TLS reverse proxy.

### Docker sidecar example

If MeshMonitor uses the standard `meshmonitor-data` Docker volume, the panel can run as a small sidecar sharing the same `/data` volume:

```bash
docker run -d --name emcomm-panel --restart unless-stopped \
  -p 8787:8787 \
  -v meshmonitor-data:/data \
  -e MM_EMCOMM_PANEL_TOKEN='use-a-long-random-token' \
  python:3.12-alpine \
  python3 /data/scripts/mm_emcomm_panel.py --host 0.0.0.0 --port 8787
```

If your MeshMonitor installation uses a different named volume or a bind mount, use that same `/data` source instead.

> The web panel is an operator convenience interface. LIVE mode still requires deliberate confirmation, and EXERCISE injects remain blocked while LIVE.

See [`docs/NATIVE_SCRIPT_ACTIONS_PROPOSAL.md`](docs/NATIVE_SCRIPT_ACTIONS_PROPOSAL.md) for the proposed future `mm_meta` native-button design.

---

## Operating modes

### EXERCISE mode

EXERCISE is the default mode.

All exercise responses are explicitly labeled **TEST**, **EXERCISE**, and/or **SIMULATED**. Formal traffic is rendered with TEST before the precedence (`TEST R`, `TEST P`, …), and Field 7 must begin `TEST MESSAGE`. Timed simulated injects are available only in this mode.

Use EXERCISE mode for:
- ARRL® Simulated Emergency Test (SET)
- ARES / club exercises
- Served-agency drills
- Mesh communications testing
- Training and after-action evaluation

### LIVE mode

LIVE mode is intended for actual emergency-communications operations.

LIVE mode:
- Accepts only the `EMCOMM` command prefix
- Logs only information supplied by operators
- Blocks simulated exercise injects
- Does not invent or infer incident conditions
- Never automatically adds `TEST` or `TEST MESSAGE`
- Cannot be enabled by an inbound mesh message

> If actual emergency traffic occurs during an exercise, operators must stop treating that message as exercise traffic and clearly identify it as real-world traffic according to their local operating procedure.

Enable LIVE mode **locally on the MeshMonitor host**:

```bash
/data/scripts/mm_emcomm_control.py --mode live --confirm-live
```

Return to EXERCISE mode:

```bash
/data/scripts/mm_emcomm_control.py --mode exercise
```

Check the current mode:

```bash
/data/scripts/mm_emcomm_control.py --mode status
```

> Real-world radio traffic may be visible to other network participants. Follow applicable laws, regulations, local plans, served-agency procedures, and good information-security practices. Avoid transmitting sensitive information over open or untrusted RF networks.

---

## Repository layout
<pre>
├── mm_emcomm_control.py    # Runtime script used by MeshMonitor
├── mm_emcomm_panel.py      # Optional browser operator panel
├── docs/                   # Documentation (GitHub Pages + Markdown)
│   ├── index.html
│   ├── index.js
│   ├── formal-traffic.md   # ICS-213 / NTS-style formal traffic reference
│   ├── tracking.md         # Delivery receipts, TRACK, capture, station activity
│   └── examples/           # Example exercise configurations (not defaults)
├── tests/                  # pytest suite
├── ISSUE_TEMPLATE/
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── SECURITY.md
├── CHANGELOG.md
├── LICENSE
└── README.md
</pre>

---

## IMPORTANT: Which file do I use?

### Use this file in MeshMonitor

`mm_emcomm_control.py`

This is the **only file** MeshMonitor should execute.

### Do NOT run these files

`docs/index.html`  
`docs/index.js`

These files only display documentation on GitHub Pages.

---

## Installing mm_emcomm_control.py

Copy the runtime script into:

```text
/data/scripts/mm_emcomm_control.py
```

Make it executable:

```bash
chmod +x /data/scripts/mm_emcomm_control.py
```

---

## MeshMonitor Auto Responder configuration

Create two Auto Responder rules pointing to the same runtime script.

### Rule 1 — EmComm commands

Trigger regex:

```regex
^EMCOMM\b
```

Action: Script  
Script path:

```text
/data/scripts/mm_emcomm_control.py
```

### Rule 2 — Legacy SET exercise commands

Trigger regex:

```regex
^SET\b
```

Action: Script  
Script path:

```text
/data/scripts/mm_emcomm_control.py
```

The `SET` prefix is accepted only in EXERCISE mode. LIVE mode requires `EMCOMM`.

### Rule 3 (optional) — Silent capture of ordinary traffic

To also log ordinary channel messages during a SET or activation, add a catch-all rule. It **never transmits**.

Trigger regex:

```regex
.*
```

Action: Script
Script path: `/data/scripts/mm_emcomm_control.py`
Script arguments: `--capture`

On **Meshtastic**, place this rule **after** Rules 1 and 2, because only the first matching rule runs. On **MeshCore**, every matching rule runs; capture ignores `EMCOMM`/`SET` commands there, so nothing is logged twice. Captured messages include SNR, hops, and channel where MeshMonitor provides them. See [docs/tracking.md](docs/tracking.md) for limits and privacy notes.

---

## Mesh commands

### Tactical

```text
EMCOMM CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE>
EMCOMM CHECKOUT <CALLSIGN>
EMCOMM SITREP <LOCATION> <STATUS>
EMCOMM STATUS
EMCOMM HELP
```

### Formal (ICS-213 / NTS-style)

```text
EMCOMM TRAFFIC <PRECEDENCE> [RE:<ID>] 2:<TO> 3:<FROM> 4:<SUBJECT> 7:<MESSAGE>
EMCOMM RELAY <TRAFFIC-ID> [VIA <ROUTE>]
EMCOMM RCVD <TRAFFIC-ID>          # addressee confirms delivery (alias: DELIVERED)
EMCOMM TRACK <TRAFFIC-ID>         # logged / relayed / delivered status
```

- Required: Field 2 To, 3 From, 4 Subject, 7 Message. Optional: 1 Incident Name, 5 Date, 6 Time, 8 Approved By (last), `RE:<ID>`.
- Precedence: `R` Routine, `P` Priority, `W` Welfare, `EMERGENCY` (always spelled out).
- Field 7 runs to the end of the message (an optional trailing `8:` excepted).
- EXERCISE mode: Field 7 **must** begin `TEST MESSAGE`; the system renders precedence as `TEST P` etc.
- Long messages: send `EMCOMM TRAFFIC 1/2 …`, `EMCOMM TRAFFIC 2/2 …` (the panel generates these).

```text
EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL
→ TEST ACK EX-001 TO EOC LOGGED. PREC TEST P. NOT A DELIVERY CONFIRMATION.

EMCOMM TRAFFIC P 1:SET 2:EOC 3:SHELTER1 4:WATER 5:10/03/26 6:0930 7:TEST MESSAGE REQUEST 20 CASES WATER 8:OPERATOR1

EMCOMM TRAFFIC R RE:EX-001 2:FIELD1 3:EOC 4:STATUS 7:TEST MESSAGE RECEIVED THANKS
→ TEST ACK EX-002 RE:EX-001 TO FIELD1 LOGGED. PREC TEST R. NOT A DELIVERY CONFIRMATION.
```

**An ACK from EmComm Control confirms that the system received and logged the traffic. It does not confirm delivery to the intended recipient.** Delivery is recorded only when a station sends `EMCOMM RCVD <ID>`, and that receipt is operator-reported. Traffic IDs (`EX-###`, `EC-###`) are internal identifiers, not NTS message numbers.

```text
EMCOMM RCVD EX-001
→ TEST RCVD EX-001 DELIVERY CONFIRMED BY KN4EOC AT 11:10. LOGGED.

EMCOMM TRACK EX-001
→ TEST TRACK EX-001 PREC TEST P TO EOC: LOGGED 11:05 | RELAYED 1X (LAST 11:07) | DELIVERED 11:10 BY KN4EOC (5.0 MIN)
```

Full references: [docs/formal-traffic.md](docs/formal-traffic.md) and [docs/tracking.md](docs/tracking.md).

### Legacy syntax

Legacy traffic syntax remains supported for compatibility. Structured ICS-213 / NTS-style traffic is preferred.

```text
EMCOMM TRAFFIC <TO> [ROUTINE|PRIORITY|IMMEDIATE] <TEXT>
```

`ROUTINE` → `R`, `PRIORITY` → `P`. **`IMMEDIATE` is not an NTS precedence**; it is logged as `P` with `legacy_precedence = IMMEDIATE`, and the ACK says `LEGACY IMMEDIATE LOGGED AS P`.

While in EXERCISE mode, the original `SET` prefix remains valid:

```text
SET CHECKIN W4ABC MIAMI-EOC BATTERY NCS
SET SITREP SHELTER-1 RF-LINK-GOOD
SET TRAFFIC P 2:EOC 3:SHELTER-1 4:TEST 7:TEST MESSAGE RADIO CHECK
SET STATUS
```

---

## Message length

| Setting | Default | Override |
|---|---|---|
| Hard limit per emitted mesh message | **133 characters** | `MM_EMCOMM_MAXLEN` (minimum 60) |
| Recommended operating target | **120 ASCII characters** | `MM_EMCOMM_RECOMMENDED_LEN` |

133 is a conservative common default intended to work for Meshtastic and MeshCore. Actual limits vary by firmware, channel, and path overhead, so set your own value if your network differs. Longer responses are split automatically with `[1/2]`-style numbering. Formal traffic uses field-preserving multipart.

---

## Exercise configuration

Defaults are generic (`Emergency Communications Exercise`). To describe your own exercise **without modifying source code**, create `/data/scripts/mm_emcomm_config.json` (or point `MM_EMCOMM_CONFIG` at a file):

```json
{
  "exercise_name": "Emergency Communications Exercise",
  "exercise_id": "",
  "exercise_type": "",
  "organization": "",
  "incident_name": "",
  "start": "",
  "end": "",
  "local_instructions": ""
}
```

Environment variables override the file: `MM_EMCOMM_EXERCISE_NAME` (legacy `SET_NAME`), `MM_EMCOMM_EXERCISE_ID`, `MM_EMCOMM_EXERCISE_TYPE`, `MM_EMCOMM_ORGANIZATION`, `MM_EMCOMM_INCIDENT_NAME`, `MM_EMCOMM_EXERCISE_START`, `MM_EMCOMM_EXERCISE_END`, `MM_EMCOMM_LOCAL_INSTRUCTIONS`.

- The exercise name appears in injects 1 and 8.
- `local_instructions` is appended to HELP in EXERCISE mode.
- The incident name pre-fills Field 1 in the panel composer.
- All values appear in the after-action summary.

Other options:

- `MM_EMCOMM_TEST_PREFIX` — `validate` (default) or `auto`. Controls whether exercise traffic missing `TEST MESSAGE` is rejected or auto-prefixed.
- `MM_EMCOMM_PART_TIMEOUT` — seconds before incomplete multipart traffic expires (default 1800).

**Example exercise scenario:** [docs/examples/south-dade-set-2026.md](docs/examples/south-dade-set-2026.md) — an example SET configuration, not a default.

---

## Local administration

### Send an operator-supplied announcement

In either mode:

```bash
/data/scripts/mm_emcomm_control.py --announce "NCS requests all field stations check in"
```

The script labels the announcement according to the active mode. In EXERCISE mode it is also marked simulated.

### Reset counters and current operational state

```bash
/data/scripts/mm_emcomm_control.py --reset
```

### Correct the roster locally

```bash
/data/scripts/mm_emcomm_control.py --checkout W4ABC
```

### Export for after-action review

```bash
/data/scripts/mm_emcomm_control.py --export
/data/scripts/mm_emcomm_control.py --export /path/to/output-dir
```

Writes:

- `roster.csv`
- `traffic_log.csv`
- `formal_traffic.csv`: one row per formal message with ICS-213 fields and delivery status (logged / relayed / delivered, who confirmed, minutes to delivery)
- `stations.csv`: per-station activity and SNR/hop coverage
- `captured_messages.csv`
- `summary.txt`: delivery totals and the most active stations With no directory given, the export is written under the script's data directory, timestamped. The operator panel offers the same CSV files as one-click downloads.

Reset preserves the current LIVE / EXERCISE mode.

---

## EXERCISE mode timed events

Simulated injects are available only in EXERCISE mode:

```text
--inject 1
--inject 2
--inject 3
--inject 4
--inject 5
--inject 6
--inject 7
--inject 8
```

Example sequence:

```text
09:00  Inject 1 — exercise begins / check-ins
09:15  Inject 2 — simulated commercial power failure
09:30  Inject 3 — simulated cellular / Internet degradation
10:00  Inject 4 — simulated served-agency SITREP request
10:30  Inject 5 — simulated tactical traffic phase
11:00  Inject 6 — formal traffic phase (ICS-213 / NTS-style TEST messages)
11:30  Inject 7 — simulated partial restoration
12:00  Inject 8 — end of exercise
```

All injects begin `TEST EXERCISE INJECT N` and are kept within the configured message limit, using multiple messages where needed. If an inject is invoked while LIVE, the script refuses to transmit it.

---

## State and logs

EmComm Control stores runtime data under:

```text
/data/scripts/mm_emcomm_control_data/
```

Files:

```text
state.json
traffic.jsonl
```

The state file stores the current mode, participants/stations, counts, pending multipart traffic, and exercise state. The JSONL log records check-ins, SITREPs, structured formal traffic, relays, announcements, mode changes, and exercise injects.

Pre-2.3 traffic records are upgraded to the structured field model in memory when read or exported. The log file on disk is never rewritten.

### Migration from SET Exercise Control

If the previous `/data/scripts/mm_arrl_set_data/` directory exists and the new EmComm state does not yet exist, v2 performs a best-effort one-time migration of the previous state and traffic log.

The old runtime filename `mm_arrl_set.py` is replaced by `mm_emcomm_control.py`.

---

## Maintenance / Reinstall (Advanced)

These steps are only required when upgrading, troubleshooting, or resetting an installation.

### Disable EmComm Control in MeshMonitor

1. Open **MeshMonitor**
2. Go to **Info → Automation**
3. Disable Auto Responder rules pointing to `mm_emcomm_control.py`
4. Disable Timed Events pointing to the script if applicable
5. Click **Save**

### Remove runtime and state

Inside the MeshMonitor container:

```bash
docker exec -it meshmonitor sh
rm -f /data/scripts/mm_emcomm_control.py
rm -rf /data/scripts/mm_emcomm_control_data
exit
```

### Reinstall

1. Copy `mm_emcomm_control.py` to `/data/scripts/`
2. Make it executable
3. Recreate / re-enable the `^EMCOMM\b` rule
4. Optionally retain `^SET\b` for exercise compatibility
5. Recreate exercise Timed Events if desired
6. Click **Save**

---

## Versioning

This project follows semantic versioning in the same style as `meshmonitor-radio-id-qth`.

- **v1.0.0** — initial SET Exercise Control implementation
- **v2.0.0** — renamed to EmComm Control; adds dual LIVE / EXERCISE operation and the new `mm_emcomm_control.py` runtime
- **v2.0.1** — changes the MeshMonitor icon to 🚨 and documents city, county/regional, and state EOC deployments
- **v2.1.0** — adds the optional browser Operator Control Panel for one-click LIVE / EXERCISE switching and operational status
- **v2.2.0** — adds roster checkout, traffic precedence, and after-action CSV export (CLI and panel)
- **v2.3.0** — compressed ICS-213 / NTS-style formal traffic, TEST validation, replies, relays, multipart, 133-character default limit, generic exercise configuration
- **v2.4.0** — message tracking: delivery receipts (`RCVD`), status queries (`TRACK`), optional silent capture of mesh traffic, receive metadata (SNR/hops/channel), per-station activity summary

See [CHANGELOG.md](CHANGELOG.md) for details.

---

## ARRL trademark notice

ARRL® and related names and marks are trademarks of the American Radio Relay League, Incorporated.

EmComm Control is an independent, community-developed MeshMonitor tool. It may be used as part of an ARRL Simulated Emergency Test (SET), but it is **not affiliated with, sponsored by, endorsed by, or officially maintained by ARRL**. Likewise, it is not affiliated with or endorsed by FEMA, and it is not certified as an ICS-213, NTS, Winlink, ARES, or RACES implementation.

No ARRL logos or graphical trademarks are included with this project.

---

## License

This project is licensed under the MIT License.

See the [LICENSE](LICENSE) file for details.  
Full license text: https://opensource.org/licenses/MIT

---

## Contributing

Pull requests are welcome. Open an issue first to discuss ideas or report bugs.

---

## Acknowledgments

* MeshMonitor built by [Yeraze](https://github.com/Yeraze)
* Shout out to [South Dade GMRS Club](https://www.southdadegmrs.com/)

Discover other community-contributed scripts for MeshMonitor: https://meshmonitor.org/user-scripts.html
