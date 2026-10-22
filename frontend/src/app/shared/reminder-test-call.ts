import { Component, OnDestroy, OnInit, inject, input, output, signal } from '@angular/core';
import { ApiService, errorText } from '../core/api.service';
import { TranscriptLine } from '../core/models';
import { CallTranscript, intentClass, intentLabel } from './reminders';

const RATE = 16000;
/** ~20 ms of 16 kHz audio per WebSocket frame. */
const FRAME_SAMPLES = 320;
/** Mic level (RMS) above which we treat the tester as talking, for barge-in. */
const VOICE_RMS = 0.02;

type Phase = 'starting' | 'connecting' | 'live' | 'ending' | 'ended' | 'error';
type AgentState = 'listening' | 'thinking' | 'speaking' | '';

/** AudioWorklet that forwards mic samples in ~2048-sample blocks. Loaded from a Blob URL. */
const WORKLET_SOURCE = `
class MicCapture extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Float32Array(2048); this.n = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      for (let i = 0; i < ch.length; i++) {
        this.buf[this.n++] = ch[i];
        if (this.n === this.buf.length) { this.port.postMessage(this.buf.slice(0)); this.n = 0; }
      }
    }
    return true;
  }
}
registerProcessor('mic-capture', MicCapture);
`;

/** Turns native-rate float samples into 16 kHz mono s16le frames (box-filter downsampling). */
class Downsampler {
  private carry = new Float32Array(0);
  private pending: number[] = [];
  constructor(private ratio: number) {}

  /** Returns complete FRAME_SAMPLES-sized little-endian PCM frames. */
  push(input: Float32Array): ArrayBuffer[] {
    const data = new Float32Array(this.carry.length + input.length);
    data.set(this.carry);
    data.set(input, this.carry.length);
    const outLen = Math.floor(data.length / this.ratio);
    for (let i = 0; i < outLen; i++) {
      const start = Math.floor(i * this.ratio);
      const end = Math.max(start + 1, Math.floor((i + 1) * this.ratio));
      let sum = 0;
      for (let j = start; j < end; j++) sum += data[j];
      this.pending.push(sum / (end - start));
    }
    this.carry = data.slice(Math.floor(outLen * this.ratio));

    const frames: ArrayBuffer[] = [];
    while (this.pending.length >= FRAME_SAMPLES) {
      const chunk = this.pending.splice(0, FRAME_SAMPLES);
      const buf = new ArrayBuffer(FRAME_SAMPLES * 2);
      const view = new DataView(buf);
      chunk.forEach((v, i) => {
        const s = Math.max(-1, Math.min(1, v));
        view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      });
      frames.push(buf);
    }
    return frames;
  }
}

/**
 * Two-way test of the payment reminder voice agent from the browser: no phone line needed.
 * Mic → 16 kHz s16le frames over the WebSocket; agent PCM frames are played back gaplessly.
 */
@Component({
  selector: 'app-reminder-test-call',
  imports: [CallTranscript],
  template: `
    <div class="overlay">
      <div class="dialog wide" role="dialog" aria-label="Test call in browser">
        <div class="card-head">
          <h2>Test call in browser</h2>
          <span [class]="'badge plain ' + phaseClass()">{{ phaseLabel() }}</span>
          <div class="spacer"></div>
          <button class="btn btn-sm btn-ghost" (click)="close()" aria-label="Close">✕</button>
        </div>
        <div class="card-body body">
          <p class="small muted flat">You play the customer. Speak into your microphone; the AI agent talks back through your speakers.
            Use headphones to avoid echo. Test calls do not count as reminder attempts.</p>

          @if (phase() === 'live') {
            <div class="state">
              <span class="pulse" [class]="'pulse ' + (agentState() || 'idle')"></span>
              <strong>{{ stateLabel() }}</strong>
            </div>
          }
          @if (error()) { <div class="banner danger">{{ error() }}</div> }

          <app-call-transcript [lines]="lines()" emptyText="The conversation will appear here." />

          @if (result(); as r) {
            <div class="result">
              <div class="row wrap"><span class="label">Result</span>
                @if (r.intent) { <span [class]="'badge ' + intentClass(r.intent)">{{ intentLabel(r.intent) }}</span> }
                @else { <span class="faint">no intent</span> }
              </div>
              @if (r.summary) { <div>{{ r.summary }}</div> }
            </div>
          }
        </div>
        <div class="dialog-actions">
          @if (phase() === 'live' || phase() === 'connecting' || phase() === 'starting') {
            <button class="btn btn-danger" (click)="hangup()">Hang up</button>
          } @else {
            <button class="btn" (click)="close()">Close</button>
          }
        </div>
      </div>
    </div>
  `,
  styles: `
    .dialog.wide { width: min(640px, 100%); max-height: calc(100vh - 32px); display: flex; flex-direction: column; }
    .body { overflow-y: auto; }
    .flat { margin: 0; }
    .state { display: flex; align-items: center; gap: 10px; }
    .pulse { width: 12px; height: 12px; border-radius: 50%; background: var(--faint); }
    .pulse.listening { background: var(--accent); box-shadow: 0 0 0 4px rgba(37,211,102,.2); }
    .pulse.thinking { background: var(--warn); animation: blink 1s infinite; }
    .pulse.speaking { background: #4b45b5; animation: blink .6s infinite; }
    @keyframes blink { 50% { opacity: .35; } }
    .result { background: var(--brand-soft); border: 1px solid #bfe0d3; border-radius: 8px; padding: 10px 12px;
      display: flex; flex-direction: column; gap: 6px; }
  `,
})
export class ReminderTestCall implements OnInit, OnDestroy {
  readonly orderId = input.required<number>();
  readonly closed = output<void>();
  private api = inject(ApiService);

  protected phase = signal<Phase>('starting');
  protected agentState = signal<AgentState>('');
  protected lines = signal<TranscriptLine[]>([]);
  protected result = signal<{ intent: string | null; summary: string | null } | null>(null);
  protected error = signal('');
  protected intentLabel = intentLabel;
  protected intentClass = intentClass;

  private ws?: WebSocket;
  private ctx?: AudioContext;
  private stream?: MediaStream;
  private source?: MediaStreamAudioSourceNode;
  private capture?: AudioWorkletNode | ScriptProcessorNode;
  private sink?: GainNode;
  private workletUrl?: string;
  private downsampler?: Downsampler;
  private playing = new Set<AudioBufferSourceNode>();
  private playhead = 0;
  private oddByte: number | null = null;
  private lastVoiceAt = 0;
  private endTimer?: ReturnType<typeof setTimeout>;
  private done = false;

  ngOnInit() { this.start(); }

  ngOnDestroy() {
    this.done = true;
    this.cleanup(true);
  }

  private async start() {
    try {
      // Mic + audio first so the browser asks for permission straight away.
      this.ctx = new AudioContext();
      if (this.ctx.state === 'suspended') await this.ctx.resume().catch(() => undefined);
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      if (this.done) return this.cleanup(true);
      await this.setupCapture();
      if (this.done) return this.cleanup(true);
    } catch (err: any) {
      return this.fail(err?.name === 'NotAllowedError'
        ? 'Microphone access was blocked. Allow the microphone for this site and try again.'
        : `Could not start the microphone: ${err?.message ?? err}`);
    }

    this.phase.set('connecting');
    this.api.testReminder(this.orderId()).subscribe({
      next: res => { if (!this.done) this.connect(res.ws_url); },
      error: err => this.fail(errorText(err)),
    });
  }

  private async setupCapture() {
    const ctx = this.ctx!;
    this.downsampler = new Downsampler(ctx.sampleRate / RATE);
    this.source = ctx.createMediaStreamSource(this.stream!);
    // the capture node must reach the destination to be pulled; keep it silent
    this.sink = ctx.createGain();
    this.sink.gain.value = 0;
    this.sink.connect(ctx.destination);

    if (ctx.audioWorklet && typeof AudioWorkletNode !== 'undefined') {
      try {
        this.workletUrl = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: 'application/javascript' }));
        await ctx.audioWorklet.addModule(this.workletUrl);
        const node = new AudioWorkletNode(ctx, 'mic-capture', { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
        node.port.onmessage = (e: MessageEvent<Float32Array>) => this.onMic(e.data);
        this.source.connect(node).connect(this.sink);
        this.capture = node;
        return;
      } catch { /* fall back to ScriptProcessor below */ }
    }
    const node = ctx.createScriptProcessor(2048, 1, 1);
    node.onaudioprocess = e => this.onMic(new Float32Array(e.inputBuffer.getChannelData(0)));
    this.source.connect(node).connect(this.sink);
    this.capture = node;
  }

  private onMic(samples: Float32Array) {
    let sq = 0;
    for (let i = 0; i < samples.length; i++) sq += samples[i] * samples[i];
    if (Math.sqrt(sq / samples.length) > VOICE_RMS) this.lastVoiceAt = performance.now();

    const frames = this.downsampler?.push(samples) ?? [];
    if (this.ws?.readyState !== WebSocket.OPEN || this.phase() !== 'live') return;
    for (const f of frames) this.ws.send(f);
  }

  private connect(url: string) {
    if (url.startsWith('/')) url = `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}${url}`;
    let ws: WebSocket;
    try { ws = new WebSocket(url); } catch (err: any) { return this.fail(`Could not connect to the voice agent: ${err?.message ?? err}`); }
    ws.binaryType = 'arraybuffer';
    this.ws = ws;
    ws.onopen = () => this.phase.set('live');
    ws.onmessage = e => {
      if (e.data instanceof ArrayBuffer) this.play(e.data);
      else this.onText(String(e.data));
    };
    ws.onerror = () => {
      if (this.phase() === 'connecting') this.fail('Could not connect to the voice agent. Is it running?');
    };
    ws.onclose = () => {
      this.ws = undefined;
      if (this.phase() !== 'error') this.phase.set('ended');
      this.agentState.set('');
      this.stopMic();
    };
  }

  private onText(raw: string) {
    let msg: any;
    try { msg = JSON.parse(raw); } catch { return; }
    if (msg.type === 'transcript' && msg.text) {
      this.lines.update(l => [...l, { speaker: msg.speaker === 'agent' ? 'agent' : 'customer', text: msg.text }]);
    } else if (msg.type === 'state') {
      // barge-in: the agent stopped to listen while we still have its speech queued and the tester is talking
      if (msg.state === 'listening' && this.playing.size && performance.now() - this.lastVoiceAt < 1000) this.flushPlayback();
      this.agentState.set(msg.state);
    } else if (msg.type === 'end') {
      this.result.set({ intent: msg.intent ?? null, summary: msg.summary ?? null });
      this.phase.set('ending');
      this.stopMic();
      // the agent closes the socket after "end"; make sure it does not linger
      this.endTimer = setTimeout(() => this.ws?.close(), 3000);
    }
  }

  /** Queue one 16 kHz s16le chunk right after the previous one so playback is gapless. */
  private play(data: ArrayBuffer) {
    const ctx = this.ctx;
    if (!ctx || ctx.state === 'closed') return;
    let bytes = new Uint8Array(data);
    if (this.oddByte !== null) {
      const joined = new Uint8Array(bytes.length + 1);
      joined[0] = this.oddByte;
      joined.set(bytes, 1);
      bytes = joined;
      this.oddByte = null;
    }
    if (bytes.length % 2) { this.oddByte = bytes[bytes.length - 1]; bytes = bytes.subarray(0, bytes.length - 1); }
    const n = bytes.length / 2;
    if (!n) return;

    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const buffer = ctx.createBuffer(1, n, RATE);
    const out = buffer.getChannelData(0);
    for (let i = 0; i < n; i++) out[i] = view.getInt16(i * 2, true) / 0x8000;

    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    const startAt = Math.max(this.playhead, ctx.currentTime + 0.05);
    src.start(startAt);
    this.playhead = startAt + buffer.duration;
    this.playing.add(src);
    src.onended = () => this.playing.delete(src);
  }

  private flushPlayback() {
    for (const src of this.playing) { try { src.stop(); } catch { /* already stopped */ } }
    this.playing.clear();
    this.playhead = 0;
    this.oddByte = null;
  }

  protected hangup() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      try { this.ws.send(JSON.stringify({ type: 'hangup' })); } catch { /* ignore */ }
      this.phase.set('ending');
      this.stopMic();
      this.flushPlayback();
      // wait briefly for the agent's "end" (intent + summary), then close regardless
      this.endTimer = setTimeout(() => this.ws?.close(), 4000);
    } else {
      this.done = true;
      this.cleanup(true);
      this.phase.set('ended');
    }
  }

  protected close() {
    this.done = true;
    this.cleanup(true);
    this.closed.emit();
  }

  private fail(text: string) {
    this.error.set(text);
    this.phase.set('error');
    this.cleanup(true);
  }

  private stopMic() {
    this.stream?.getTracks().forEach(t => t.stop());
    this.stream = undefined;
    if (this.capture) {
      if (this.capture instanceof ScriptProcessorNode) this.capture.onaudioprocess = null;
      else this.capture.port.onmessage = null;
      this.capture.disconnect();
      this.capture = undefined;
    }
    this.source?.disconnect();
    this.source = undefined;
  }

  private cleanup(closeSocket: boolean) {
    clearTimeout(this.endTimer);
    this.stopMic();
    this.flushPlayback();
    if (closeSocket && this.ws) {
      const ws = this.ws;
      this.ws = undefined;
      ws.onmessage = ws.onerror = ws.onclose = null;
      if (ws.readyState === WebSocket.OPEN) { try { ws.send(JSON.stringify({ type: 'hangup' })); } catch { /* ignore */ } }
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close();
    }
    this.sink?.disconnect();
    this.sink = undefined;
    if (this.ctx && this.ctx.state !== 'closed') this.ctx.close().catch(() => undefined);
    this.ctx = undefined;
    if (this.workletUrl) { URL.revokeObjectURL(this.workletUrl); this.workletUrl = undefined; }
  }

  protected phaseLabel() {
    return ({ starting: 'Starting microphone…', connecting: 'Connecting…', live: 'On call', ending: 'Ending…',
      ended: 'Call ended', error: 'Failed' } as Record<Phase, string>)[this.phase()];
  }
  protected phaseClass() {
    return ({ starting: '', connecting: 's-new', live: 'ok', ending: 'warn', ended: '', error: 'danger' } as Record<Phase, string>)[this.phase()];
  }
  protected stateLabel() {
    return ({ listening: 'Listening – speak now', thinking: 'Thinking…', speaking: 'Agent speaking' } as Record<string, string>)[this.agentState()]
      ?? 'Waiting for the agent…';
  }
}
