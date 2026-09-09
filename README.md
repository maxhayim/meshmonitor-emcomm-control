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

This repository contains:
- **mm_emcomm_control.py** — the actual MeshMonitor Auto Responder / Timed Event script (runtime)
- **mm_emcomm_panel.py** — optional browser-based operator control panel for LIVE / EXERCISE mode and status
- **docs/** — GitHub Pages documentation (display only)

---

## What this does

EmComm Control allows operators to:

- Check in with callsign, location, power source, and role
- Submit and log SITREPs
- Log addressed message traffic with unique traffic IDs
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
- Current station/check-in, SITREP, traffic, and event counts
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

All exercise responses are explicitly labeled **EXERCISE** and/or **SIMULATED**. Timed simulated injects are available only in this mode.

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
- Cannot be enabled by an inbound mesh message

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
├── docs/                   # GitHub Pages documentation
│   ├── index.html
│   └── index.js
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

---

## Mesh commands

```text
EMCOMM CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE>
EMCOMM SITREP <LOCATION> <STATUS>
EMCOMM TRAFFIC <TO> <TEXT>
EMCOMM STATUS
EMCOMM HELP
```

### Example — LIVE or EXERCISE

```text
EMCOMM CHECKIN W4ABC MIAMI-EOC BATTERY NCS
EMCOMM SITREP SHELTER-1 COMMERCIAL-POWER-DOWN RF-LINK-GOOD
EMCOMM TRAFFIC EOC REQUEST-20-CASES-WATER
EMCOMM STATUS
```

### Legacy exercise compatibility

While in EXERCISE mode, the original syntax remains valid:

```text
SET CHECKIN W4ABC MIAMI-EOC BATTERY NCS
SET SITREP SHELTER-1 RF-LINK-GOOD
SET TRAFFIC EOC TEST-MESSAGE
SET STATUS
```

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
10:30  Inject 5 — simulated message-traffic phase
11:00  Inject 6 — simulated formal-message / ICS-213 phase
11:30  Inject 7 — simulated partial restoration
12:00  Inject 8 — end of exercise
```

If an inject is invoked while LIVE, the script refuses to transmit it.

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

The state file stores the current mode, participants/stations, counts, and exercise state. The JSONL log records check-ins, SITREPs, message traffic, announcements, mode changes, and exercise injects.

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

See [CHANGELOG.md](CHANGELOG.md) for details.

---

## ARRL trademark notice

ARRL® and related names and marks are trademarks of the American Radio Relay League, Incorporated.

EmComm Control is an independent, community-developed MeshMonitor tool. It may be used as part of an ARRL Simulated Emergency Test (SET), but it is **not affiliated with, sponsored by, endorsed by, or officially maintained by ARRL**.

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
