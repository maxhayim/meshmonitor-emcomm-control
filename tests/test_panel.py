import http.client
import socket
import threading

import mm_emcomm_control as control
import mm_emcomm_panel as panel
from conftest import send


def test_panel_change_mode_reports_no_op_on_repeat():
    first = panel.panel_change_mode("live")
    assert "LIVE" in first
    assert control.load_state()["mode"] == "live"
    second = panel.panel_change_mode("live")
    assert "Already" in second


def test_panel_reset_preserves_mode():
    panel.panel_change_mode("live")
    msg = panel.panel_reset()
    assert "LIVE" in msg
    assert control.load_state()["mode"] == "live"
    assert control.load_state()["participants"] == {}


def test_panel_checkout_removes_station(monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM CHECKIN W4ABC MIAMI-EOC BATTERY NCS")
    msg = panel.panel_checkout("w4abc")
    assert "Removed" in msg
    assert "W4ABC" not in control.load_state()["participants"]


def test_panel_checkout_unknown_station():
    msg = panel.panel_checkout("GHOST")
    assert "not found" in msg.lower()


def test_build_csv_roundtrip():
    rows = [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
    data = panel.build_csv(rows, ["a", "b"])
    lines = data.strip().splitlines()
    assert lines[0] == "a,b"
    assert lines[1] == "1,2"
    assert lines[2] == "3,4"


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _run_server(token=""):
    port = _free_port()
    server = panel.PanelServer(("127.0.0.1", port), panel.Handler, token=token)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, port


def test_logout_clears_session_cookie():
    server, thread, port = _run_server(token="secret-token")
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(
            "POST", "/login",
            body="token=secret-token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp = conn.getresponse()
        resp.read()
        assert resp.status == 303
        login_cookie = resp.getheader("Set-Cookie")
        assert login_cookie and "emcomm_panel_auth=" in login_cookie

        conn.request("GET", "/logout", headers={"Cookie": login_cookie.split(";")[0]})
        resp = conn.getresponse()
        resp.read()
        logout_cookie = resp.getheader("Set-Cookie")
        assert logout_cookie is not None
        assert "emcomm_panel_auth=;" in logout_cookie
        assert "Max-Age=0" in logout_cookie
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_requires_auth_when_token_set():
    server, thread, port = _run_server(token="secret-token")
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "access token" in body.lower()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
