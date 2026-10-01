#!/usr/bin/env python3
"""Local browser control panel for EmComm Control.

The panel changes the same state used by mm_emcomm_control.py, so operators can
switch LIVE / EXERCISE mode without shell access after the panel is started.

Security defaults:
- Binds to 127.0.0.1 by default.
- Refuses non-loopback binding unless an access token is configured.
- Uses an HttpOnly, SameSite=Strict session cookie when token auth is enabled.
- Contains no external web assets or Python dependencies.
"""

import argparse
import csv
import hashlib
import hmac
import html
import io
import json
import os
import secrets
import sys
import webbrowser
from collections import deque
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

import mm_emcomm_control as control

PANEL_VERSION = "2.3.0"
DEFAULT_HOST = os.getenv("MM_EMCOMM_PANEL_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("MM_EMCOMM_PANEL_PORT", "8787"))
DEFAULT_TOKEN = os.getenv("MM_EMCOMM_PANEL_TOKEN", "")
COOKIE_NAME = "emcomm_panel_auth"


def is_loopback(host):
    return host.lower() in {"127.0.0.1", "localhost"}


def mode_name(mode):
    return "LIVE" if mode == "live" else "EXERCISE"


def read_recent_events(limit=40):
    if not control.LOG_FILE.exists():
        return []
    rows = []
    try:
        with control.LOG_FILE.open("r", encoding="utf-8") as f:
            lines = deque(f, maxlen=limit)
        for line in reversed(lines):
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append(item)
            except Exception:
                continue
    except Exception:
        return []
    return rows


def panel_change_mode(mode):
    if mode not in {"live", "exercise"}:
        raise ValueError("invalid mode")
    state = control.load_state()
    previous = state.get("mode", "exercise")
    if previous == mode:
        return f"Already in {mode_name(mode)} mode."
    state["mode"] = mode
    state["last_inject"] = 0
    if mode == "exercise":
        state["exercise"] = control.EXERCISE_NAME
    control.save_state(state)
    control.log_event(
        "mode_change",
        "web-panel",
        f"{previous} -> {mode}",
        {"source": "operator_control_panel"},
    )
    return f"Mode changed to {mode_name(mode)}."


def panel_reset():
    current = control.load_state()
    mode = current.get("mode", "exercise")
    state = control.default_state(mode)
    control.save_state(state)
    control.log_event(
        "reset",
        "web-panel",
        f"{mode_name(mode)} state reset from operator panel",
        {"source": "operator_control_panel"},
    )
    return f"{mode_name(mode)} counters and current operational state reset."


def panel_checkout(callsign):
    callsign = (callsign or "").strip().upper()
    state = control.load_state()
    participants = state.get("participants", {}) or {}
    if callsign not in participants:
        return f"{callsign} not found on roster."
    del participants[callsign]
    state["participants"] = participants
    state["events"] = int(state.get("events", 0)) + 1
    control.save_state(state)
    control.log_event(
        "checkout",
        "web-panel",
        f"Removed {callsign} from roster",
        {"callsign": callsign, "source": "operator_control_panel"},
    )
    return f"Removed {callsign} from roster."


def build_csv(rows, fieldnames):
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


COMPOSE_FIELDS = [
    # (form name, ICS key, label, required)
    ("incident", "1", "1. Incident Name (optional)", False),
    ("to", "2", "2. To", True),
    ("from", "3", "3. From", True),
    ("subject", "4", "4. Subject", True),
    ("date", "5", "5. Date (optional)", False),
    ("time", "6", "6. Time (optional)", False),
    ("message", "7", "7. Message", True),
    ("approved", "8", "8. Approved By (optional)", False),
]
PRECEDENCE_CHOICES = [("R", "R - Routine"), ("P", "P - Priority"), ("W", "W - Welfare"), ("EMERGENCY", "EMERGENCY")]


def compose_from_form(form, mode):
    """Turn panel form values into validated EMCOMM TRAFFIC command(s).

    The panel only generates commands for the operator to send from a Meshtastic
    or MeshCore client; it does not transmit or log traffic itself.
    """
    exercise = mode != "live"
    precedence = (form.get("precedence") or "R").strip().upper()
    if precedence not in control.PRECEDENCE_NAMES:
        precedence = "R"
    traffic = control.FormalTraffic(precedence=precedence)
    for name, key, _, _ in COMPOSE_FIELDS:
        value = control.normalize(form.get(name, ""))
        if value:
            traffic.fields[key] = value
    errors = []
    reply = control.normalize(form.get("reply_to", "")).upper()
    if reply:
        if control.TRAFFIC_ID_RE.match(reply):
            traffic.reply_to = reply
        else:
            errors.append("REPLY TO MUST BE ONE TRAFFIC ID, E.G. EX-001")
    errors += control.validate_formal(traffic, exercise, auto_prefix=False)
    commands = []
    if not errors:
        try:
            commands = control.compose_traffic_command(traffic)
        except control.TrafficError as exc:
            errors.append(str(exc))
    return {
        "errors": errors,
        "commands": [{"text": c, "report": control.length_report(c)} for c in commands],
    }


# Live character counter for the formal-traffic composer. Mirrors the single-part
# command built by control.compose_traffic_command; the server-side result is
# authoritative and also handles multipart splitting.
COUNTER_SCRIPT = """
(function(){
  var form = document.getElementById('compose'); if(!form) return;
  var max = +form.dataset.max, rec = +form.dataset.rec, ex = form.dataset.exercise === '1';
  var counter = document.getElementById('counter'), warn = document.getElementById('counter-warn');
  function val(n){ var e = form.elements[n]; return e ? e.value.replace(/\\s+/g,' ').trim() : ''; }
  function update(){
    var cmd = 'EMCOMM TRAFFIC ' + (ex ? 'TEST ' : '') + val('precedence');
    var re = val('reply_to'); if(re) cmd += ' RE:' + re.toUpperCase();
    form.querySelectorAll('[data-field]').forEach(function(e){
      var v = e.value.replace(/\\s+/g,' ').trim(); if(v) cmd += ' ' + e.dataset.field + ':' + v;
    });
    counter.textContent = cmd.length + ' / ' + max;
    warn.textContent = cmd.length > max ? ' Exceeds configured limit; will be generated as multipart.'
      : (cmd.length > rec ? ' Recommended LoRa target exceeded.' : '');
  }
  form.addEventListener('input', update); update();
})();
"""


def formal_traffic_recent(limit=25):
    rows = control.formal_traffic_rows()
    return list(reversed(rows[-limit:]))


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, token=""):
        super().__init__(address, handler)
        self.panel_token = token
        self.auth_digest = hashlib.sha256(token.encode("utf-8")).hexdigest() if token else ""


class Handler(BaseHTTPRequestHandler):
    server_version = f"EmCommPanel/{PANEL_VERSION}"

    def log_message(self, fmt, *args):
        sys.stderr.write("[panel] %s - %s\n" % (self.address_string(), fmt % args))

    def common_headers(self, content_type="text/html; charset=utf-8", nonce=""):
        script_src = f" script-src 'nonce-{nonce}';" if nonce else ""
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            f"default-src 'none'; style-src 'unsafe-inline';{script_src} form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )

    def send_html(self, body, status=200, extra_headers=None, nonce=""):
        data = body.encode("utf-8")
        self.send_response(status)
        self.common_headers(nonce=nonce)
        if extra_headers:
            for key, value in extra_headers:
                self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.common_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_csv(self, filename, data):
        payload = data.encode("utf-8")
        self.send_response(200)
        self.common_headers("text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, path):
        self.send_response(303)
        self.send_header("Location", path)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def form(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 32768:
            raise ValueError("request too large")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return parse_qs(raw, keep_blank_values=True)

    def authorized(self):
        if not self.server.auth_digest:
            return True
        jar = cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie", ""))
        except Exception:
            return False
        morsel = jar.get(COOKIE_NAME)
        if not morsel:
            return False
        return hmac.compare_digest(morsel.value, self.server.auth_digest)

    def require_auth(self):
        if self.authorized():
            return True
        if self.command == "GET":
            self.send_html(self.login_page())
        else:
            self.send_html(self.login_page("Authentication required."), status=403)
        return False

    def login_page(self, error=""):
        notice = f'<div class="notice bad">{esc(error)}</div>' if error else ""
        return self.layout(
            "Login",
            f"""
            <section class="card narrow">
              <h1>🚨 EmComm Control Panel</h1>
              <p>This panel requires the local access token.</p>
              {notice}
              <form method="post" action="/login">
                <label>Access token</label>
                <input type="password" name="token" autocomplete="current-password" required autofocus>
                <button class="primary" type="submit">Sign in</button>
              </form>
            </section>
            """,
        )

    def layout(self, title, body, script="", nonce=""):
        script_tag = f'<script nonce="{nonce}">{script}</script>' if script and nonce else ""
        return f"""<!doctype html>
        <html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
        <title>{esc(title)} · EmComm Control</title>
        <style>
        :root{{--bg:#0b0f17;--card:#121a28;--card2:#0f1624;--text:#edf3ff;--muted:#aebbd4;--border:#273650;--blue:#388bfd;--red:#ef4444;--yellow:#f59e0b;--green:#22c55e}}
        *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:16px system-ui,-apple-system,Segoe UI,Roboto,sans-serif}}
        a{{color:#7db6ff}} .wrap{{max-width:1180px;margin:auto;padding:24px}} header{{display:flex;justify-content:space-between;gap:16px;align-items:center;flex-wrap:wrap;margin-bottom:20px}}
        h1,h2,h3{{margin-top:0}} .muted{{color:var(--muted)}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}}
        .card{{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;margin:14px 0}} .narrow{{max-width:520px;margin:70px auto}}
        .metric{{font-size:2rem;font-weight:750}} .pill{{display:inline-block;border-radius:999px;padding:7px 12px;font-weight:750}} .live{{background:#3f1015;color:#fecaca;border:1px solid #7f1d1d}} .exercise{{background:#3d2a08;color:#fde68a;border:1px solid #92400e}}
        .actions{{display:flex;flex-wrap:wrap;gap:12px}} button,.button{{display:inline-block;border:0;border-radius:10px;padding:13px 16px;font-weight:700;text-decoration:none;cursor:pointer;background:#24324a;color:var(--text)}}
        button.primary,.button.primary{{background:var(--blue);color:white}} button.danger,.button.danger{{background:var(--red);color:white}} button.warn,.button.warn{{background:var(--yellow);color:#111827}} button.good,.button.good{{background:var(--green);color:#052e16}}
        input,select,textarea{{width:100%;margin:8px 0 14px;padding:12px;border-radius:9px;border:1px solid var(--border);background:#0a101b;color:var(--text)}} label{{font-weight:650}}
        table{{width:100%;border-collapse:collapse;font-size:.93rem}} th,td{{text-align:left;border-bottom:1px solid var(--border);padding:9px 7px;vertical-align:top}} th{{color:var(--muted)}} .scroll{{overflow:auto}}
        .notice{{padding:12px 14px;border-radius:10px;margin:12px 0;background:#13223b;border:1px solid #27486f}} .notice.bad{{background:#3f1015;border-color:#7f1d1d}} .notice.good{{background:#0c2f20;border-color:#166534}}
        code,pre{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}} pre.cmd{{white-space:pre-wrap;word-break:break-all;background:#0a101b;border:1px solid var(--border);border-radius:9px;padding:10px;margin:6px 0}}
        .banner{{padding:14px 16px;border-radius:12px;margin:12px 0;font-weight:700}} .banner.exercise{{background:#3d2a08;color:#fde68a;border:1px solid #92400e}} .banner.live{{background:#3f1015;color:#fecaca;border:1px solid #7f1d1d}}
        .formgrid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:0 14px}} .wide{{grid-column:1/-1}} .counter{{font-weight:700}} .warn-text{{color:#fbbf24}} .bad-text{{color:#fca5a5}} footer{{color:var(--muted);margin-top:24px;font-size:.9rem}}
        </style></head><body><div class="wrap">{body}<footer>EmComm Control Panel v{PANEL_VERSION} · Local operator interface</footer></div>{script_tag}</body></html>"""

    def compose_card(self, mode, form=None, result=None):
        exercise = mode != "live"
        form = dict(form or {})
        if not form:
            form["incident"] = control.CONFIG.get("incident_name", "")
            form["precedence"] = "R"
            form["message"] = "TEST MESSAGE " if exercise else ""
        options = "".join(
            f'<option value="{esc(v)}"{" selected" if form.get("precedence") == v else ""}>{esc(lbl)}</option>'
            for v, lbl in PRECEDENCE_CHOICES
        )
        inputs = []
        for name, key, label, required in COMPOSE_FIELDS:
            req = " required" if required else ""
            value = esc(form.get(name, ""))
            if key == "7":
                hint = "Must begin TEST MESSAGE in EXERCISE mode." if exercise else "Sent exactly as entered. LIVE mode never adds TEST."
                inputs.append(
                    f'<div class="wide"><label for="f-{name}">{esc(label)}</label>'
                    f'<textarea id="f-{name}" name="{name}" rows="3"{req} data-field="{key}">{value}</textarea>'
                    f'<div class="muted">{esc(hint)}</div></div>'
                )
            else:
                inputs.append(
                    f'<div><label for="f-{name}">{esc(label)}</label>'
                    f'<input id="f-{name}" name="{name}" value="{value}"{req} data-field="{key}"></div>'
                )
        out = ""
        if result:
            if result["errors"]:
                out = '<div class="notice bad">' + "<br>".join(esc(e) for e in result["errors"]) + "</div>"
            else:
                rows = []
                for i, cmd in enumerate(result["commands"], 1):
                    rep = cmd["report"]
                    cls = "bad-text" if rep["over_limit"] else ("warn-text" if rep["over_recommended"] else "")
                    part = f"Part {i}/{len(result['commands'])} · " if len(result["commands"]) > 1 else ""
                    rows.append(
                        f'<pre class="cmd">{esc(cmd["text"])}</pre>'
                        f'<div class="muted {cls}">{part}{rep["length"]} / {rep["limit"]} {esc(rep["warning"])}</div>'
                    )
                out = (
                    '<div class="notice good">Send the command(s) below from your Meshtastic or MeshCore client, in order. '
                    "The panel does not transmit or log traffic; EmComm Control logs it when received.</div>" + "".join(rows)
                )
        mode_hint = (
            "EXERCISE / TEST: the system marks this traffic TEST (e.g. TEST P). Field 7 must begin TEST MESSAGE."
            if exercise else "LIVE: real-world traffic. Nothing is added; do not include exercise markings."
        )
        return f"""
        <section class="card"><h2>Formal traffic (ICS-213 / NTS-style)</h2>
        <p class="muted">Compressed ICS-213-compatible fields with NTS-style precedence. Generates the compact <code>EMCOMM TRAFFIC</code> command. {esc(mode_hint)}</p>
        <form method="post" action="/traffic/compose" id="compose" data-exercise="{'1' if exercise else '0'}" data-max="{control.MAX_LEN}" data-rec="{control.RECOMMENDED_LEN}">
          <div class="formgrid">
            <div><label for="f-precedence">Precedence</label><select id="f-precedence" name="precedence">{options}</select></div>
            <div><label for="f-reply">Reply To (optional traffic ID)</label><input id="f-reply" name="reply_to" value="{esc(form.get('reply_to', ''))}" placeholder="EX-001"></div>
            {''.join(inputs)}
          </div>
          <div class="actions"><button class="primary" type="submit">Generate command</button>
          <span class="counter" id="counter">— / {control.MAX_LEN}</span><span id="counter-warn" class="warn-text"></span></div>
        </form>
        {out}
        </section>"""

    def dashboard(self, message="", form=None, result=None):
        state = control.load_state()
        mode = state.get("mode", "exercise")
        mode_class = "live" if mode == "live" else "exercise"
        participants = state.get("participants", {}) or {}
        events = read_recent_events(40)
        formal = formal_traffic_recent(25)
        notice = f'<div class="notice good">{esc(message)}</div>' if message else ""
        cfg = control.CONFIG

        station_rows = "".join(
            f"<tr><td><strong>{esc(call)}</strong></td><td>{esc(info.get('location'))}</td><td>{esc(info.get('power'))}</td><td>{esc(info.get('role'))}</td><td>{esc(info.get('time'))}</td>"
            f"<td><form method=\"post\" action=\"/action/checkout\"><input type=\"hidden\" name=\"callsign\" value=\"{esc(call)}\"><button class=\"warn\" type=\"submit\">Remove</button></form></td></tr>"
            for call, info in sorted(participants.items())
        ) or '<tr><td colspan="6" class="muted">No stations checked in.</td></tr>'

        event_rows = "".join(
            f"<tr><td>{esc(item.get('time'))}</td><td>{esc(item.get('mode'))}</td><td>{esc(item.get('kind'))}</td><td>{esc(item.get('from_node'))}</td><td>{esc(item.get('message'))}</td></tr>"
            for item in events
        ) or '<tr><td colspan="5" class="muted">No events logged yet.</td></tr>'

        formal_rows = "".join(
            f"<tr><td><strong>{esc(r.get('traffic_id'))}</strong></td>"
            f"<td>{esc(control.precedence_display(r.get('precedence', ''), r.get('test_traffic')))}</td>"
            f"<td>{esc(r.get('field_2_to'))}</td><td>{esc(r.get('field_3_from'))}</td><td>{esc(r.get('field_4_subject'))}</td>"
            f"<td>{esc(r.get('field_7_message'))}</td><td>{esc(r.get('reply_to'))}</td><td>{esc(r.get('relay_count'))}</td>"
            f"<td>{esc(r.get('received_time'))}</td></tr>"
            for r in formal
        ) or '<tr><td colspan="9" class="muted">No formal traffic logged yet.</td></tr>'

        live_action = (
            '<span class="button good">LIVE is active</span>'
            if mode == "live"
            else '<form method="post" action="/confirm/live"><button class="danger" type="submit">Activate LIVE</button></form>'
        )
        exercise_action = (
            '<span class="button warn">EXERCISE is active</span>'
            if mode == "exercise"
            else '<form method="post" action="/confirm/exercise"><button class="warn" type="submit">Switch to EXERCISE</button></form>'
        )
        if mode == "live":
            banner = '<div class="banner live">LIVE MODE — real-world traffic. No TEST markings are added. Simulated injects are blocked.</div>'
        else:
            banner = '<div class="banner exercise">EXERCISE / TEST MODE — all traffic is simulated. Formal message text (Field 7) must begin TEST MESSAGE.</div>'
        details = [
            ("Exercise", state.get("exercise") or cfg.get("exercise_name")), ("ID", cfg.get("exercise_id")),
            ("Type", cfg.get("exercise_type")), ("Organization", cfg.get("organization")),
            ("Incident", cfg.get("incident_name")), ("Start", cfg.get("start")), ("End", cfg.get("end")),
        ]
        exercise_info = " · ".join(f"{esc(k)}: <strong>{esc(v)}</strong>" for k, v in details if v)

        body = f"""
        <header><div><h1>🚨 EmComm Control Panel</h1><div class="muted">Operator controls for LIVE and EXERCISE operations</div></div><div><span class="pill {mode_class}">{mode_name(mode)}</span></div></header>
        {banner}
        {notice}
        <section class="card"><h2>Mode control</h2><div class="actions">{live_action}{exercise_action}<a class="button primary" href="/">Refresh Status</a><form method="post" action="/confirm/reset"><button type="submit">Reset Operation</button></form></div><p class="muted">LIVE changes are deliberate and require a second confirmation screen. Simulated injects remain blocked while LIVE.</p><p class="muted">{exercise_info}</p></section>
        <section class="grid">
          <div class="card"><div class="muted">Checked-in stations</div><div class="metric">{len(participants)}</div></div>
          <div class="card"><div class="muted">SITREPs</div><div class="metric">{int(state.get('sitreps',0))}</div></div>
          <div class="card"><div class="muted">Traffic records</div><div class="metric">{int(state.get('traffic_count',0))}</div></div>
          <div class="card"><div class="muted">Logged events</div><div class="metric">{int(state.get('events',0))}</div></div>
        </section>
        {self.compose_card(mode, form, result)}
        <section class="card"><h2>Formal traffic log</h2><div class="scroll"><table><thead><tr><th>ID</th><th>Prec</th><th>2. To</th><th>3. From</th><th>4. Subject</th><th>7. Message</th><th>RE</th><th>Relays</th><th>Received</th></tr></thead><tbody>{formal_rows}</tbody></table></div><p class="muted">IDs are internal EmComm Control identifiers, not NTS message numbers. A logged ACK confirms receipt by EmComm Control, not delivery to the addressee.</p></section>
        <section class="card"><h2>Check-ins</h2><div class="scroll"><table><thead><tr><th>Callsign</th><th>Location</th><th>Power</th><th>Role</th><th>Last check-in</th><th>Actions</th></tr></thead><tbody>{station_rows}</tbody></table></div><p class="muted">Removing a station only corrects the roster; it does not notify the station and can be redone by checking in again.</p></section>
        <section class="card"><h2>Recent operational log</h2><div class="scroll"><table><thead><tr><th>Time</th><th>Mode</th><th>Type</th><th>Source</th><th>Details</th></tr></thead><tbody>{event_rows}</tbody></table></div></section>
        <section class="card"><h2>After-action export</h2><p class="muted">Download the current roster, full traffic/event log, and structured formal traffic as CSV for drill or incident review.</p><div class="actions"><a class="button primary" href="/export/roster.csv">Download roster CSV</a><a class="button primary" href="/export/traffic.csv">Download traffic log CSV</a><a class="button primary" href="/export/formal_traffic.csv">Download formal traffic CSV</a></div></section>
        <section class="card"><h2>Operational note</h2><p>This panel changes EmComm Control state and displays its local logs. It does not replace an EOC incident-management, dispatch, CAD, records, or approved emergency communications system, the official ICS-213 form, Winlink forms, or NTS radiogram software.</p><p class="muted">For LAN access, run with an access token and place the panel only on a trusted management network or behind an authenticated TLS reverse proxy.</p></section>
        """
        nonce = secrets.token_urlsafe(16)
        return self.layout("Dashboard", body, script=COUNTER_SCRIPT, nonce=nonce), nonce

    def confirmation(self, action):
        if action == "live":
            title = "Activate LIVE mode?"
            text = "Real operational traffic may be logged and transmitted through your configured MeshMonitor workflows. Simulated injects will be blocked."
            button = '<button class="danger" type="submit">Yes — Activate LIVE</button>'
            hidden = '<input type="hidden" name="mode" value="live"><input type="hidden" name="confirmed" value="yes">'
            target = "/action/mode"
        elif action == "exercise":
            title = "Switch to EXERCISE mode?"
            text = "Future EmComm responses will be marked as exercise/simulated traffic and SET compatibility will be enabled."
            button = '<button class="warn" type="submit">Yes — Switch to EXERCISE</button>'
            hidden = '<input type="hidden" name="mode" value="exercise"><input type="hidden" name="confirmed" value="yes">'
            target = "/action/mode"
        else:
            title = "Reset operation?"
            text = "This clears current station/check-in counters and operational state while preserving the active LIVE/EXERCISE mode. Existing JSONL log history is retained."
            button = '<button class="danger" type="submit">Yes — Reset Operation</button>'
            hidden = '<input type="hidden" name="confirmed" value="yes">'
            target = "/action/reset"
        return self.layout(
            "Confirm",
            f'<section class="card narrow"><h1>{esc(title)}</h1><p>{esc(text)}</p><div class="actions"><form method="post" action="{target}">{hidden}{button}</form><a class="button" href="/">Cancel</a></div></section>',
        )

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self.send_json({"ok": True, "panelVersion": PANEL_VERSION})
            return
        if parsed.path == "/login":
            self.send_html(self.login_page())
            return
        if parsed.path == "/logout":
            self.send_response(303)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", f"{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if not self.require_auth():
            return
        if parsed.path == "/api/status":
            state = control.load_state()
            self.send_json({
                "version": control.__version__,
                "panelVersion": PANEL_VERSION,
                "mode": state.get("mode", "exercise"),
                "stations": len(state.get("participants", {}) or {}),
                "sitreps": int(state.get("sitreps", 0)),
                "traffic": int(state.get("traffic_count", 0)),
                "events": int(state.get("events", 0)),
            })
            return
        if parsed.path == "/export/roster.csv":
            state = control.load_state()
            rows = [
                {
                    "callsign": call, "location": info.get("location", ""),
                    "power": info.get("power", ""), "role": info.get("role", ""),
                    "node": info.get("node", ""), "time": info.get("time", ""),
                }
                for call, info in sorted((state.get("participants", {}) or {}).items())
            ]
            self.send_csv("emcomm_roster.csv", build_csv(rows, ["callsign", "location", "power", "role", "node", "time"]))
            return
        if parsed.path == "/export/traffic.csv":
            self.send_csv("emcomm_traffic_log.csv", build_csv(control.read_log_records(), control.TRAFFIC_LOG_FIELDS))
            return
        if parsed.path == "/export/formal_traffic.csv":
            self.send_csv("emcomm_formal_traffic.csv", build_csv(control.formal_traffic_rows(), control.FORMAL_TRAFFIC_FIELDS))
            return
        if parsed.path != "/":
            self.send_html(self.layout("Not found", '<section class="card"><h1>Not found</h1><a href="/">Dashboard</a></section>'), status=404)
            return
        params = parse_qs(parsed.query)
        message = params.get("msg", [""])[0]
        page, nonce = self.dashboard(message)
        self.send_html(page, nonce=nonce)

    def do_POST(self):
        parsed = urlsplit(self.path)
        if parsed.path == "/login":
            try:
                supplied = self.form().get("token", [""])[0]
            except Exception:
                self.send_html(self.login_page("Invalid request."), status=400)
                return
            if self.server.panel_token and hmac.compare_digest(supplied, self.server.panel_token):
                self.send_response(303)
                self.send_header("Location", "/")
                self.send_header("Set-Cookie", f"{COOKIE_NAME}={self.server.auth_digest}; Path=/; HttpOnly; SameSite=Strict")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            else:
                self.send_html(self.login_page("Invalid access token."), status=403)
            return

        if not self.require_auth():
            return
        try:
            fields = self.form()
        except Exception:
            self.send_html(self.layout("Error", '<section class="card"><h1>Invalid request</h1></section>'), status=400)
            return

        if parsed.path == "/confirm/live":
            self.send_html(self.confirmation("live"))
            return
        if parsed.path == "/confirm/exercise":
            self.send_html(self.confirmation("exercise"))
            return
        if parsed.path == "/confirm/reset":
            self.send_html(self.confirmation("reset"))
            return
        if parsed.path == "/action/mode":
            mode = fields.get("mode", [""])[0]
            confirmed = fields.get("confirmed", [""])[0]
            if confirmed != "yes" or mode not in {"live", "exercise"}:
                self.send_html(self.layout("Refused", '<section class="card"><h1>Mode change refused</h1><p>Confirmation is required.</p><a href="/">Return</a></section>'), status=400)
                return
            try:
                msg = panel_change_mode(mode)
                self.redirect("/?msg=" + quote(msg))
            except Exception as exc:
                self.send_html(self.layout("Error", f'<section class="card"><h1>Mode change failed</h1><p>{esc(exc)}</p><a href="/">Return</a></section>'), status=500)
            return
        if parsed.path == "/action/reset":
            if fields.get("confirmed", [""])[0] != "yes":
                self.send_html(self.layout("Refused", '<section class="card"><h1>Reset refused</h1><p>Confirmation is required.</p></section>'), status=400)
                return
            try:
                msg = panel_reset()
                self.redirect("/?msg=" + quote(msg))
            except Exception as exc:
                self.send_html(self.layout("Error", f'<section class="card"><h1>Reset failed</h1><p>{esc(exc)}</p><a href="/">Return</a></section>'), status=500)
            return
        if parsed.path == "/traffic/compose":
            form = {k: v[0] for k, v in fields.items() if v}
            mode = control.load_state().get("mode", "exercise")
            page, nonce = self.dashboard(form=form, result=compose_from_form(form, mode))
            self.send_html(page, nonce=nonce)
            return
        if parsed.path == "/action/checkout":
            callsign = fields.get("callsign", [""])[0]
            try:
                msg = panel_checkout(callsign)
                self.redirect("/?msg=" + quote(msg))
            except Exception as exc:
                self.send_html(self.layout("Error", f'<section class="card"><h1>Checkout failed</h1><p>{esc(exc)}</p><a href="/">Return</a></section>'), status=500)
            return
        self.send_html(self.layout("Not found", '<section class="card"><h1>Not found</h1></section>'), status=404)


def main():
    parser = argparse.ArgumentParser(description="EmComm Control browser operator panel")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="TCP port (default: 8787)")
    parser.add_argument("--token", default=DEFAULT_TOKEN, help="Panel access token; or set MM_EMCOMM_PANEL_TOKEN")
    parser.add_argument("--open", action="store_true", help="Open the local panel in the default browser")
    args = parser.parse_args()

    if args.port < 1 or args.port > 65535:
        raise SystemExit("Port must be between 1 and 65535.")
    if not is_loopback(args.host) and not args.token:
        raise SystemExit(
            "Refusing non-loopback panel without authentication. Set --token or MM_EMCOMM_PANEL_TOKEN."
        )

    server = PanelServer((args.host, args.port), Handler, token=args.token)
    display_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    url = f"http://{display_host}:{args.port}/"
    print(f"EmComm Control Panel v{PANEL_VERSION}")
    print(f"Listening on {args.host}:{args.port}")
    print(f"Open: {url}")
    print("Authentication: enabled" if args.token else "Authentication: localhost-only")
    if args.open and is_loopback(args.host):
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
