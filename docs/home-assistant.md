# Home Assistant integration

Two independent ways to connect the tracker to Home Assistant (HA). Both are opt-in,
send only coarse, discreet data, and can be revoked at any time.

| | Direction | Use it for |
|---|---|---|
| Webhook | tracker -> HA (push) | instant automations when a period starts or ends |
| RESTful sensor | HA -> tracker (poll) | a sensor entity with the current state |

## 0. Server settings

* `PUBLIC_BASE_URL` (optional): used to print absolute URLs. Without it the API
  returns only the path (`/ha/<token>/state`); prefix your own origin.
* **`ALLOW_PRIVATE_WEBHOOKS=1`**: by default webhook targets that are private,
  loopback or link-local (10.x, 192.168.x, 127.x, 169.254.x, `localhost`, ...) are
  refused (SSRF guard), at registration *and* at delivery. Home Assistant normally
  lives on your LAN, so a homelab install must set this environment variable on the
  tracker's container/process. Public HTTPS targets work without it.
* `WEBHOOK_SCHEDULER_SECONDS=900` (optional): starts a small background loop that
  fires the time-driven events (`period_expected_soon`, `fertile_window_starting`).
  Alternatively run `flask webhooks tick` from cron every 15-60 minutes. Run only one
  of the two; either is safe with several workers (each event fires once per cycle).

## 1. Webhook (push)

Create a webhook in HA first so you know its URL (step 1a), then register it:

```sh
TOKEN=...   # your JWT access token
curl -X POST https://tracker.example/users/me/webhooks \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"url": "http://homeassistant.local:8123/api/webhook/CHANGE_ME_long_random_id",
       "events": ["period_started", "period_ended", "period_expected_soon"]}'
```

The response contains `secret` (`whsec_...`) **once**. `fertile_window_starting` is
only sent if you list it explicitly. `POST /users/me/webhooks/<id>/test` sends a
signed `test` event; `POST .../rotate-secret` replaces the secret.

Events: `period_started`, `period_ended`, `period_expected_soon` (once per cycle,
when P(start within 2 days) reaches 50%), `fertile_window_starting` (opt-in).

Payload (JSON, minimal):

```json
{"id": "9f3c...", "event": "period_started", "timestamp": 1790000000, "date": "2026-10-25"}
```

`period_expected_soon` adds `"probability": "50-75%"` or `"75-100%"`. Headers:
`X-Timestamp` and `X-Signature: sha256=<hex>` where the signature is
`HMAC_SHA256(secret, "<X-Timestamp>.<raw body>")`. Delivery: 3 attempts (backoff
0 s, 1 s, 3 s) on a small background worker pool (8 workers; if the queue is full an
event is dropped rather than delaying requests). Each attempt has a hard 5 s limit in
total, including connect, TLS and a slow-trickling response; 5xx/timeouts are retried,
other 4xx are not; redirects are not followed. After 10 failed deliveries in a row the
webhook is switched off and `disabled_reason` in `GET /users/me/webhooks` says why;
`PATCH {"active": true}` re-enables it. Target addresses are checked including IPv4
addresses embedded in IPv6 (NAT64, 6to4, Teredo, `::ffff:`), and multicast/reserved
ranges are refused.

Home Assistant's webhook trigger cannot verify signatures, so treat the long random
`webhook_id` as the secret, keep `local_only: true`, and do not expose HA's webhook
endpoint publicly. (A receiver that can run code, e.g. Node-RED or a proxy, should
verify `X-Signature` and reject timestamps older than a few minutes.)

### (a) Automation triggered by the webhook

```yaml
# configuration.yaml
input_boolean:
  period_started_seen:
    name: Period started (webhook seen)

automation:
  - alias: "Cycle tracker: period started"
    triggers:
      - trigger: webhook
        webhook_id: CHANGE_ME_long_random_id
        allowed_methods: [POST]
        local_only: true
    conditions:
      - condition: template
        value_template: "{{ trigger.json.event == 'period_started' }}"
    actions:
      - action: input_boolean.turn_on
        target:
          entity_id: input_boolean.period_started_seen
      - action: logbook.log
        data:
          name: Cycle tracker
          message: "{{ trigger.json.event }} on {{ trigger.json.date }}"
```

(Older HA versions use `trigger:` / `platform: webhook` / `action:` /
`service:`; the keys above are the 2024.10+ syntax.)

## 2. RESTful sensor (poll)

Create the secret URL (shown once, rotating replaces it):

```sh
curl -X POST https://tracker.example/users/me/home-assistant \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"include_fertile": false}'
# -> {"path": "/ha/<token>/state", "url": null}
```

`GET /ha/<token>/state` needs no other credential and returns

```json
{"state": "expected_soon", "attributes": {"days_until_likely_start": "3-7"}}
```

* `state`: `period` (bleeding now), `expected_soon` (50% or more that a period starts
  within 7 days), `none` (also when there is no data or the history has lapsed).
* `days_until_likely_start`: coarse bucket `0-2`, `3-7`, `8-14`, `15+` or `null`.
* `fertile_window` (`now`/`soon`/`no`) only when `include_fertile` is true.

```yaml
# configuration.yaml
rest:
  - resource: http://tracker.example:5000/ha/CHANGE_ME_TOKEN/state
    scan_interval: 900
    sensor:
      - name: "Cycle status"
        unique_id: cycle_status
        value_template: "{{ value_json.state }}"
        json_attributes_path: "$.attributes"
        json_attributes:
          - days_until_likely_start
```

Entity: `sensor.cycle_status` (state `period` / `expected_soon` / `none`, attribute
`days_until_likely_start`).

## Privacy notes

Payloads and the sensor never contain past dates, cycle lengths, symptoms or exact
probabilities. Sensor and share tokens are stored only as SHA-256 hashes.
Revoke with `DELETE /users/me/webhooks/<id>` and `DELETE /users/me/home-assistant`.

* **Webhook secrets are stored in clear text** in the database, because the HMAC key
  must be readable to sign each delivery (they are shown to you only once). Protect
  database backups and dumps like credentials, and use `rotate-secret` if one leaks.
* **Events can be lost.** Time-driven events (`period_expected_soon`,
  `fertile_window_starting`) are marked as sent *before* they are delivered, so each
  fires at most once per cycle even with several workers. A crash or restart between
  that mark and the send can therefore lose that one event; it is not re-sent.
  Delivery is also best-effort (see the queue and auto-disable behaviour above).
* **What repeated polling can still reveal.** The partner page and the sensor show
  only coarse buckets, but someone who polls them every day sees a time series. The
  thresholds between buckets are shifted by a stable 0-2 days per link and a bucket
  only moves further away when the forecast is clearly later, which blurs the exact
  day a bucket changes without hiding it. Roughly when the next period is due can
  still be read off the day the status changes, and the day "period expected soon"
  stops being shown is about when a period began. The partner page shows
  "Nothing to share right now" during a period unless the owner turns on
  `scope.show_current`; with it on (and always for the Home Assistant `period` state)
  the start and end of every period are visible exactly. Over months, a watcher can
  also learn the typical cycle length. Share the link only with someone you trust with
  that, and rotate or revoke it whenever that changes.
