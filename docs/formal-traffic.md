# Formal traffic: ICS-213 / NTS-style message handling

EmComm Control v2.3.0 handles **formal traffic** with a **compressed ICS-213-compatible field structure and NTS-style traffic handling**. It is built for LoRa mesh networks (Meshtastic and MeshCore), where each text message is short. The goal is to keep the important formal-message fields and handling practices intact inside that limit.

> **Disclaimer.** This software provides an ICS-213 / NTS-style workflow for training and communications support. It is not an official FEMA ICS-213, ARRL NTS, Winlink, ARES, RACES, or government message-management system. No certification by, or endorsement from, FEMA, ARRL, or any agency is claimed or implied.

It is **not** a replacement for:

- the official ICS-213 General Message form
- Winlink forms
- official NTS radiogram software or NTS procedures
- agency-specific message-management systems

---

## Two kinds of traffic

| Class | Commands | Format |
|---|---|---|
| **Tactical** | `CHECKIN`, `CHECKOUT`, `SITREP`, `STATUS`, `HELP` | Lightweight, unchanged from v2.2 |
| **Formal** | `TRAFFIC` (and `RELAY`) | Compressed ICS-213 fields with NTS-style precedence |

Tactical traffic is never forced into ICS-213 format.

---

## What the standards terms mean here

**ICS-213** is the FEMA / NIMS *General Message* form, with these numbered blocks:

| Field | ICS-213 block | EmComm Control | Log column |
|---|---|---|---|
| 1 | Incident Name (optional) | optional | `field_1_incident` |
| 2 | To (name and position) | **required** | `field_2_to` |
| 3 | From (name and position) | **required** | `field_3_from` |
| 4 | Subject | **required** | `field_4_subject` |
| 5 | Date | optional | `field_5_date` |
| 6 | Time | optional | `field_6_time` |
| 7 | Message | **required** | `field_7_message` |
| 8 | Approved by | optional | `field_8_approved_by` |

The paper form's signature lines, position titles and reply section are not reproduced. Replies are separate messages that reference the original (see [Replies](#replies)).

**NTS-style handling** means borrowing these principles from the ARRL National Traffic System:

- traffic **precedence** (EMERGENCY, PRIORITY, WELFARE, ROUTINE)
- **TEST** marking of exercise traffic
- numbering and reference concepts
- accurate relay
- acknowledgment
- preserving message content without alteration

EmComm Control does **not** produce an ARRL radiogram preamble: no NTS message number, station of origin, check, place of origin, or filing time/date. It is not an NTS-compliant radiogram.

---

## Command syntax

```text
EMCOMM TRAFFIC <PRECEDENCE> [RE:<ID>] 2:<TO> 3:<FROM> 4:<SUBJECT> 7:<MESSAGE>
```

With optional fields:

```text
EMCOMM TRAFFIC P 1:SET 2:EOC 3:SHELTER1 4:WATER 5:10/03/26 6:0930 7:TEST MESSAGE REQUEST 20 CASES WATER 8:OPERATOR1
```

Parsing rules:

- Fields are `N:value` tokens and may appear in any order **before** Field 7.
- **Field 7 runs to the end of the message**, so message text may contain things like `RATIO 1:2` or `2:30`.
- The only exception is a trailing `8:` (Approved By), which must be the last field. An `8:` followed by a digit, such as `8:00`, stays in the message text.
- The operator's text is stored exactly as sent, apart from whitespace normalization. Case is not changed.
- A field may appear only once per message part.
- `|` separators, as used in the canonical relay format, are accepted and ignored.

---

## Precedence

| Input | Stored | Meaning (ARRL NTS) |
|---|---|---|
| `R` / `ROUTINE` | `R` | Routine; most traffic in normal times |
| `W` / `WELFARE` | `W` | Health-and-welfare inquiries or advisories |
| `P` / `PRIORITY` | `P` | Important, time-limited or official traffic not at EMERGENCY level |
| `EMERGENCY` | `EMERGENCY` | Life-and-death urgency. Always spelled out; `E` is not accepted. |

No other precedence terms are accepted in the structured format.

### Legacy `IMMEDIATE` compatibility mapping

The v2.2 syntax accepted `ROUTINE | PRIORITY | IMMEDIATE`. **`IMMEDIATE` is not an NTS precedence.** For backward compatibility:

- Legacy `IMMEDIATE` is logged as **`P` (PRIORITY)**. It is never mapped to `EMERGENCY`, because EMERGENCY has a specific life-and-death meaning that operators must choose deliberately.
- The original word is kept in the `legacy_precedence` log column.
- The ACK says so explicitly: `... LEGACY IMMEDIATE LOGGED AS P.`

---

## Exercise (TEST) traffic

Following ARRL practice for test and exercise messages, the word **TEST** precedes the precedence in the default `standard` style (see [SET-safe style](#exercise-marking-styles-standard-and-set-safe) for shared networks with TEST-triggered bots): `TEST R`, `TEST P`, `TEST W`, `TEST EMERGENCY`.

In **EXERCISE** mode:

- All formal traffic is flagged `test_traffic = true` and rendered with `TEST` before the precedence.
- **Field 7 must begin `TEST MESSAGE`.** Traffic without it is rejected with a short corrective response, and no traffic ID is used up:

  ```text
  TEST TRAFFIC REJECTED: FIELD 7 MUST BEGIN TEST MESSAGE. USE: EMCOMM TRAFFIC P 2:TO 3:FROM 4:SUBJ 7:TEST MESSAGE TEXT
  ```

- Optional auto-prefix: set `MM_EMCOMM_TEST_PREFIX=auto` to prepend `TEST MESSAGE` instead of rejecting. The default, `validate`, is preferred because it makes operators practise correct message handling.
- Injects and system messages identify themselves with `TEST`, `EXERCISE` and/or `SIMULATED`.

In **LIVE** mode:

- `TEST` and `TEST MESSAGE` are **never** added automatically.
- Simulated incident conditions are never generated, and exercise injects are blocked.
- LIVE mode still requires a local `--mode live --confirm-live` (or the panel's confirmation screen).

### Exercise marking styles: standard and SET-safe

`exercise_style` in `mm_emcomm_config.json`, or `MM_EMCOMM_EXERCISE_STYLE`, selects how exercise traffic is marked:

| | `standard` (default) | `set-safe` |
|---|---|---|
| Precedence | `TEST R`, `TEST W`, `TEST P`, `TEST EMERGENCY` | `SET R`, `SET W`, `SET P`, `SET EMERGENCY` |
| Field 7 must begin | `TEST MESSAGE` | `EXERCISE` |
| System responses | `TEST ACK …`, `TEST RELAY …`, `TEST EXERCISE INJECT N …` | `EXERCISE ACK …`, `EXERCISE RELAY …`, `EXERCISE INJECT N …` |
| Relay line | `TEST R \| EX-007 \| 2:MIKE \| … \| 7:TEST MESSAGE …` | `SET R \| EX-007 \| 2:MIKE \| … \| 7:EXERCISE …` |

**Why SET-safe exists.** Some shared mesh networks have third-party bots that trigger on the literal word `TEST`. When those bots cannot be changed, operators may use the SET-safe marker (`SET` + `EXERCISE`) to prevent unintended automated responses while still clearly identifying simulated traffic.

This is an **operational adaptation for shared LoRa networks**. It is not a claim that `SET` replaces formal ARRL/NTS test-message terminology in general. Where bot interference is not a concern, use the standard style.

Behavior in SET-safe style:

- **Precedence stays operator-chosen:** R, W, P, or EMERGENCY (for simulated life-and-death traffic only). Exercise traffic is not assumed to be Priority.
- **No TEST on air:** in EXERCISE mode, no system output contains the word `TEST`. This covers ACKs, rejections, help, injects, relay output, multipart parts, `TRACK` and `RCVD` responses, and panel-generated commands.
- **Field 7 check:** must begin with the whole word `EXERCISE`. `MM_EMCOMM_TEST_PREFIX=auto` prefixes `EXERCISE` instead of rejecting.
- **Either marker accepted on input:** operators may type `SET` or `TEST` before the precedence; output always uses the active style.
- **Relay lines are ignored by the bot:** a line beginning `SET R |` also matches EmComm Control's own `^SET\b` rule, so EmComm Control ignores relayed canonical lines (`<PREC> | …` after the prefix) silently instead of answering with HELP.
- **History is preserved:** each record stores `exercise_marker` (`TEST` or `SET`), and changing styles later does not rewrite existing messages.
- **LIVE mode is unchanged** in either style and never adds `TEST`, `SET` or `EXERCISE`.

### Real-world traffic during an exercise

If actual emergency traffic occurs during an exercise, operators must **stop treating that message as exercise traffic** and clearly identify it as real-world traffic according to their local operating procedure. This might mean switching EmComm Control to LIVE mode, or passing the traffic on a separate, designated path. EmComm Control does not define an official phrase for this; use the one your served agency or exercise plan specifies.

---

## Traffic IDs are internal

`EX-001`, `EX-002`, … (EXERCISE) and `EC-001`, `EC-002`, … (LIVE) are **internal EmComm Control identifiers**:

- They are **not** NTS message numbers and do not meet NTS numbering requirements.
- They restart after `--reset`.
- If your net also assigns NTS numbers, include the NTS number in Field 7 or record it under your own procedure.

---

## Acknowledgments

```text
TEST ACK EX-003 TO EOC LOGGED. PREC TEST P. NOT A DELIVERY CONFIRMATION.
LIVE ACK EC-003 TO EOC LOGGED. PREC P. NOT A DELIVERY CONFIRMATION.
```

**An "ACK" from EmComm Control confirms only that the system received and logged the traffic. It does not confirm delivery to the intended recipient.** Receipt, logging, relay and final delivery are separate steps. EmComm Control records the first three automatically; delivery is recorded only when a station sends `EMCOMM RCVD <ID>` (see [Delivery receipts and tracking](tracking.md)). That receipt is operator-reported, not a network-level guarantee.

---

## Relay

```text
EMCOMM RELAY <TRAFFIC-ID> [VIA <ROUTE>]
```

A relay:

- logs a separate `relay` record (`TRACK` and the exports show the relay count) with `relayed_by`, `relay_time`, `relay_count` and `relay_route`
- **never rewrites** To, From, Subject, Message or any other original field
- returns the canonical, unaltered message text for the relaying station to pass on

Canonical relay format:

```text
TEST P | EX-003 | 2:EOC | 3:FIELD1 | 4:COMMS | 7:TEST MESSAGE SHELTER COMMS OPERATIONAL
```

---

## Replies

```text
EMCOMM TRAFFIC R RE:EX-007 2:SHELTER1 3:EOC 4:WATER 7:TEST MESSAGE REQUEST APPROVED
```

A reply is a **new formal message with its own traffic ID**; the `RE:` reference is stored in `reply_to`. The original message is never modified. If the referenced ID is not in the log, the reply is still accepted and the ACK adds `REF NOT IN LOG.`

---

## Message length and multipart traffic

- Default hard limit per emitted message: **133 characters** (`MM_EMCOMM_MAXLEN` overrides; minimum 60).
- Recommended operating target: **120 ASCII characters** (`MM_EMCOMM_RECOMMENDED_LEN` overrides).
- Non-ASCII characters can take several bytes on air; prefer plain ASCII.

133 is a conservative common default for Meshtastic and MeshCore text workflows. Actual limits vary by firmware, channel and path overhead, so the value stays configurable.

### Sending multipart traffic

When a command would exceed the limit, send it in numbered parts. Each part keeps its field labels, and a repeated label continues that field:

```text
EMCOMM TRAFFIC 1/2 P 2:EOC 3:SHELTER1 4:SUPPLIES 7:TEST MESSAGE NEED 40 COTS
EMCOMM TRAFFIC 2/2 7:AND 80 BLANKETS AT NORTH ENTRANCE 8:OPS1
```

- Parts are buffered **per sending node**, and the message is logged only when all parts have arrived.
- Part 1 must arrive first; a new `1/n` restarts the buffer.
- Incomplete parts expire after `MM_EMCOMM_PART_TIMEOUT` seconds (default 1800).
- At most 9 parts.

The operator panel's composer generates these parts automatically.

### Multipart relay output

Relay output that exceeds the limit is split the same way. Every part carries the same traffic ID and an explicit `k/n`:

```text
TEST P | EX-002 1/2 | 1:SET | 2:EOC | 3:SHELTER1 | 4:WATER | 5:10/03/26 | 6:0930 | 7:TEST MESSAGE REQUEST 20 CASES WATER AT 8:00
EX-002 2/2 | 8:OPERATOR1
```

Fields are split only at word boundaries, and the field label is repeated, so a receiving station or `reassemble_serialized()` can rebuild the complete message.

---

## Legacy syntax

Legacy traffic syntax remains supported for compatibility. Structured ICS-213 / NTS-style traffic is preferred.

```text
EMCOMM TRAFFIC <TO> [ROUTINE|PRIORITY|IMMEDIATE] <TEXT>
```

Legacy traffic is normalized as follows:

- Stored as Field 2 = `<TO>`, Field 7 = `<TEXT>`, `syntax = legacy`.
- It is not checked for required fields or `TEST MESSAGE`. In EXERCISE mode it is still flagged as TEST traffic.
- Pre-2.3 log records are upgraded **in memory** when read or exported. `traffic.jsonl` on disk is never rewritten.
- A legacy message whose `<TO>` is literally `R`, `P`, `W`, `TEST`, or a precedence word is read as structured traffic.

---

## Structured log record

Each formal message is one `kind: traffic` JSONL record containing:

- **Identity:** `traffic_id`, `mode`, `precedence`, `test_traffic`
- **ICS-213 fields:** `field_1_incident` … `field_8_approved_by`
- **Reference:** `reply_to`, `reply_found`
- **Receipt:** `from_node`, `received_time`, `raw_input`, `parts`
- **Format:** `syntax`, `legacy_precedence`
- **v2.2 compatibility columns:** `to`, `body`

`--export` writes `formal_traffic.csv` (one row per formal message, with relay counts) alongside `traffic_log.csv`, `roster.csv` and `summary.txt`. The operator panel offers the same CSVs as downloads.

---

## Example generic SET exchange

**Originator:**

```text
EMCOMM TRAFFIC P 2:EOC 3:SHELTER1 4:WATER 7:TEST MESSAGE REQUEST 20 CASES WATER
```

**System:**

```text
TEST ACK EX-007 TO EOC LOGGED. PREC TEST P. NOT A DELIVERY CONFIRMATION.
```

**Relay** (original fields preserved):

```text
EMCOMM RELAY EX-007 VIA HILLTOP-RPT
→ TEST RELAY EX-007 #1 LOGGED. FIELDS UNCHANGED. NOT A DELIVERY CONFIRMATION.
→ TEST P | EX-007 | 2:EOC | 3:SHELTER1 | 4:WATER | 7:TEST MESSAGE REQUEST 20 CASES WATER
```

**Reply:**

```text
EMCOMM TRAFFIC R RE:EX-007 2:SHELTER1 3:EOC 4:WATER 7:TEST MESSAGE REQUEST APPROVED
→ TEST ACK EX-008 RE:EX-007 TO SHELTER1 LOGGED. PREC TEST R. NOT A DELIVERY CONFIRMATION.
```

This exchange is an example only. For a worked example deployment, see [`examples/south-dade-set-2026.md`](examples/south-dade-set-2026.md).

---

## References

- FEMA, *ICS Form 213, General Message* (v3) — https://training.fema.gov/emiweb/is/icsresource/assets/ics%20forms/ics%20form%20213,%20general%20message%20(v3).pdf
- ARRL, *Public Service Communications Manual — Chapter Six: ARRL Precedences and Handling Instructions* — http://www.arrl.org/chapter-six-arrl-precedences-and-handling-instructions
- ARRL, *NTS Methods and Practices Guidelines* — https://www.arrl.org/files/file/Public%20Service/MPG104A.pdf

ARRL® is a trademark of the American Radio Relay League, Incorporated. EmComm Control is independent and not affiliated with, sponsored by, or endorsed by ARRL or FEMA.
