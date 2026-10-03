/* eslint-disable no-unused-vars */
/*
  meshmonitor-emcomm-control — GitHub Pages (docs/index.js)
  Single-file documentation UI in the same zero-dependency style as the companion MeshMonitor project.
*/

(() => {
  const REPO = "maxhayim/meshmonitor-emcomm-control";
  const SCRIPT = "mm_emcomm_control.py";

  const el = (tag, attrs = {}, children = []) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") node.className = v;
      else if (k === "html") node.innerHTML = v;
      else node.setAttribute(k, v);
    }
    for (const child of Array.isArray(children) ? children : [children]) {
      if (child === null || child === undefined) continue;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return node;
  };

  const style = el("style", {
    html: `
      :root{
        --bg:#0b0f17; --card:#121a28; --card2:#0f1624;
        --text:#e8eefc; --muted:#b7c3df; --border:#24314a;
        --accent:#5aa2ff; --good:#4ade80; --warn:#fbbf24;
        --mono:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,"Liberation Mono",monospace;
        --sans:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;
      }
      *{box-sizing:border-box}
      body{margin:0;background:linear-gradient(180deg,#070a11 0%,var(--bg) 100%);color:var(--text);font-family:var(--sans)}
      a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
      .wrap{max-width:1040px;margin:0 auto;padding:30px 18px 64px}
      .hero{margin-bottom:20px}.hero h1{font-size:2.35rem;margin:0 0 8px}.hero p{color:var(--muted);font-size:1.05rem;max-width:820px}
      .badges{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}.pill{border:1px solid var(--border);background:var(--card2);padding:6px 10px;border-radius:999px;color:var(--muted);font-size:.9rem}
      .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
      .card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:19px;margin:14px 0}.card h2,.card h3{margin-top:0}
      pre{white-space:pre-wrap;background:#080c13;border:1px solid var(--border);padding:14px;border-radius:10px;overflow:auto;font-family:var(--mono)}
      code{font-family:var(--mono)}
      .live{border-left:4px solid var(--good)} .exercise{border-left:4px solid var(--warn)}
      .muted{color:var(--muted)}
      ul{line-height:1.65}
    `,
  });
  document.head.appendChild(style);

  const app = document.getElementById("app");
  const wrap = el("main", { class: "wrap" });

  wrap.appendChild(el("section", { class: "hero", html: `
    <h1>🚨 EmComm Control</h1>
    <p>Emergency communications control for MeshMonitor with deliberately separated LIVE and EXERCISE modes over Meshtastic and MeshCore, suitable for city, county/regional, and state Emergency Operations Center (EOC) workflows.</p>
    <div class="badges">
      <span class="pill">Python 3.9+</span>
      <span class="pill">MIT License</span>
      <span class="pill">Meshtastic</span>
      <span class="pill">MeshCore</span>
      <span class="pill">LIVE + EXERCISE</span>
      <span class="pill">ICS-213 / NTS-style traffic</span>
    </div>
    <p><a href="https://github.com/${REPO}">GitHub repository</a> · <a href="https://github.com/${REPO}/blob/main/${SCRIPT}">View runtime script</a></p>
  ` }));

  wrap.appendChild(el("section", { class: "card", html: `
    <h2>Emergency Operations Center (EOC) use</h2>
    <p>EmComm Control can support communications-control and logging workflows in government EOCs and supporting communications rooms.</p>
    <ul>
      <li><strong>City / municipal EOCs</strong> — local field teams, facilities, SITREPs and message logging</li>
      <li><strong>County / regional EOCs</strong> — cross-jurisdiction coordination, shelters and regional resources</li>
      <li><strong>State EOCs</strong> — statewide communications coordination and regional status collection</li>
    </ul>
    <p class="muted">It complements, rather than replaces, an agency's incident-management, dispatch, records, and approved emergency communications systems.</p>
  ` }));

  wrap.appendChild(el("section", { class: "card", html: `
    <h2>Operator Control Panel</h2>
    <p>Operators can use a local browser UI instead of terminal commands to switch between LIVE and EXERCISE modes.</p>
    <ul>
      <li>Confirmed <strong>Activate LIVE</strong> button</li>
      <li><strong>Switch to EXERCISE</strong> and <strong>Refresh Status</strong></li>
      <li>Check-in, SITREP, traffic and event counters</li>
      <li>Station, formal traffic, and recent-log tables</li>
      <li>Structured ICS-213 formal traffic composer with character counter</li>
      <li>Delivery status, per-station activity, and optional silent capture of mesh traffic</li>
      <li>Optional Net Control automation: scheduled exercise announcements and automatic check-in ACKs</li>
      <li>LAN binding requires an access token</li>
    </ul>
    <pre>python3 /data/scripts/mm_emcomm_panel.py --open</pre>
  ` }));

  const modes = el("div", { class: "grid" });
  modes.appendChild(el("section", { class: "card live", html: `
    <h2>LIVE mode</h2>
    <p>For real-world operator-entered emergency communications.</p>
    <ul>
      <li>Check-ins, SITREPs and traffic logging</li>
      <li>Operator-supplied announcements</li>
      <li>No simulated injects</li>
      <li>Cannot be enabled by inbound mesh traffic</li>
    </ul>
    <pre>/data/scripts/${SCRIPT} --mode live --confirm-live</pre>
  ` }));
  modes.appendChild(el("section", { class: "card exercise", html: `
    <h2>EXERCISE mode</h2>
    <p>For drills, SET activities and simulated incidents.</p>
    <ul>
      <li>Explicit TEST / EXERCISE / SIMULATED labeling</li>
      <li>Eight timed exercise injects</li>
      <li>Legacy SET command compatibility</li>
      <li>After-action logging</li>
    </ul>
    <pre>/data/scripts/${SCRIPT} --mode exercise</pre>
  ` }));
  wrap.appendChild(modes);

  wrap.appendChild(el("section", { class: "card", html: `
    <h2>Install</h2>
    <pre>/data/scripts/${SCRIPT}\nchmod +x /data/scripts/${SCRIPT}</pre>
    <p>Create MeshMonitor Auto Responder rules for:</p>
    <pre>^EMCOMM\\b\n^SET\\b   # exercise compatibility</pre>
  ` }));

  wrap.appendChild(el("section", { class: "card", html: `
    <h2>Mesh commands</h2>
    <h3>Tactical</h3>
    <pre>EMCOMM CHECKIN &lt;CALLSIGN&gt; &lt;LOCATION&gt; &lt;POWER&gt; &lt;ROLE&gt;\nEMCOMM CHECKOUT &lt;CALLSIGN&gt;\nEMCOMM SITREP &lt;LOCATION&gt; &lt;STATUS&gt;\nEMCOMM STATUS\nEMCOMM HELP</pre>
    <h3>Formal (ICS-213 / NTS-style)</h3>
    <pre>EMCOMM TRAFFIC P 2:EOC 3:FIELD1 4:STATUS 7:TEST MESSAGE COMMS OPERATIONAL\nEMCOMM TRAFFIC R RE:EX-001 2:FIELD1 3:EOC 4:STATUS 7:TEST MESSAGE RECEIVED\nEMCOMM RELAY EX-001\nEMCOMM RCVD EX-001     # addressee confirms delivery\nEMCOMM TRACK EX-001    # logged / relayed / delivered</pre>
    <p class="muted">Fields: 1 Incident · 2 To · 3 From · 4 Subject · 5 Date · 6 Time · 7 Message · 8 Approved By. Precedence R / P / W / EMERGENCY. In EXERCISE mode Field 7 must begin TEST MESSAGE (or EXERCISE in the optional SET-safe style for networks with TEST-triggered bots). A system ACK confirms logging, not delivery. Default message limit 133 characters (120 recommended).</p>
    <p class="muted">This is an ICS-213 / NTS-style workflow for training and communications support. It is not an official FEMA ICS-213, ARRL NTS, Winlink, ARES, RACES, or government message-management system. See <a href="https://github.com/${REPO}/blob/main/docs/formal-traffic.md">docs/formal-traffic.md</a>.</p>
  ` }));

  wrap.appendChild(el("section", { class: "card", html: `
    <h2>Exercise injects</h2>
    <p>Available only while EXERCISE mode is active.</p>
    <pre>/data/scripts/${SCRIPT} --inject 1\n...\n/data/scripts/${SCRIPT} --inject 8</pre>
  ` }));

  wrap.appendChild(el("section", { class: "card", html: `
    <h2>Operational note</h2>
    <p>LIVE mode logs operator-supplied information; it does not invent or infer incident conditions. Operators remain responsible for applicable laws, radio-service rules, served-agency procedures, and information security.</p>
    <p class="muted">ARRL® is a trademark of the American Radio Relay League, Incorporated. This independent project is not affiliated with or endorsed by ARRL.</p>
  ` }));

  app.appendChild(wrap);
})();
