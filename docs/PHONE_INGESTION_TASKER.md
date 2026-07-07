# Phone Ingestion With Tasker

JamesOS can receive phone activity from Android through Tasker. This is designed for James's own phone and local assistant context.

## Endpoint

```text
POST /phone-ingest
Header: X-JamesOS-Key: <api key>
Content-Type: application/json
```

Example URL on the desktop/server:

```text
http://DESKTOP_OR_MESHNET_IP:8787/phone-ingest
```

## Privacy Defaults

- Only ingest events from James's own phone.
- Start with SMS/call events before notification capture.
- Notification capture should ingest new notification previews only, not full third-party app history.
- Keep generated phone reports under `~/JamesOSData`.

## Single Event Payload

```json
{
  "type": "sms",
  "device": "pixel",
  "timestamp": "2026-07-06T12:00:00-05:00",
  "person": "Name or number",
  "number": "+15551234567",
  "direction": "inbound",
  "app": "Messages",
  "text": "Message body or notification preview"
}
```

## Batch Payload

```json
{
  "events": [
    {
      "type": "call",
      "device": "pixel",
      "person": "Name",
      "number": "+15551234567",
      "direction": "missed",
      "app": "Phone",
      "text": "Missed call"
    }
  ]
}
```

## Tasker Task

Create a Tasker task named `Send To JamesOS`.

Variables:

- `%j_type`
- `%j_person`
- `%j_number`
- `%j_direction`
- `%j_app`
- `%j_text`
- `%j_timestamp`

HTTP Request:

- Method: `POST`
- URL: `%JAMESOS_URL`
- Headers:

```text
Content-Type: application/json
X-JamesOS-Key: %JAMESOS_KEY
```

Body:

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

## Suggested Profiles

### Incoming SMS

- Event: Phone -> Received Text
- Type: `sms`
- App: `Messages`
- Person/number/text from Tasker SMS variables

### Calls

- Events: Missed Call, Phone Ringing, Phone Offhook
- Type: `call`
- App: `Phone`
- Direction: `incoming`, `outgoing`, or `missed`

### Messenger / LINE Notifications

Requires AutoNotification.

- Event: AutoNotification Intercept
- Type: `messenger` or `line`
- Person: notification title
- Text: notification text

## Quick Test

```bash
curl -X POST http://localhost:8787/phone-ingest \
  -H "Content-Type: application/json" \
  -H "X-JamesOS-Key: YOUR_KEY" \
  -d '{"type":"sms","device":"test","person":"Test","number":"555","direction":"inbound","app":"Messages","text":"Hello from Tasker"}'
```

## Related Legacy Doc

The older detailed setup notes remain in:

```text
docs/tasker-phone-ingest.md
```
