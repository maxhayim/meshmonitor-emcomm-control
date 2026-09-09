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
import hashlib
import hmac
import html
import json
import os
import sys
import webbrowser
from collections import deque
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

import mm_emcomm_control as control

PANEL_VERSION = "2.1.0"
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


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, handler, token=""):
        super().__init__(address, handler)
        self.panel_token = token
        self.auth_digest = hashlib.sha256(token.encode("utf-8")).hexdigest() if token else ""


class Handler(BaseHTTPRequestHandler):
    server_version = "EmCommPanel/2.1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[panel] %s - %s\n" % (self.address_string(), fmt % args))

    def common_headers(self, content_type="text/html; charset=utf-8"):
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )

    def send_html(self, body, status=200, extra_headers=None):
        data = body.encode("utf-8")
        self.send_response(status)
        self.common_headers()
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

    def layout(self, title, body):
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
        input{{width:100%;margin:8px 0 14px;padding:12px;border-radius:9px;border:1px solid var(--border);background:#0a101b;color:var(--text)}} label{{font-weight:650}}
        table{{width:100%;border-collapse:collapse;font-size:.93rem}} th,td{{text-align:left;border-bottom:1px solid var(--border);padding:9px 7px;vertical-align:top}} th{{color:var(--muted)}} .scroll{{overflow:auto}}
        .notice{{padding:12px 14px;border-radius:10px;margin:12px 0;background:#13223b;border:1px solid #27486f}} .notice.bad{{background:#3f1015;border-color:#7f1d1d}} .notice.good{{background:#0c2f20;border-color:#166534}}
        code{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}} footer{{color:var(--muted);margin-top:24px;font-size:.9rem}}
        </style></head><body><div class="wrap">{body}<footer>EmComm Control Panel v{PANEL_VERSION} · Local operator interface</footer></div></body></html>"""

    def dashboard(self, message=""):
        state = control.load_state()
        mode = state.get("mode", "exercise")
        mode_class = "live" if mode == "live" else "exercise"
        participants = state.get("participants", {}) or {}
        events = read_recent_events(40)
        notice = f'<div class="notice good">{esc(message)}</div>' if message else ""

        station_rows = "".join(
            f"<tr><td><strong>{esc(call)}</strong></td><td>{esc(info.get('location'))}</td><td>{esc(info.get('power'))}</td><td>{esc(info.get('role'))}</td><td>{esc(info.get('time'))}</td></tr>"
            for call, info in sorted(participants.items())
        ) or '<tr><td colspan="5" class="muted">No stations checked in.</td></tr>'

        event_rows = "".join(
            f"<tr><td>{esc(item.get('time'))}</td><td>{esc(item.get('mode'))}</td><td>{esc(item.get('kind'))}</td><td>{esc(item.get('from_node'))}</td><td>{esc(item.get('message'))}</td></tr>"
            for item in events
        ) or '<tr><td colspan="5" class="muted">No events logged yet.</td></tr>'

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

        body = f"""
        <header><div><h1>🚨 EmComm Control Panel</h1><div class="muted">Operator controls for LIVE and EXERCISE operations</div></div><div><span class="pill {mode_class}">{mode_name(mode)}</span></div></header>
        {notice}
        <section class="card"><h2>Mode control</h2><div class="actions">{live_action}{exercise_action}<a class="button primary" href="/">Refresh Status</a><form method="post" action="/confirm/reset"><button type="submit">Reset Operation</button></form></div><p class="muted">LIVE changes are deliberate and require a second confirmation screen. Simulated injects remain blocked while LIVE.</p></section>
        <section class="grid">
          <div class="card"><div class="muted">Checked-in stations</div><div class="metric">{len(participants)}</div></div>
          <div class="card"><div class="muted">SITREPs</div><div class="metric">{int(state.get('sitreps',0))}</div></div>
          <div class="card"><div class="muted">Traffic records</div><div class="metric">{int(state.get('traffic_count',0))}</div></div>
          <div class="card"><div class="muted">Logged events</div><div class="metric">{int(state.get('events',0))}</div></div>
        </section>
        <section class="card"><h2>Check-ins</h2><div class="scroll"><table><thead><tr><th>Callsign</th><th>Location</th><th>Power</th><th>Role</th><th>Last check-in</th></tr></thead><tbody>{station_rows}</tbody></table></div></section>
        <section class="card"><h2>Recent operational log</h2><div class="scroll"><table><thead><tr><th>Time</th><th>Mode</th><th>Type</th><th>Source</th><th>Details</th></tr></thead><tbody>{event_rows}</tbody></table></div></section>
        <section class="card"><h2>Operational note</h2><p>This panel changes EmComm Control state and displays its local logs. It does not replace an EOC incident-management, dispatch, CAD, records, or approved emergency communications system.</p><p class="muted">For LAN access, run with an access token and place the panel only on a trusted management network or behind an authenticated TLS reverse proxy.</p></section>
        """
        return self.layout("Dashboard", body)

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
        if parsed.path == "/logout":
            self.redirect("/login")
            return
        if parsed.path != "/":
            self.send_html(self.layout("Not found", '<section class="card"><h1>Not found</h1><a href="/">Dashboard</a></section>'), status=404)
            return
        params = parse_qs(parsed.query)
        message = params.get("msg", [""])[0]
        self.send_html(self.dashboard(message))

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
