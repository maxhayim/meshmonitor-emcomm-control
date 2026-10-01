import json
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


FORM = {
    "precedence": "P", "to": "EOC", "from": "FIELD1", "subject": "STATUS",
    "message": "TEST MESSAGE COMMS OPERATIONAL",
}


def test_compose_from_form_exercise():
    result = panel.compose_from_form(dict(FORM), "exercise")
    assert result["errors"] == []
    assert [c["text"] for c in result["commands"]] == [
        "EMCOMM TRAFFIC TEST P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL"
    ]
    report = result["commands"][0]["report"]
    assert report["limit"] == control.MAX_LEN
    assert report["length"] == len(result["commands"][0]["text"])


def test_compose_from_form_requires_test_message_in_exercise():
    form = dict(FORM, message="COMMS OPERATIONAL")
    result = panel.compose_from_form(form, "exercise")
    assert any("TEST MESSAGE" in e for e in result["errors"])
    assert result["commands"] == []


def test_compose_from_form_live_has_no_test():
    form = dict(FORM, message="COMMS OPERATIONAL", reply_to="ec-004")
    result = panel.compose_from_form(form, "live")
    assert result["errors"] == []
    text = result["commands"][0]["text"]
    assert text == "EMCOMM TRAFFIC P RE:EC-004 2:EOC 3:FIELD1 4:STATUS 7:COMMS OPERATIONAL"
    assert "TEST" not in text


def test_compose_from_form_multipart_and_warning():
    form = dict(FORM, message="TEST MESSAGE " + "SUPPLIES NEEDED " * 12)
    result = panel.compose_from_form(form, "exercise")
    assert len(result["commands"]) > 1
    assert all(not c["report"]["over_limit"] for c in result["commands"])
    form = dict(FORM, message="TEST MESSAGE " + "X" * 65)
    result = panel.compose_from_form(form, "exercise")
    rep = result["commands"][0]["report"]
    assert rep["over_recommended"] and rep["warning"] == "Recommended LoRa target exceeded."


def test_dashboard_shows_exercise_banner_and_composer():
    server, thread, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        csp = resp.getheader("Content-Security-Policy")
        assert "EXERCISE / TEST MODE" in body
        assert "must begin TEST MESSAGE" in body
        assert 'action="/traffic/compose"' in body
        assert "script-src 'nonce-" in csp
        nonce = csp.split("'nonce-")[1].split("'")[0]
        assert f'<script nonce="{nonce}">' in body

        conn.request(
            "POST", "/traffic/compose",
            body="precedence=P&to=EOC&from=FIELD1&subject=STATUS&message=TEST+MESSAGE+COMMS+OPERATIONAL",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "EMCOMM TRAFFIC TEST P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL" in body
        assert f"/ {control.MAX_LEN}" in body
        assert control.load_state()["traffic_count"] == 0  # composing never logs traffic
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_formal_traffic_csv_download(monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL")
    server, thread, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/export/formal_traffic.csv")
        resp = conn.getresponse()
        data = resp.read().decode("utf-8")
        assert resp.status == 200
        assert data.splitlines()[0].startswith("traffic_id,mode,precedence,test_traffic,field_1_incident")
        assert "EX-001" in data
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_dashboard_shows_tracking_sections(monkeypatch, capsys):
    send(monkeypatch, capsys, "EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL", from_id="!f1")
    send(monkeypatch, capsys, "EMCOMM RCVD EX-001", from_id="!eoc")
    server, thread, port = _run_server()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        body = conn.getresponse().read().decode("utf-8")
        assert "Station activity" in body
        assert "Captured mesh messages" in body
        assert "Delivered" in body and "by !eoc" in body
        for path in ("/export/stations.csv", "/export/captured_messages.csv"):
            conn.request("GET", path)
            resp = conn.getresponse()
            data = resp.read().decode("utf-8")
            assert resp.status == 200
            assert data.splitlines()[0].split(",")[0] in {"station", "time"}
        conn.request("GET", "/api/status")
        status = json.loads(conn.getresponse().read())
        assert status["deliveries"] == 1 and "captured" in status
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
