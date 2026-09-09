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

# Changelog

All notable changes to EmComm Control are documented here.

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
