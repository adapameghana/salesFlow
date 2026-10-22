# Payment reminder calls (AI voice)

Orders that are not fully paid get an automatic phone call from an AI voice agent. The agent speaks to the customer in their language (English, Hindi, Telugu or Tamil), reminds them of the pending amount, and understands their spoken reply. Everything is open source and runs on your own machines.

```
 ┌──────────────┐  every 30 min   ┌───────────────┐  POST /calls      ┌──────────────┐  ARI + AudioSocket  ┌──────────┐
 │ backend      │ ──────────────▶ │ reminder      │ ────────────────▶ │ voice_agent  │ ◀─────────────────▶ │ Asterisk │──▶ phone line
 │ (FastAPI)    │                 │ service       │                   │ (Pipecat,    │                     └──────────┘   (Bluetooth SIM
 │              │ ◀────────────── │               │ ◀──────────────── │  Whisper,    │                                     / SIP trunk)
 └──────────────┘   result + transcript            POST .../result   │  Ollama, TTS)│
                                                                       └──────────────┘
```

## Rules
- **Who is called:** an order qualifies when all of these are true:
  - payment status is not Paid;
  - the balance is above 0;
  - the order is not Cancelled;
  - the order has a valid Indian mobile number;
  - the order is at least `REMINDER_FIRST_AFTER_HOURS` old;
  - it has had fewer than `REMINDER_MAX_ATTEMPTS` calls;
  - the last call was at least `REMINDER_GAP_HOURS` ago;
  - reminders are on for the order;
  - today is on or after any promised payment date.
- **When calls are made:** only between `REMINDER_WINDOW_START` and `REMINDER_WINDOW_END`, business time (IST). Calls go out one at a time.
- **What the call says:** a greeting, the pending amount, and a request for when they can pay. The agent understands the reply as one of these intents:

| intent | effect |
|---|---|
| `paid_claimed` | needs follow-up: staff verify the payment (the order is never auto-marked Paid) |
| `will_pay` | `promised_date` is saved on the order; no calls until that date |
| `ask_details` | the agent repeats the amount and items (from the DB only) |
| `callback`, `dispute`, `other` | needs follow-up: the team calls back |
| `wrong_number`, `not_interested` | reminders are turned off for the order |
| `no_response` | nothing; counts as an attempt |

## Configuration (`backend/.env`)
See `backend/.env.example`: `REMINDERS_ENABLED`, `REMINDER_*`, `BUSINESS_NAME`, `VOICE_AGENT_URL`, `VOICE_AGENT_WS_URL`, `VOICE_AGENT_SECRET`, `REMINDER_RECORDINGS_DIR`.

---

## Interface contract

All calls between the backend and the voice agent carry the header `X-Agent-Secret: <VOICE_AGENT_SECRET>`.

### Backend → voice agent: place a call
`POST {VOICE_AGENT_URL}/calls`
```json
{
  "call_id": 42,
  "phone": "9876543210",
  "context": {
    "order_id": 7, "order_number": "ORD-2026-0007", "customer_name": "Sri Sai Clinic",
    "language": "te", "balance": 4250.0, "amount_due": 5000.0, "amount_paid": 750.0,
    "business_name": "Dhanush Healthcare", "attempt_no": 1,
    "items": [{"name": "Nitrile gloves M", "quantity": 5, "unit": "box"}],
    "today": "2026-10-22"
  }
}
```
- The response is `202 {"accepted": true}`. Any other status code means the call failed to start, and the backend marks the call `failed`.
- `language` is one of `en|hi|te|ta`. `phone` is 10 digits with no country code.

### Voice agent → backend: call context (used by browser test calls)
`GET {BACKEND_URL}/api/internal/reminders/{call_id}/context` returns `{"call_id": 42, "phone": "...", "context": {...same as above...}}`.

### Voice agent → backend: call result
`POST {BACKEND_URL}/api/internal/reminders/{call_id}/result`
```json
{
  "status": "answered",
  "intent": "will_pay",
  "promised_date": "2026-10-24",
  "summary": "Customer said they will pay by UPI on Friday.",
  "transcript": [
    {"speaker": "agent", "text": "Namaskaram ...", "ts": 0.0},
    {"speaker": "customer", "text": "...", "ts": 6.2}
  ],
  "duration_seconds": 48,
  "recording_wav_base64": "UklGRi4uLg==",
  "error": null
}
```
- `status` is one of `answered|no_answer|busy|failed`.
- `intent` is one of `paid_claimed|will_pay|ask_details|callback|dispute|wrong_number|not_interested|no_response|other`, or null.
- `promised_date` is `YYYY-MM-DD` or null.
- `recording_wav_base64` is optional.

### Browser test call (no phone line)
1. The frontend calls `POST /api/orders/{id}/reminders/test`. The backend creates a call row (`provider='browser'`, `status='test'`) and returns:
   - `call_id`;
   - `ws_url`, of the form `{VOICE_AGENT_WS_URL}/test?call_id=42&token=<hmac>`.

   `token` is the hex HMAC-SHA256 of `str(call_id)` keyed with `VOICE_AGENT_SECRET`.
2. The browser opens the WebSocket. The agent checks the token and loads the context through the context endpoint.
3. **Browser → agent:** binary frames of 16 kHz mono signed 16-bit little-endian PCM (microphone audio). It can also send the text frame `{"type":"hangup"}`.
4. **Agent → browser:**
   - binary frames of 16 kHz mono s16le PCM (the agent's voice);
   - text JSON frames:
     - `{"type":"transcript","speaker":"agent|customer","text":"..."}`
     - `{"type":"state","state":"listening|thinking|speaking"}`
     - `{"type":"end","intent":"...","summary":"..."}`

     The socket closes after `end`.
5. At the end the agent POSTs the result as for a phone call. The backend keeps `status='test'` for browser calls, so they do not count as attempts.
