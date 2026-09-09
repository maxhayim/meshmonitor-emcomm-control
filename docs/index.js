document.getElementById("app").innerHTML = `
<h1>🚨 ARRL SET Exercise Control</h1>
<p>Unofficial MeshMonitor exercise-control script for the ARRL Simulated Emergency Test (SET).</p>
<p><a href="https://github.com/maxhayim/meshmonitor-setexercisecontrol/blob/main/mm_arrl_set.py">View mm_arrl_set.py</a></p>
<pre>SET CHECKIN &lt;CALLSIGN&gt; &lt;LOCATION&gt; &lt;POWER&gt; &lt;ROLE&gt;
SET SITREP &lt;LOCATION&gt; &lt;STATUS&gt;
SET TRAFFIC &lt;TO&gt; &lt;TEXT&gt;
SET STATUS
SET HELP</pre>`;
