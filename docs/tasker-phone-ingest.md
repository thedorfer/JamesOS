# Tasker Phone Ingest Setup

This sends daily phone activity into JamesOS as separate streams:

- Call log
- SMS/RCS
- Facebook Messenger notifications
- LINE notifications

JamesOS endpoint:

```text
POST http://100.77.201.40:8787/phone-ingest
Header: X-JamesOS-Key: <your API key>
Content-Type: application/json
```

## Privacy defaults

Only send data from your own phone. Start with call log and SMS first. For Messenger and LINE, this guide captures new notification text only; it does not read full app history.

## Required Android apps

Install:

- Tasker
- AutoNotification plugin, for Messenger/LINE notification capture

Recommended:

- Give Tasker notification access
- Exclude Tasker from battery optimization
- Keep NordVPN Meshnet connected when away from home

## Payload format

JamesOS accepts one item:

```json
{
  "type": "sms",
  "device": "pixel",
  "timestamp": "2026-07-02T20:00:00-05:00",
  "person": "Name or number",
  "number": "+15551234567",
  "direction": "inbound",
  "app": "Messages",
  "text": "message text"
}
```

Or a batch:

```json
{
  "events": [
    {"type": "call", "person": "Name", "number": "+1555", "direction": "incoming"},
    {"type": "line", "person": "Name", "app": "LINE", "text": "message preview"}
  ]
}
```

## Tasker Task: Send To JamesOS

Create a Task named `Send To JamesOS`.

Variables expected:

- `%j_type`
- `%j_person`
- `%j_number`
- `%j_direction`
- `%j_app`
- `%j_text`
- `%j_timestamp`

Actions:

1. Variable Set `%JAMESOS_URL` to `http://100.77.201.40:8787/phone-ingest`
2. Variable Set `%JAMESOS_KEY` to your Jade API key
3. Variable Set `%payload` to:

```json
{
  "type":"%j_type",
  "device":"pixel",
  "timestamp":"%j_timestamp",
  "person":"%j_person",
  "number":"%j_number",
  "direction":"%j_direction",
  "app":"%j_app",
  "text":"%j_text"
}
```

4. HTTP Request
   - Method: POST
   - URL: `%JAMESOS_URL`
   - Headers:

```text
Content-Type: application/json
X-JamesOS-Key: %JAMESOS_KEY
```

   - Body: `%payload`
   - Timeout: 30

## Profile 1: Incoming SMS

Tasker can capture SMS directly on many Android devices.

Profile:

- Event → Phone → Received Text

Linked Task:

1. Variable Set `%j_type` = `sms`
2. Variable Set `%j_person` = `%SMSRN`
3. Variable Set `%j_number` = `%SMSRF`
4. Variable Set `%j_direction` = `inbound`
5. Variable Set `%j_app` = `Messages`
6. Variable Set `%j_text` = `%SMSRB`
7. Variable Set `%j_timestamp` = `%DATE %TIME`
8. Perform Task → `Send To JamesOS`

## Profile 2: Missed/Incoming/Outgoing calls

Tasker call variables vary by Android version. Start with missed/incoming call events and adjust after testing.

Profile options:

- Event → Phone → Missed Call
- Event → Phone → Phone Ringing
- Event → Phone → Phone Offhook

Linked Task example:

1. Variable Set `%j_type` = `call`
2. Variable Set `%j_person` = `%CNAME`
3. Variable Set `%j_number` = `%CNUM`
4. Variable Set `%j_direction` = `incoming` or `missed`
5. Variable Set `%j_app` = `Phone`
6. Variable Set `%j_text` = `Call event: %j_direction`
7. Variable Set `%j_timestamp` = `%DATE %TIME`
8. Perform Task → `Send To JamesOS`

For a full daily call-log sweep, use Tasker SQL/content-provider actions if available on your device, or use a call-log export plugin. Notification/event capture is easier and safer to start.

## Profile 3: Facebook Messenger notifications

Requires AutoNotification.

Profile:

- Event → Plugin → AutoNotification → Intercept
- App: Messenger

Linked Task:

1. Variable Set `%j_type` = `messenger`
2. Variable Set `%j_person` = `%antitle`
3. Variable Set `%j_number` = empty
4. Variable Set `%j_direction` = `inbound`
5. Variable Set `%j_app` = `Messenger`
6. Variable Set `%j_text` = `%antext`
7. Variable Set `%j_timestamp` = `%DATE %TIME`
8. Perform Task → `Send To JamesOS`

## Profile 4: LINE notifications

Requires AutoNotification.

Profile:

- Event → Plugin → AutoNotification → Intercept
- App: LINE

Linked Task:

1. Variable Set `%j_type` = `line`
2. Variable Set `%j_person` = `%antitle`
3. Variable Set `%j_number` = empty
4. Variable Set `%j_direction` = `inbound`
5. Variable Set `%j_app` = `LINE`
6. Variable Set `%j_text` = `%antext`
7. Variable Set `%j_timestamp` = `%DATE %TIME`
8. Perform Task → `Send To JamesOS`

## Daily summary

On desktop/server:

```bash
cd ~/JamesOS
source .venv/bin/activate
PYTHONPATH=. python3 scripts/phone_daily_summary.py
```

Output:

```text
~/Notes/JamesOS/Reports/Phone/Phone Daily Summary.md
```

## Quick test from phone or laptop

```bash
curl -X POST http://100.77.201.40:8787/phone-ingest \
  -H "Content-Type: application/json" \
  -H "X-JamesOS-Key: YOUR_KEY" \
  -d '{"type":"sms","device":"test","person":"Test Person","number":"555","direction":"inbound","app":"Messages","text":"Hello from Tasker test"}'
```
