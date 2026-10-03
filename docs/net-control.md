# Net Control automation

Optional automation for exercise Net Control. It can:

- send **scheduled announcements** before, during and at the end of an exercise
- **automatically acknowledge** compact SET check-ins addressed to Net Control
- log every automatic action for after-action review

Key properties:

- **Optional and off by default.** Nothing changes unless `mm_emcomm_config.json` has a `net_control` block with `"enabled": true`. Every switch defaults to off.
- **EXERCISE mode only.** In LIVE mode no exercise announcement is sent and no check-in is auto-acknowledged. Switching to LIVE stops all exercise automation immediately and drops queued announcements.
- **Organization-neutral.** Names, callsigns, places, times and message text all come from config. Nothing organization-specific is built into the code.
- **SET-safe aware.** With `"exercise_style": "set-safe"`, ACKs use `SET R`, and any announcement containing the word `TEST` is refused (logged, not sent).

---

## Configuration

Add a `net_control` block to `mm_emcomm_config.json`. The exercise `start` and `end` already in the config define the schedule and the check-in window, so they are not repeated here.

```json
"net_control": {
  "enabled": true,
  "name": "NET CONTROL",
  "operator_name": "",
  "callsign": "",
  "location": { "mode": "auto", "override": "" },
  "auto_checkin_ack": true,
  "checkin_ack_window": "exercise",
  "dedup_window_minutes": 3,
  "late_grace_minutes": 10,
  "allow_long_messages": false,
  "announcements": {
    "enabled": true,
    "before_start": [ { "minutes_before": 60, "message": "EXERCISE BEGINS IN 1 HOUR." } ],
    "at_start":     { "message": "EXERCISE IS NOW IN PROGRESS. SIMULATED TRAFFIC ONLY." },
    "during":       { "interval_minutes": 60, "message": "EXERCISE IN PROGRESS. SIMULATED TRAFFIC ONLY." },
    "before_end":   [ { "minutes_before": 15, "message": "EXERCISE ENDS IN 15 MINUTES." } ],
    "at_end":       { "message": "EXERCISE COMPLETE. THANK YOU FOR PARTICIPATING." },
    "set_start":    { "enabled": true, "message": "SET START | NET OPEN | ALL STATIONS PLEASE USE THE SET MESSAGE TEMPLATE | NET CONTROL ACTIVE" },
    "set_end":      { "enabled": true, "message": "SET COMPLETE | NET CLOSED | THANK YOU TO ALL STATIONS FOR PARTICIPATING | RETURNING CHANNEL TO NORMAL TRAFFIC" }
  },
  "channels": ["meshtastic:0", "meshcore:0"]
}
```

| Key | Default | Meaning |
|---|---|---|
| `enabled` | `false` | Master switch for all Net Control automation |
| `name`, `operator_name`, `callsign` | empty | Net Control identity (see below); all optional |
| `location.mode` | `auto` | `auto`, `override` or `none` |
| `location.override` | empty | Exercise-specific place name, e.g. a city or EOC name |
| `auto_checkin_ack` | `false` | Reply to valid check-ins |
| `checkin_ack_window` | `exercise` | `exercise`: only from `start` until before `end`. `always`: any time in EXERCISE mode |
| `dedup_window_minutes` | `3` | Duplicate-suppression window when no packet ID is available (1–120) |
| `late_grace_minutes` | `10` | How late a scheduled announcement may still go out (1–60) |
| `allow_long_messages` | `false` | Over-limit announcements are **refused** by default; `true` sends them in numbered parts. Never truncated |
| `announcements.enabled` | `false` | Switch for scheduled announcements |
| `announcements.set_start` / `set_end` | off | SET start (net open) / SET end (net closed) messages, each with its own `enabled` switch |
| `channels` | empty (any) | Channels selected for this SET, e.g. `"0"`, `"meshtastic:0"`, `"meshcore:1"`. Announcements and check-in ACKs are only sent on these |

Invalid values are ignored with a warning; nothing is guessed. Warnings are shown in the panel and by `--automation-status`.

### Identity

The reply identity is chosen in this order:

1. `operator_name` + `callsign` (e.g. `ERIC KI4XYZ`)
2. `name` + `callsign` (e.g. `NET CONTROL KI4XYZ`)
3. `callsign`
4. `name`
5. `operator_name`
6. `NET CONTROL`

### Location

The reply says `RECEIVED HERE IN <place>` only when a place is known:

1. **`location.override`.** An exercise-specific place name, so one installation can serve different EOCs or command posts.
2. **Auto mode.** The location Net Control's own callsign gave when it checked in (`EMCOMM CHECKIN <CALLSIGN> <LOCATION> …`).
3. **Otherwise none.** The reply is just `… | CHECKIN ACK | RECEIVED`. No location is ever invented.

**Exact GPS coordinates are never transmitted.** MeshMonitor exposes only the node's coordinates (`MM_LAT`/`MM_LON`), not a place name. EmComm Control adds no reverse-geocoding or network dependency, so coordinates are never turned into, or sent as, a location. The panel reports "node coordinates available, no place name (not transmitted)". Overrides that look like coordinates are rejected.

---

## Check-ins

Preferred compact format, sent on the exercise channel:

```text
SET R | NET CONTROL | <CALLSIGN OR NAME> | CHECKIN | FROM <LOCATION>
```

| Field | Meaning |
|---|---|
| `SET R` | Exercise marker and precedence (`TEST R` in the standard style) |
| `NET CONTROL` | To: Net Control (also matches `NCS`, the configured name, callsign or identity) |
| `<CALLSIGN OR NAME>` | From: the participant, e.g. `WRWJ781` or `ERIC WRZU598` |
| `CHECKIN` | Subject; must be exactly `CHECKIN` |
| `FROM <LOCATION>` | Message: where the participant is |

Example reply:

```text
SET R | NET CONTROL | WRWJ781 | CHECKIN | FROM CORAL SPRINGS, FLORIDA
→ SET R | WRWJ781 | NET CONTROL KI4XYZ | CHECKIN ACK | RECEIVED HERE IN <OVERRIDE PLACE>
```

The alternate order `SET R | <STATION> | NET CONTROL | CHECKIN | …` is also accepted and normalized, but the preferred format is the one above. Accepted check-ins are added to the roster with the reported location.

> **What the ACK means.** It confirms reception by the Net Control automation only. It does **not** mean formal traffic was delivered or handled, or that a served agency received anything.

### Loop and duplicate protection

- **No reply to replies:** only the exact subject `CHECKIN` is matched, so a `CHECKIN ACK` never triggers another reply.
- **No reply to Net Control:** a check-in whose sender contains `NET CONTROL`, or matches the configured callsign, name or identity, is ignored and logged.
- **Duplicates:** checked by MeshMonitor's `PACKET_ID` when available (Meshtastic). Otherwise (MeshCore) by a hash of network, source, channel, sender and text, within `dedup_window_minutes`. Suppressions are logged. Duplicate state is kept in `automation.json`, so a script restart doesn't re-acknowledge a recent packet.
- **Malformed lines** are ignored silently and never answered with HELP. This includes anything in pipe format that is not a valid check-in, such as relayed formal traffic.

### Check-in window

- With `checkin_ack_window: "exercise"`, ACKs are sent from `start` up to, but not including, `end`.
- Before the start, at or after the end, and at any time in LIVE mode, check-ins are logged as blocked and not answered.
- If `start`/`end` are not configured, EXERCISE mode alone governs.

---

## Scheduled announcements

| Item | Fires at | Key |
|---|---|---|
| `before_start` | `start − minutes_before` | `prestart-60`, `prestart-15`, … |
| `at_start` | `start` | `start` |
| `during` | every `interval_minutes` after start, **before** end | `during-60`, `during-120`, … |
| `before_end` | `end − minutes_before` | `preend-15`, … |
| `at_end` | `end` | `end` |

Scheduling rules:

- **Each item fires once per target.** The same message goes out on Meshtastic and on MeshCore, each exactly once.
- **Periodic warnings** are never sent at or after the end. They are also never stacked on an explicit item at the same minute.
- **Late runs:** an item is sent up to `late_grace_minutes` late. After that it is logged as **missed** and not sent, so a late start never floods the channel with old messages.
- **After the end:** no announcements fire, status becomes **COMPLETED**, and nothing remains in Upcoming.
- **Upcoming list:** fired (or skipped) items leave it. History stays in the log and the after-action export.
- **`--reset`** does not re-arm announcements that already went out. Fired state is kept in `automation.json`, separate from `state.json`.
- **Message text is used exactly as configured.**

### SET start and end messages

Two optional messages mark the net opening and closing:

| Message | Sent | Example |
|---|---|---|
| `set_start` | once, when the SET begins (`start`) | `SET START \| NET OPEN \| ALL STATIONS PLEASE USE THE SET MESSAGE TEMPLATE \| NET CONTROL ACTIVE` |
| `set_end` | once, when the SET ends (`end`) | `SET COMPLETE \| NET CLOSED \| THANK YOU TO ALL STATIONS FOR PARTICIPATING \| RETURNING CHANNEL TO NORMAL TRAFFIC` |

Behavior:

- **Independent switches:** each message has its own `enabled` switch, and each can be edited in the panel.
- **Exact timing:** the start message never goes out before the SET begins, and the end message never goes out before it ends. A scheduler that runs more than `late_grace_minutes` late logs the message as missed instead of sending it late.
- **No duplicates across restarts:** once sent, the record in `automation.json` prevents a repeat, even if the scheduler or MeshMonitor restarts.
- **Same-minute order:** when other announcements share the minute, the start message goes first and the end message last.
- **Logged as system-generated traffic:** each send is an `AUTO ANNOUNCEMENT` (`schedule_event` `set-start` / `set-end`, `system_generated: true`), shown in the panel's activity list and `automation_log.csv`.
- **Echo safe:** these lines begin with `SET`, so they match the `^SET\b` Auto Responder rule if they come back over the mesh. EmComm Control ignores pipe-format lines that are not commands, so an echo is never answered.

### SET channels

`channels` limits Net Control automation to the channels selected for the SET:

- **Entry format:** bare numbers match on either network; `meshtastic:N` or `meshcore:N` match one network only.
- **No selection means no restriction.**
- **What the script can and can't do:** MeshMonitor decides where output goes, either the Timed Event's channel or the channel the check-in arrived on. On any other channel, EmComm Control stays silent and logs the reason.
- **Meshtastic Timed Events** don't tell the script their channel, so add `--channel N` to their arguments, for example `--schedule-check --channel 0`. MeshCore Timed Events pass the channel automatically.
- **Direct-message check-ins** to Net Control are still acknowledged, by DM.

### After the SET ends

Once the SET has ended, its SET-specific automation closes:

- no further announcements or check-in ACKs
- the panel shows the start/end messages and channels read-only, and hides manual sends
- edits to them are refused

Identity settings stay editable. Configure a new SET by changing `start`/`end` in the config file.

### MeshMonitor setup

**1. Schedule check (Timed Event)**, one per network/channel that should carry announcements:

| Setting | Value |
|---|---|
| Schedule (cron) | `* * * * *` (every minute) |
| Script | `/data/scripts/mm_emcomm_control.py` |
| Arguments | `--schedule-check` (Meshtastic with SET channels: `--schedule-check --channel 0`) |
| Channel | The exercise channel |

The script prints nothing unless an announcement is due, so MeshMonitor sends nothing in between. Optional `--target NAME` labels the target in logs; by default the target is derived from MeshMonitor's `TIMER_ID` and source.

As an alternative, use one Timed Event per announcement with `--announcement <key>`, for example `--announcement start` with cron `0 9 3 10 *`. The schedule check is usually simpler because the times come from config.

**2. Check-ins (Auto Responder)**

| Style | Rule needed |
|---|---|
| SET-safe | The existing `^SET\b` rule already covers `SET R | …` lines; nothing to add. |
| Standard | Add a rule with trigger `^TEST\s+(R\|P\|W\|EMERGENCY)\s*\|`, the same script, and no arguments. |

**Local commands** (never transmitted):

```bash
mm_emcomm_control.py --automation-status     # identity, location, status, upcoming, warnings
```

---

## Message length

- **Recommended target:** 120 ASCII characters. **Hard limit:** 133 characters (`MM_EMCOMM_MAXLEN`).
- **Announcements:** configured announcements over the hard limit are **refused** (config warning, panel warning, skip logged) unless `allow_long_messages` is set, in which case they are sent in numbered parts.
- **Check-in ACKs:** if the location would push an ACK over the limit, the location is **omitted** (whole, never cut) and the reason is logged. If the ACK is still too long, it is not sent and the reason is logged.

---

## Operator panel

The **Net Control Automation** section shows:

- automation on/off, name, operator, callsign and display identity
- ACK and announcement switches
- location mode, detected location, override and effective location
- exercise style
- next scheduled announcement and last automatic transmission
- schedule status: `SCHEDULED`, `ACTIVE`, `COMPLETED`, `PAUSED (LIVE MODE)`, `DISABLED` or `NO SCHEDULE`
- the Timed Event targets seen
- the **Upcoming Automatic Messages** list
- recent automatic activity
- every configured announcement with its character count

After the end it shows **"Exercise completed — no scheduled announcements remaining."**

Controls:

- **Settings.** Enable or disable automation, ACKs and announcements, and edit name, operator name, callsign and the SET location override.
  - Changes are stored as **local overrides** in `automation.json`; the config file is never rewritten.
  - **Clear local overrides** restores the config values.
  - Inbound mesh messages can never change these settings.
- **Send a configured announcement.** Shows a preview (event, message, character count, target, mode, SET-safe status) and asks for confirmation. The panel cannot transmit by itself; the announcement is queued and sent by the next `--schedule-check` run on each target (about 1 minute; the queue expires after 10 minutes). It is refused in LIVE mode, after the end, or when the message breaks a length or SET-safe rule.

---

## Logging and exports

Every automatic action is logged as `kind: automation` with an `event`:

| Event | Meaning |
|---|---|
| `AUTO CHECKIN ACK` | ACK sent |
| `AUTO ACK SKIPPED` | Valid check-in not answered (automation off, ACK off, loop guard, length) |
| `AUTO ACK BLOCKED OUTSIDE WINDOW` | Before start / at or after end |
| `AUTO ACK BLOCKED LIVE MODE` | LIVE mode |
| `AUTO DUPLICATE SUPPRESSED` | Same packet/check-in already handled |
| `AUTO ANNOUNCEMENT` | Announcement sent (scheduled, CLI or panel-queued) |
| `AUTO ANNOUNCEMENT SKIPPED` | Due but not sent (LIVE, disabled, missed, length, TEST in set-safe) |
| `AUTO SCHEDULE COMPLETED` | All items handled after the end (per target) |
| `AUTO SETTINGS CHANGED` / `AUTO ANNOUNCEMENT QUEUED` | Panel actions |

Fields recorded where available: time, mode, target, network, channel, participant, incoming text, outgoing text, schedule event, location source, effective location and reason.

`--export` writes these to a new **`automation_log.csv`**, and `summary.txt` gains a Net Control automation count line. Existing CSV files keep their formats.

---

## MeshMonitor limitations

- **Reply routing is MeshMonitor's:** an Auto Responder reply goes back on the channel (or DM) the check-in arrived on. A script cannot pick a different channel, so a MeshCore check-in is answered on MeshCore and a Meshtastic check-in on Meshtastic.
- **Announcement channels** are set per Timed Event in MeshMonitor, not by the script.
- **Cron granularity is one minute.** Announcements go out within about a minute of their time.
- **No packet ID on MeshCore,** so MeshCore duplicates are detected by text within `dedup_window_minutes`.
- **Location data is coordinates only.** MeshMonitor exposes node coordinates, not place names, so automatic location comes from Net Control's own check-in location or the override.
- **Airtime cutoff:** MeshMonitor can pause automations when the mesh is congested. An announcement paused longer than `late_grace_minutes` is logged as missed.
