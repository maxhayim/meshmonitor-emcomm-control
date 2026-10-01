# Message tracking: delivery receipts, TRACK, capture, and station activity

EmComm Control v2.4.0 can follow formal traffic from origination to delivery. It can also silently log ordinary mesh traffic and summarize activity per station. All of this works the same way in **LIVE** and **EXERCISE** (SET) mode, and every record notes which mode it was logged in.

---

## Message lifecycle

| Step | How it is recorded | Shown as |
|---|---|---|
| Originated / logged | `EMCOMM TRAFFIC …` → system ACK | `logged` |
| Relayed | `EMCOMM RELAY <ID> [VIA <ROUTE>]` | `relayed` (with relay count) |
| Delivered | `EMCOMM RCVD <ID>` sent by the addressee's station | `delivered` (who, when, minutes from origination) |

The original message fields are never changed by any of these steps.

### Delivery receipts: `EMCOMM RCVD <ID>`

The **addressee** (or the operator who handed the message to the addressee) sends a receipt once the message has actually been delivered. `EMCOMM DELIVERED <ID>` works the same way.

```text
EMCOMM RCVD EX-007
→ TEST RCVD EX-007 DELIVERY CONFIRMED BY KN4EOC AT 11:10. LOGGED.
```

- The confirming station is labeled by its checked-in callsign when known, otherwise by node name or ID.
- `delivery_minutes` (time from origination to receipt) is recorded for after-action review.
- A second receipt is also logged, and the response names the first confirming station. The first receipt counts as the delivery.
- A receipt sent from the same node that originated the message is accepted but flagged (`self_confirmed`, `NOTE: SENT BY ORIGINATING NODE`).
- In LIVE mode the response begins `LIVE RCVD`; TEST is never added.

> **What "delivered" means.** A receipt is **operator-reported**: a station is stating that the addressee has the message. It is not a network-level delivery guarantee. The system ACK still confirms only that EmComm Control logged the traffic.

### Status queries: `EMCOMM TRACK <ID>`

Any station can ask where a message stands:

```text
EMCOMM TRACK EX-007
→ TEST TRACK EX-007 PREC TEST P TO NCS: LOGGED 11:05 | RELAYED 1X (LAST 11:07) | DELIVERED 11:10 BY KN4EOC (5.0 MIN)
```

If no receipt has arrived yet, the response ends `DELIVERY NOT YET CONFIRMED`. Long responses are split to fit the configured message limit.

Because traffic IDs restart after `--reset`, `TRACK`, `RELAY` and `RCVD` always refer to the **most recent** message with that ID. Older relays and receipts are never attached to a newer message.

---

## Receive metadata

MeshMonitor passes receive details to Auto Responder scripts. EmComm Control stores the following with every mesh-originated record (check-ins, SITREPs, traffic, relays, receipts and captured messages):

| Field | From MeshMonitor | Notes |
|---|---|---|
| `from_name` | `FROM_LONG_NAME` / `FROM_SHORT_NAME` | Node's advertised name |
| `snr`, `rssi` | `SNR`, `RSSI` | RSSI is Meshtastic only |
| `hops` | `HOPS` | Meshtastic only |
| `channel`, `is_direct` | `CHANNEL`, `IS_DIRECT` | |
| `via_mqtt`, `packet_id` | `VIA_MQTT`, `PACKET_ID` | Meshtastic only |
| `network` | `meshtastic` or `meshcore` | Detected from `MESHCORE_SOURCE_ID` |

**MeshCore channel messages** carry a synthetic channel ID instead of the sender's key. On MeshCore channels, EmComm Control therefore identifies the sender by the advertised name. This also keeps multipart traffic from different senders separate.

---

## Silent capture of ordinary mesh traffic (optional)

By default EmComm Control only sees messages beginning with `EMCOMM` or `SET`. To also log **ordinary channel chat** during a SET or activation, add a catch-all Auto Responder rule that runs the same script with `--capture`.

Capture mode **never transmits**. MeshMonitor sends nothing when a script prints no response.

### MeshMonitor rule

| Setting | Value |
|---|---|
| Trigger regex | `.*` (or a narrower pattern) |
| Action | Script |
| Script | `/data/scripts/mm_emcomm_control.py` |
| Script arguments | `--capture` |
| Channel | The channel(s) your exercise or activation uses |

### Rule ordering

The two networks handle overlapping rules differently, and EmComm Control handles both:

- **Meshtastic** runs only the **first** matching rule. Put the capture rule **after** the `^EMCOMM\b` and `^SET\b` rules. If it is accidentally placed first, an `EMCOMM` command reaching it is still processed normally rather than lost.
- **MeshCore** runs **every** matching rule. The capture rule ignores `EMCOMM` / `SET` commands there, because the main rule already handles them, so nothing is logged twice.

### What capture records

Each captured message is logged as `kind: capture` with the text, sender, mode and the receive metadata above. It appears in:

- the panel's **Captured mesh messages** table
- `captured_messages.csv`
- the per-station summary

On MeshCore, the node's own channel posts may come back to it. Captured messages that look like EmComm Control's own output (`TEST ACK …`, injects, relay text) are kept but flagged `possible_echo`, and they are left out of station activity counts.

### Limits

- Capture only sees what MeshMonitor passes to the rule. If MeshMonitor's airtime cutoff is pausing automations because the mesh is congested, those messages are not captured. **MeshMonitor's own message history remains the authoritative record of channel traffic.**
- Capture logs everything matching the rule. Real-world traffic can contain personal information, so follow your organization's records and privacy policies. Remove or disable the rule when you are not collecting.

---

## Per-station activity summary

`--export` (and the panel) produce a per-station summary in `stations.csv` and a **Station activity** table. Each station row includes:

| Column | Meaning |
|---|---|
| `station` | Checked-in callsign, else node name, else node ID |
| `nodes`, `names`, `networks` | Node IDs, names and networks the station was heard on |
| `checkins`, `checkouts`, `sitreps` | Tactical activity |
| `traffic_sent`, `relays`, `deliveries_confirmed` | Formal traffic handled |
| `captured_messages` | Ordinary messages captured |
| `messages_total`, `first_heard`, `last_heard` | Totals and time span |
| `avg_snr`, `best_snr`, `min_hops`, `max_hops` | Coverage indicators from receive metadata |

`summary.txt` adds three things:

- formal traffic delivery totals (`N of M confirmed delivered`, median and longest minutes to delivery, number relayed)
- the number of captured messages
- the ten most active stations

---

## Export files

| File | Contents |
|---|---|
| `roster.csv` | Current check-in roster |
| `traffic_log.csv` | Every logged event with all fields |
| `formal_traffic.csv` | One row per formal message: ICS-213 fields, `status`, `relay_count`, `delivered_by`, `delivered_time`, `delivery_minutes`, `receipt_count`, receive metadata |
| `stations.csv` | Per-station activity summary |
| `captured_messages.csv` | Silently captured mesh messages |
| `summary.txt` | Totals, delivery statistics, most active stations |
