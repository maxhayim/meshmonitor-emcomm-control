# Changelog

All notable changes to EmComm Control are documented here.

## [2.3.0] - 2026-10-01

### Added
- Compressed ICS-213 / NTS-style formal traffic handling: `EMCOMM TRAFFIC <PREC> [RE:<ID>] 2:<TO> 3:<FROM> 4:<SUBJECT> 7:<MESSAGE>`.
- Structured ICS-213 Fields 1–8 support (2, 3, 4, 7 required; 1, 5, 6, 8 optional). Field 7 runs to the end of the message, so content such as `2:30` is preserved.
- NTS-style precedence `R` / `P` / `W` / `EMERGENCY`, normalized internally.
- TEST traffic validation for exercises: EXERCISE mode renders `TEST R` / `TEST P` / `TEST W` / `TEST EMERGENCY` and requires Field 7 to begin `TEST MESSAGE`. `MM_EMCOMM_TEST_PREFIX=auto` auto-prefixes instead of rejecting.
- Formal-message references/replies (`RE:EX-001`). A reply is a new message with its own traffic ID; the original is never modified.
- `EMCOMM RELAY <ID> [VIA <ROUTE>]`: relay metadata (`relayed_by`, `relay_time`, `relay_count`, `relay_route`) is logged separately, and the canonical unaltered message text is returned.
- Multipart formal traffic: inbound `EMCOMM TRAFFIC 1/2 …` / `2/2 …` buffered per sender; field-preserving multipart relay output with the same traffic ID and `k/n` numbering; `reassemble_serialized()` for receivers.
- Structured traffic logging (`traffic_id`, `precedence`, `test_traffic`, `field_1_incident` … `field_8_approved_by`, `reply_to`, `from_node`, `received_time`, `raw_input`, …) and a new `formal_traffic.csv` export (CLI and panel).
- Configurable 133-character default LoRa message limit (`MM_EMCOMM_MAXLEN`) with a 120-character recommended target (`MM_EMCOMM_RECOMMENDED_LEN`). Long responses are numbered `[1/2]`.
- Formal traffic UI in the operator panel: structured ICS-213 composer that generates the compact (and multipart) command, a live `current / maximum` character counter with a soft warning above 120, an EXERCISE / TEST or LIVE banner, and a formal traffic log table.
- Generic exercise configuration via optional `mm_emcomm_config.json` and/or environment variables: exercise name, ID, type, organization, incident name, start, end, and local instructions.
- Documented South Dade GMRS SET example (`docs/examples/south-dade-set-2026.md`), clearly labeled as an example and not a default.
- `docs/formal-traffic.md` standards and compliance reference.
- Expanded automated tests (81 total).

### Changed
- Default maximum message length is now 133 characters (was 190).
- HELP is split into concise TACTICAL and FORMAL messages, each within the limit.
- All exercise injects now begin `TEST EXERCISE INJECT N` and fit the configured limit. Inject 6 now specifically starts the formal (ICS-213 / NTS-style) traffic phase; Inject 5 is the tactical traffic phase.
- Formal traffic ACKs now read `TEST ACK EX-003 TO EOC LOGGED. PREC TEST P. NOT A DELIVERY CONFIRMATION.` (LIVE: `LIVE ACK …`, never TEST).
- Mesh-emitted text uses ASCII hyphens instead of em dashes.
- Invalid `MM_EMCOMM_MAXLEN` values fall back to the default instead of crashing.
- Improved standards/compliance documentation: no certification or endorsement claimed, and internal traffic IDs are explicitly not NTS message numbers.

### Compatibility
- Legacy `EMCOMM TRAFFIC <TO> [ROUTINE|PRIORITY|IMMEDIATE] <TEXT>` remains supported and is normalized into the structured model. Legacy `IMMEDIATE` (not an NTS precedence) is logged as `P` with `legacy_precedence=IMMEDIATE`, and the ACK states the mapping.
- Pre-2.3 traffic log records are upgraded in memory for display and export; `traffic.jsonl` is not rewritten. Older `state.json` files load unchanged.
- Tactical commands (`CHECKIN`, `CHECKOUT`, `SITREP`, `STATUS`) and LIVE-mode safeguards are unchanged.

## [2.2.0] - 2026-09-09

### Added
- `EMCOMM CHECKOUT <CALLSIGN>` mesh command, `--checkout` CLI flag, and a per-row Remove button in the operator panel to correct the roster without waiting for a fresh check-in.
- Optional precedence on message traffic: `EMCOMM TRAFFIC <TO> [ROUTINE|PRIORITY|IMMEDIATE] <TEXT>` (defaults to ROUTINE), recorded in the traffic log and echoed in the ACK.
- After-action export: `--export [DIR]` CLI flag and CSV download links in the operator panel produce `roster.csv`, `traffic_log.csv`, and a `summary.txt` for drill/incident review.
- `tests/` pytest suite covering mode gating, command parsing, roster/checkout behavior, export output, and panel auth.
- CI workflow that runs the test suite on push and pull request.

### Fixed
- Operator panel `/logout` now actually clears the session cookie instead of redirecting without ending the session.

## [2.1.0] - 2026-09-09

### Added
- Optional `mm_emcomm_panel.py` browser Operator Control Panel.
- One-click confirmed LIVE / EXERCISE mode switching.
- Dashboard counts for check-ins, SITREPs, traffic records, and events.
- Checked-in station and recent operational-log tables.
- Localhost-only default binding and required token authentication for LAN binds.
- Native MeshMonitor script-action metadata proposal for future upstream support.

### Changed
- Version bumped to 2.1.0.
- Documentation now includes local, EOC/LAN, and Docker-sidecar panel deployment examples.
- Corrected documented Python baseline to 3.9+ because the runtime uses `zoneinfo`.

## [2.0.1] - 2026-09-09

### Changed
- Changed the MeshMonitor script-picker emoji from 📡 to 🚨.
- Added explicit deployment guidance for city/municipal, county/regional, and state Emergency Operations Centers (EOCs).
- Expanded GitHub Pages and README positioning for government EOC communications-support workflows.

## v2.0.0 — EmComm Control / LIVE + EXERCISE

### Renamed
- Project renamed from SET Exercise Control to **EmComm Control**.
- Runtime renamed from `mm_arrl_set.py` to `mm_emcomm_control.py`.
- Runtime state moved to `mm_emcomm_control_data/`.

### Added
- **LIVE mode** for real-world operator-entered emergency-communications traffic.
- **EXERCISE mode** for drills, ARRL® SET use, and simulated injects.
- `EMCOMM` command prefix for both modes.
- Local-only mode administration with `--mode exercise`, `--mode live --confirm-live`, and `--mode status`.
- Operator-supplied `--announce` support.
- Mode-aware traffic IDs (`EC-###` for LIVE and `EX-###` for EXERCISE).
- Mode field in JSONL event logs.
- Best-effort migration from the legacy `mm_arrl_set_data/` state directory.

### Safety / operational behavior
- LIVE mode cannot be enabled by inbound mesh traffic.
- Simulated exercise injects are blocked in LIVE mode.
- The legacy `SET` prefix is disabled while LIVE.
- LIVE mode never fabricates incident conditions; it only acknowledges and logs operator-supplied information.
- Delivery acknowledgments explicitly state that logging does not guarantee delivery to the named recipient.

### Compatibility
- Legacy `SET CHECKIN`, `SET SITREP`, `SET TRAFFIC`, `SET STATUS`, and `SET HELP` remain available in EXERCISE mode.
- Python standard-library only; no pip dependencies.

## v1.0.0 — Initial SET Exercise Control

- Initial MeshMonitor exercise-control runtime.
- Check-ins, SITREPs, simulated traffic logging, status, and eight timed exercise injects.
- Explicit EXERCISE / SIMULATED labeling.
- GitHub Pages documentation and standard project files.
