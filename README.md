<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.8%2B-blue" alt="Python Version">
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-green" alt="License">
  </a>
</p>

# 🚨 SET Exercise Control

An unofficial ARRL Simulated Emergency Test (SET) exercise-control Script for [**MeshMonitor**](https://github.com/Yeraze/MeshMonitor), supporting simulated emergency communications over [**Meshtastic**](https://meshtastic.org/), [**MeshCore**](https://meshcore.io), or any other mesh network MeshMonitor supports.

This repository contains:
- **mm_arrl_set.py** — the actual MeshMonitor Auto Responder / Timed Event script (runtime)
- **docs/** — GitHub Pages documentation (display only)

---

## What this does

This MeshMonitor script allows operators to:

- Check in with callsign, location, power source, and role
- Submit simulated SITREPs
- Log simulated message traffic
- Request current exercise statistics
- Run scheduled exercise injects using MeshMonitor Timed Events
- Retain exercise logs for after-action review

Every generated exercise message is explicitly marked **EXERCISE** and/or **SIMULATED**.

---

## Repository layout
<pre>
├── mm_arrl_set.py          # Runtime script used by MeshMonitor
├── docs/
│   ├── index.html
│   └── index.js
├── ISSUE_TEMPLATE/
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE
└── README.md
</pre>

---

## IMPORTANT: Which file do I use?

### Use this file in MeshMonitor

mm_arrl_set.py

This is the **only file** MeshMonitor should execute.

### Do NOT run these files

docs/index.html  
docs/index.js

These files only display documentation on GitHub Pages.

---

## Installing mm_arrl_set.py

The script must exist inside the MeshMonitor environment at:

/data/scripts/mm_arrl_set.py

Make it executable:

chmod +x /data/scripts/mm_arrl_set.py

---

## MeshMonitor Auto Responder configuration

Create one Auto Responder rule.

Trigger regex:

^SET\b

Action: Script  
Script path:

/data/scripts/mm_arrl_set.py

---

## Commands

SET CHECKIN <CALLSIGN> <LOCATION> <POWER> <ROLE>  
SET SITREP <LOCATION> <STATUS>  
SET TRAFFIC <TO> <TEXT>  
SET STATUS  
SET HELP

---

## Example usage

SET CHECKIN W4ABC MIAMI-EOC BATTERY NCS  
SET SITREP SHELTER-1 COMMERCIAL-POWER-DOWN RF-LINK-GOOD  
SET TRAFFIC EOC REQUEST-20-CASES-WATER  
SET STATUS  
SET HELP

---

## MeshMonitor Timed Events

Use the same script with:

--inject 1  
--inject 2  
--inject 3  
--inject 4  
--inject 5  
--inject 6  
--inject 7  
--inject 8

---

## Resetting the exercise

/data/scripts/mm_arrl_set.py --reset

---

## Trademark Notice

ARRL® and related names and marks are trademarks of the American Radio Relay League, Incorporated.

This project is an independent, community-developed tool intended for simulated emergency communications exercises. It is not affiliated with, sponsored by, endorsed by, or officially maintained by ARRL.

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
