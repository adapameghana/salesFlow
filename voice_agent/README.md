# Payment reminder voice agent

A self-hosted, open-source AI voice agent. It phones customers whose orders are not fully paid, tells them the pending amount, and has a short spoken conversation in **English, Hindi, Telugu or Tamil**. It does not use a keypad. The agent understands replies like "I'll pay on Friday", "I already paid by PhonePe" or "which order is this?", then reports the outcome to the order backend.

Nothing runs in the cloud and there are no per-minute fees. You only pay for your own phone line.

| Piece | Project |
|---|---|
| Telephony | [Asterisk](https://www.asterisk.org/): ARI to place calls, AudioSocket to stream audio |
| Turn detection | Silero VAD, with WebRTC VAD or an energy threshold as fallbacks |
| Speech to text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper), language fixed to the order's language |
| Understanding | [Ollama](https://ollama.com) (default `qwen2.5:7b`), with a keyword fallback |
| Replies | Fixed, polite phrases per language (`phrases.py`), filled only from order data |
| Text to speech | [AI4Bharat Indic Parler-TTS](https://huggingface.co/ai4bharat/indic-parler-tts) |

The interface with the backend is defined in [`docs/PAYMENT_REMINDERS.md`](../docs/PAYMENT_REMINDERS.md).

## How a call works

```
backend ──POST /calls──▶ queue (one call at a time)
                           │ pre-generate the personalised greeting audio
                           ▼
                     ARI originate ──▶ Asterisk ──▶ phone rings
                           │                       │ answered
                           │      AudioSocket(UUID) ◀┘ dialplan
                           ▼
   ┌──────────── CallSession (pipeline.py) ─────────────┐
   │ audio ─▶ VAD turns ─▶ Whisper ─▶ Brain ─▶ TTS ─▶ audio │
   │            ▲ barge-in stops playback when the customer talks │
   └────────────────────────────────────────────────────┘
                           │
backend ◀──POST /api/internal/reminders/{id}/result── transcript, intent, date, WAV
```

* **Brain** (`brain.py`). This is a small state machine. The LLM only labels what the customer said as JSON: `{intent, promised_date, paid_method, note}`. It never writes what the agent says, so the agent cannot invent amounts, dates or discounts.
  * greeting → "When will you be able to make the payment?"
  * `paid_claimed` → one question ("how and when did you pay?"), then thanks and "the team will verify".
  * `will_pay` → confirms the date. If no date was given, it asks once.
  * `ask_details` → repeats the amount, order number and items, then asks again.
  * `callback` and `dispute` → "our team will call you back".
  * An unclear reply gets one more try. If it is still unclear, the team calls back.
  * `wrong_number` and `not_interested` → an apology, and reminders stop.
  * Silence for 8 s → one reprompt. A second silence closes the call as `no_response`.
* **Limits.** A call allows at most 4 customer turns and lasts at most 2 minutes. The closing message always plays to the end.
* **Amounts and dates** are spelled out as words in each language (`numwords.py`, Indian numbering up to crores). For example, 4250 is read as "నాలుగు వేల రెండు వందల యాభై రూపాయలు".

## Hardware

* **Recommended:** an NVIDIA GPU with 8–12 GB of VRAM. Whisper large-v3 in float16 needs about 4 GB and Parler-TTS about 3 GB. With these, a reply starts about 1–2 s after the customer stops talking.
* **CPU only** works for browser testing, but it is slow: several seconds for each reply. Fixed phrases come from the cache, so only the parts that change (names and amounts) are synthesised during the call. For CPU, set `WHISPER_MODEL=medium` or `small`.
* Disk space: about 10 GB for the models.

## Setup (Ubuntu 22.04/24.04 or WSL2)

```bash
# from the repository root
python3 -m venv .venv-voice && source .venv-voice/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu121   # match your CUDA; CPU: omit --index-url
pip install -r voice_agent/requirements.txt
cp voice_agent/.env.example voice_agent/.env      # set VOICE_AGENT_SECRET (same as backend/.env)

# Ollama (local LLM)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b
```

The first start downloads the Whisper and Parler-TTS models from Hugging Face.

> **WSL2 note.** WSL2 can use the NVIDIA GPU, so it works well for the voice agent. It cannot see the PC's Bluetooth, though. For a Bluetooth phone line, run Asterisk on a native Linux machine instead; a Raspberry Pi or an old laptop is enough. Point that machine's AudioSocket dialplan at the IP of the machine running the agent. A SIP trunk works fine from WSL2.

## Asterisk

Install it:
```bash
sudo apt install asterisk asterisk-modules       # Asterisk 18+ includes app_audiosocket
# Bluetooth line (chan_mobile):
sudo apt install asterisk-mobile bluez            # package name may vary; otherwise build Asterisk with chan_mobile
```
Check that the modules are loaded with `asterisk -rx "module show like audiosocket"`. Do the same for `mobile` if you use a Bluetooth phone.

`/etc/asterisk/http.conf` (ARI runs over HTTP; keep it on localhost):
```ini
[general]
enabled = yes
bindaddr = 127.0.0.1
bindport = 8088
```

`/etc/asterisk/ari.conf`:
```ini
[general]
enabled = yes

[voiceagent]
type = user
read_only = no
password = change-me-too        ; = ARI_PASSWORD
```

`/etc/asterisk/extensions.conf`. When the customer answers, the call runs this context. `CALL_UUID` is set by the agent when it places the call, so the audio stream can be matched back to the right call:
```ini
[voice-agent]
exten => s,1,NoOp(Payment reminder ${CALL_UUID})
 same => n,Answer()
 same => n,AudioSocket(${CALL_UUID},127.0.0.1:9092)   ; host:port of this voice agent
 same => n,Hangup()

[incoming-mobile]
exten => s,1,Hangup()      ; we don't take inbound calls on the reminder line
```
Run `sudo asterisk -rx "core reload"` after editing these files.

### Free phone line: Bluetooth-paired Android phone with its existing SIM (chan_mobile)

1. Pair the phone with the Linux machine:
   ```bash
   bluetoothctl
   power on
   scan on
   pair AA:BB:CC:DD:EE:FF
   trust AA:BB:CC:DD:EE:FF
   ```
2. Find the phone's voice channel port: `asterisk -rx "mobile search"`.
3. Edit `/etc/asterisk/chan_mobile.conf` (named `mobile.conf` on older versions):
   ```ini
   [adapter]
   id = blue
   address = 00:11:22:33:44:55      ; from `hciconfig` / `bluetoothctl list`

   [myphone]
   address = AA:BB:CC:DD:EE:FF
   port = 2                         ; from `mobile search`
   context = incoming-mobile
   adapter = blue
   ```
4. Run `asterisk -rx "module reload chan_mobile.so"` and then `asterisk -rx "mobile show devices"`. The phone should show as *Connected*.
5. Set `ASTERISK_ENDPOINT_TEMPLATE=Mobile/myphone/{phone}`. The 10-digit number dials as a local mobile number.

This line handles one call at a time; the agent already queues calls. Keep the phone charging, and turn off battery optimisation for Bluetooth.

### Later: a SIP trunk

`/etc/asterisk/pjsip.conf` (fill in your provider's details):
```ini
[mytrunk]
type = registration
outbound_auth = mytrunk-auth
server_uri = sip:sip.provider.example
client_uri = sip:USER@sip.provider.example

[mytrunk-auth]
type = auth
auth_type = userpass
username = USER
password = PASS

[mytrunk]
type = aor
contact = sip:sip.provider.example

[mytrunk]
type = endpoint
context = incoming-mobile
disallow = all
allow = ulaw,alaw
outbound_auth = mytrunk-auth
aors = mytrunk
```
Then set `ASTERISK_ENDPOINT_TEMPLATE=PJSIP/{phone}@mytrunk`, or `PJSIP/+91{phone}@mytrunk` if your provider wants the country code.

## Running

```bash
# from the repository root, with the venv active
python -m voice_agent.server          # listens on 0.0.0.0:8100, AudioSocket on 9092
curl http://127.0.0.1:8100/health     # models loaded? asterisk/ollama reachable? cache warm-up progress
```
Set these in `backend/.env`:
```
VOICE_AGENT_URL=http://127.0.0.1:8100
VOICE_AGENT_WS_URL=ws://127.0.0.1:8100
VOICE_AGENT_SECRET=<same as voice_agent/.env>
```
At startup the agent loads the models in the background and pre-generates every fixed phrase in all four languages. The audio is cached under `CACHE_DIR/tts`. The first warm-up takes a few minutes; later starts are instant. If you change `TTS_SPEAKERS` or `TTS_VOICE_DESCRIPTION`, the phrases are generated again automatically.

## Testing without a phone line (browser test)

In the order app, open an unpaid order and click **Test reminder call**. The browser opens `WS /test?call_id=…&token=…`. The agent checks the HMAC token, loads the call context from the backend, and talks to you through the microphone and speakers (16 kHz PCM both ways). The page shows the live transcript and agent state, and the result is saved like a phone call's, but as a test call that does not count as an attempt.

Unit tests need no GPU or network:
```bash
python -m pytest voice_agent/tests
```

## Laptop demo (Windows, no NVIDIA card)

The browser test call needs no phone line, no Asterisk and no Linux. It runs directly on Windows, on the processor. Three things keep it responsive on a laptop:

- **Smaller models.** Use Whisper `small` and Ollama `qwen2.5:1.5b`. Each reply then takes about 2–4 s to understand.
- **Speech made in advance.** Making speech is slow on a CPU (10–30 s a sentence), so `voice_agent.prepare` makes every sentence the agent can say before the demo.
- **Already-made speech can be copied.** The fixed sentences are the same everywhere. Make them once on a PC with an NVIDIA card and copy the `voice_agent/cache` folder to the laptop, which saves about an hour.

### One-time setup on the laptop (needs internet; about 5 GB of downloads)
1. Set up the order app as in the main README: PostgreSQL, the database scripts including `08_payment_reminders.sql`, the backend and the frontend.
2. Install Ollama, then run `ollama pull qwen2.5:1.5b`.
3. Install the voice agent's Python packages (Python 3.10 or 3.11, CPU build of torch) into its own environment. Run this from the project folder. `scripts\start-voice-agent.bat` uses this environment automatically.
   ```bat
   python -m venv voice_agent\.venv
   voice_agent\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
   voice_agent\.venv\Scripts\python.exe -m pip install -r voice_agent\requirements.txt
   ```
4. Create `voice_agent\.env` from `.env.example` with these changes:
   ```
   VOICE_AGENT_SECRET=<same value as VOICE_AGENT_SECRET in backend\.env>
   HF_TOKEN=<your Hugging Face Read token, see below>
   OLLAMA_MODEL=qwen2.5:1.5b
   WHISPER_MODEL=small
   WHISPER_DEVICE=cpu
   WHISPER_COMPUTE_TYPE=int8
   TTS_DEVICE=cpu
   WARM_LANGS=en,te          # only the languages you will demo
   ```
   In `backend\.env`, set the same `VOICE_AGENT_SECRET` and `REMINDER_TEST_CALLS_APPLY=true`. That way, test calls update the order like real calls: it gets a promised date, appears in Needs follow-up, or has reminders turned off.

   The voice model is free but gated on Hugging Face. To get a token:
   1. Make a free account at huggingface.co.
   2. Accept the terms at https://huggingface.co/ai4bharat/indic-parler-tts.
   3. Create a **Read** token at https://huggingface.co/settings/tokens.

   Keep `TTS_MODEL`, `TTS_SPEAKERS` and `TTS_VOICE_DESCRIPTION` exactly the same on every machine. Prepared speech is matched on these values.
5. Run `scripts\start-voice-agent.bat` once while online. This downloads the speech models (about 3 GB) into the Hugging Face cache. Then close it.

### Prepare the speech
1. **Fixed sentences:** run this on the NVIDIA PC (fast) or on the laptop (about an hour).
   ```bat
   python -m voice_agent.prepare --static
   ```
   If you ran it on the PC, copy `voice_agent\cache` to the same place on the laptop.
2. **Your demo orders:** run this **on the laptop, on the demo day**, with the backend running. The greeting includes the order's current balance, and "tomorrow" depends on the date.
   ```bat
   python -m voice_agent.prepare --order ORD-2026-0007 --order ORD-2026-0008
   ```
   - It takes about 5–10 minutes for each order.
   - Add `--all-langs` if you want to switch an order's language during the demo.
   - If you change an order's amount, language or customer name, run it again for that order.

### During the demo
1. Start the backend, frontend and `scripts\start-voice-agent.bat`. Wait for `/health` to show the models loaded.
2. Open an unpaid order, set its language, and click **Test call in browser**.
3. Talk to the agent through the mic, for example:
   - "I already paid by UPI yesterday" → needs follow-up;
   - "I will pay on Friday" → promised date;
   - "What is this for?" → it reads out the order details;
   - "Wrong number" → reminders stop.
4. Afterwards, show the transcript and the result on the **Payment Reminders** page.

Tips:
- Use a headset. Laptop speakers can echo into the mic and interrupt the agent.
- Rehearse once with the exact orders you will show.
- With `REMINDER_TEST_CALLS_APPLY=true`, a test call does change the order. To repeat a scenario, clear the promised date or switch reminders back on in the order's Payment reminders card.

## Compliance (India / TRAI)

* Use this only for **service and transactional calls** to existing customers about their own orders. Do not use it for promotions.
* Call only between **10:00 and 19:00**. The backend enforces `REMINDER_WINDOW_START`/`END`; keep those inside this window.
* When a customer says *not interested*, *don't call* or *wrong number*, reminders for that order stop automatically.
* Tell customers that calls may be recorded, or set `INCLUDE_RECORDING=false`.

## Troubleshooting

| Symptom | Check |
|---|---|
| `/health` shows `asterisk: false` | Check `http.conf` and `ari.conf`, and that `ARI_URL`, `ARI_USER` and `ARI_PASSWORD` are right. Test with `curl -u voiceagent:pass http://127.0.0.1:8088/ari/asterisk/info`. |
| Phone rings, but the call is silent and the result is `no_answer` | The AudioSocket connection never arrived. Check the dialplan host:port, any firewall on port 9092, and `audiosocket: true` in `/health`. Watch with `asterisk -rvvv`. |
| Every call reports `failed` | Run `asterisk -rx "mobile show devices"` and check the device is Connected. Check that the endpoint template is right. |
| Agent talks over the customer, or cuts itself off | Adjust `VAD_THRESHOLD`: higher means less sensitive. Echo on the line can trigger barge-in. |
| Long pauses before replies | The models are on CPU, or the GPU is too small. Check that `/health` models are loaded, and try `WHISPER_MODEL=large-v3-turbo`. |
| Wrong intents | Check that `ollama list` includes `OLLAMA_MODEL`. When Ollama is down, the keyword fallback (`heuristics.py`) is used. Add the customer's common phrasings there. |
| Indic speech sounds unnatural on English names | Parler-TTS reads Latin-script names with an Indic voice. Store names in native script if this matters. |

## Code map

| File | Purpose |
|---|---|
| `server.py` | FastAPI app: `POST /calls`, `GET /health`, `WS /test`, the call queue, the browser transport |
| `pipeline.py` | `CallSession`: the realtime loop (VAD turns, barge-in, silence and time limits, recording), plus the `Transport` interface |
| `brain.py` | Conversation state machine and English summary |
| `llm.py` / `heuristics.py` | Ollama classifier and its validation / keyword and date fallback |
| `phrases.py` / `numwords.py` | Phrases per language / numbers, rupees and dates as words |
| `stt.py`, `tts.py`, `tts_cache.py`, `vad.py` | Model wrappers. Heavy imports are lazy, so tests don't need them. |
| `asterisk_ari.py`, `audiosocket.py` | Placing calls, detecting busy or no answer, AudioSocket framing and server |
| `recorder.py`, `result_client.py` | Mixed mono WAV recording; backend context and result client with retries |

Why not Pipecat? Pipecat's Asterisk support and frame APIs change from release to release. This pipeline is a short asyncio loop with explicit interfaces (Transport, STT, TTS, VAD), so the same session code serves both the phone and the browser, and it is fully unit-tested with fakes.
