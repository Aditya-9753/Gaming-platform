/**
 * Game sound effects, synthesised with the Web Audio API (no audio files to download).
 *
 * Everything goes through one master chain (gain -> compressor -> speakers) with a
 * short echo send, so effects sound full without clipping. Browsers only allow audio
 * after a user gesture; the context is created/resumed lazily. Sounds can be muted
 * from the header; the choice is remembered per browser.
 */

export type SoundName = 'win' | 'bigWin' | 'lose' | 'bet' | 'gem' | 'bomb' | 'cashout' | 'tick' | 'takeoff' | 'crash'

const STORAGE_KEY = 'rudra247.sound.muted'
let muted = readMuted()
const listeners = new Set<(muted: boolean) => void>()

function readMuted(): boolean {
  try { return localStorage.getItem(STORAGE_KEY) === '1' } catch { return false }
}

export function isMuted(): boolean { return muted }

export function setMuted(value: boolean): void {
  muted = value
  try { localStorage.setItem(STORAGE_KEY, value ? '1' : '0') } catch { /* private mode */ }
  if (value) activeEngine?.stop(false)
  listeners.forEach((fn) => fn(value))
}

export function onMutedChange(fn: (muted: boolean) => void): () => void {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

// ── audio graph ──────────────────────────────────────────────────────────────

interface Graph { ac: AudioContext; out: GainNode; echo: GainNode }
let graph: Graph | null = null

function getGraph(): Graph | null {
  if (typeof window === 'undefined') return null
  const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return null
  if (!graph) {
    const ac = new Ctor()
    const out = ac.createGain()
    out.gain.value = 0.9
    const comp = ac.createDynamicsCompressor()
    comp.threshold.value = -18
    comp.knee.value = 12
    comp.ratio.value = 4
    comp.attack.value = 0.004
    comp.release.value = 0.2
    out.connect(comp).connect(ac.destination)
    // Echo send: a short filtered feedback delay gives a little room
    const echo = ac.createGain()
    echo.gain.value = 0.22
    const delay = ac.createDelay(1)
    delay.delayTime.value = 0.13
    const fb = ac.createGain()
    fb.gain.value = 0.28
    const tone = ac.createBiquadFilter()
    tone.type = 'lowpass'
    tone.frequency.value = 3200
    echo.connect(delay).connect(tone).connect(fb).connect(delay)
    tone.connect(out)
    graph = { ac, out, echo }
  }
  if (graph.ac.state === 'suspended') void graph.ac.resume()
  return graph
}

interface NoteOpts {
  at?: number
  freq: number
  to?: number
  dur: number
  type?: OscillatorType
  gain?: number
  attack?: number
  /** Low-pass cutoff (Hz); sweeps to cutoffTo over the note if given. */
  cutoff?: number
  cutoffTo?: number
  detune?: number
  echo?: boolean
}

/** One shaped note with optional filter sweep and echo send. */
function note(g: Graph, o: NoteOpts) {
  const { ac } = g
  const start = ac.currentTime + (o.at ?? 0)
  const end = start + o.dur
  const osc = ac.createOscillator()
  osc.type = o.type ?? 'sine'
  osc.frequency.setValueAtTime(o.freq, start)
  if (o.to) osc.frequency.exponentialRampToValueAtTime(o.to, end)
  if (o.detune) osc.detune.value = o.detune
  const amp = ac.createGain()
  const peak = o.gain ?? 0.16
  amp.gain.setValueAtTime(0.0001, start)
  amp.gain.exponentialRampToValueAtTime(peak, start + (o.attack ?? 0.008))
  amp.gain.exponentialRampToValueAtTime(0.0001, end)
  let node: AudioNode = osc
  if (o.cutoff) {
    const f = ac.createBiquadFilter()
    f.type = 'lowpass'
    f.frequency.setValueAtTime(o.cutoff, start)
    if (o.cutoffTo) f.frequency.exponentialRampToValueAtTime(o.cutoffTo, end)
    node = node.connect(f)
  }
  node.connect(amp)
  amp.connect(g.out)
  if (o.echo) amp.connect(g.echo)
  osc.start(start)
  osc.stop(end + 0.05)
}

/** Bell / chime: fundamental plus inharmonic partials, long ring. */
function bell(g: Graph, at: number, freq: number, gain = 0.12, dur = 0.7) {
  note(g, { at, freq, dur, gain, type: 'sine', echo: true })
  note(g, { at, freq: freq * 2.76, dur: dur * 0.5, gain: gain * 0.35, type: 'sine', echo: true })
  note(g, { at, freq: freq * 5.4, dur: dur * 0.25, gain: gain * 0.15, type: 'sine' })
}

function noise(g: Graph, o: { at?: number; dur: number; gain?: number; cutoff: number; cutoffTo?: number; type?: BiquadFilterType }) {
  const { ac } = g
  const start = ac.currentTime + (o.at ?? 0)
  const buffer = ac.createBuffer(1, Math.max(1, Math.floor(ac.sampleRate * o.dur)), ac.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  const src = ac.createBufferSource()
  src.buffer = buffer
  const f = ac.createBiquadFilter()
  f.type = o.type ?? 'lowpass'
  f.frequency.setValueAtTime(o.cutoff, start)
  if (o.cutoffTo) f.frequency.exponentialRampToValueAtTime(o.cutoffTo, start + o.dur)
  const amp = ac.createGain()
  amp.gain.setValueAtTime(o.gain ?? 0.3, start)
  amp.gain.exponentialRampToValueAtTime(0.0001, start + o.dur)
  src.connect(f).connect(amp).connect(g.out)
  src.start(start)
}

/** A handful of tiny high bells at slightly random times: falling coins. */
function coins(g: Graph, at: number, count = 6, gain = 0.07) {
  for (let i = 0; i < count; i++) {
    bell(g, at + i * 0.055 + Math.random() * 0.03, 2200 + Math.random() * 1400, gain, 0.25)
  }
}

const SOUNDS: Record<SoundName, (g: Graph) => void> = {
  // Bright rising arpeggio in C major with coins on top
  win: (g) => {
    ;[523.25, 659.25, 783.99, 1046.5].forEach((f, i) => {
      note(g, { at: i * 0.085, freq: f, dur: 0.32, type: 'triangle', gain: 0.13, echo: true })
      note(g, { at: i * 0.085, freq: f * 2, dur: 0.2, type: 'sine', gain: 0.04 })
    })
    coins(g, 0.32, 5)
  },
  // Fanfare: arpeggio, held major chord, shower of coins
  bigWin: (g) => {
    ;[392, 523.25, 659.25, 783.99, 1046.5].forEach((f, i) => note(g, { at: i * 0.075, freq: f, dur: 0.28, type: 'triangle', gain: 0.12, echo: true }))
    ;[523.25, 659.25, 783.99, 1046.5].forEach((f) => {
      note(g, { at: 0.42, freq: f, dur: 1.1, type: 'sawtooth', gain: 0.045, cutoff: 2600, cutoffTo: 900, attack: 0.03, echo: true })
      note(g, { at: 0.42, freq: f, dur: 1.1, type: 'triangle', gain: 0.07, detune: 6 })
    })
    coins(g, 0.5, 12, 0.06)
  },
  // Soft descending "wah-wah": no harsh edges
  lose: (g) => {
    ;[[392, 370], [349.23, 330], [293.66, 262]].forEach(([f, to], i) =>
      note(g, { at: i * 0.2, freq: f, to, dur: 0.34, type: 'sawtooth', gain: 0.08, cutoff: 1400, cutoffTo: 300, attack: 0.02 }))
    note(g, { at: 0.6, freq: 131, to: 110, dur: 0.6, type: 'triangle', gain: 0.1 })
  },
  // Casino chip landing on felt
  bet: (g) => {
    noise(g, { dur: 0.05, gain: 0.35, cutoff: 6000, cutoffTo: 1500, type: 'bandpass' })
    note(g, { freq: 1800, to: 1200, dur: 0.07, type: 'sine', gain: 0.06 })
    noise(g, { at: 0.06, dur: 0.035, gain: 0.18, cutoff: 5000, type: 'bandpass' })
  },
  gem: (g) => { bell(g, 0, 1318.5, 0.11, 0.55); bell(g, 0.07, 1975.5, 0.07, 0.45) },
  // Deep boom with debris
  bomb: (g) => {
    note(g, { freq: 160, to: 38, dur: 0.75, type: 'sine', gain: 0.45, attack: 0.004 })
    noise(g, { dur: 0.9, gain: 0.5, cutoff: 2400, cutoffTo: 120 })
    noise(g, { at: 0.05, dur: 0.35, gain: 0.15, cutoff: 7000, cutoffTo: 2000, type: 'highpass' })
  },
  cashout: (g) => { coins(g, 0, 8, 0.08); note(g, { freq: 1046.5, dur: 0.25, type: 'triangle', gain: 0.08, echo: true }) },
  tick: (g) => note(g, { freq: 1500, dur: 0.035, type: 'square', gain: 0.025, cutoff: 3000 }),
  // Engine spool-up when the plane starts rolling
  takeoff: (g) => {
    note(g, { freq: 70, to: 160, dur: 1.1, type: 'sawtooth', gain: 0.07, cutoff: 400, cutoffTo: 1600, attack: 0.15 })
    noise(g, { dur: 1.0, gain: 0.08, cutoff: 500, cutoffTo: 2500 })
  },
  // Plane flies away: falling whoosh into a thud
  crash: (g) => {
    noise(g, { dur: 0.7, gain: 0.25, cutoff: 3500, cutoffTo: 200, type: 'bandpass' })
    note(g, { freq: 520, to: 70, dur: 0.7, type: 'sawtooth', gain: 0.07, cutoff: 2000, cutoffTo: 200 })
    note(g, { at: 0.55, freq: 90, to: 40, dur: 0.45, type: 'sine', gain: 0.3 })
  },
}

export function playSound(name: SoundName): void {
  if (muted) return
  try {
    const g = getGraph()
    if (g) SOUNDS[name](g)
  } catch { /* audio is a nicety; never break the game */ }
}

/** Win sound sized to the result: a fanfare for 5x or more. */
export function playWinFor(payoutPaise: number, stakePaise: number): void {
  playSound(stakePaise > 0 && payoutPaise >= stakePaise * 5 ? 'bigWin' : 'win')
}

// ── Aviator engine loop ─────────────────────────────────────────────────────

export interface EngineSound {
  /** Pitch and brightness follow the multiplier. */
  setMultiplier: (m: number) => void
  stop: (crashed: boolean) => void
}

let activeEngine: EngineSound | null = null

/** Continuous propeller/engine drone for a flying round. Returns null when muted. */
export function startEngine(): EngineSound | null {
  if (muted) return null
  activeEngine?.stop(false)
  const g = getGraph()
  if (!g) return null
  const { ac } = g
  const now = ac.currentTime

  const master = ac.createGain()
  master.gain.setValueAtTime(0.0001, now)
  master.gain.exponentialRampToValueAtTime(0.11, now + 0.6)

  const filter = ac.createBiquadFilter()
  filter.type = 'lowpass'
  filter.frequency.value = 500
  filter.Q.value = 3

  // Two detuned saws = engine body, one octave-up square = turbine whine
  const base = 75
  const oscs = [
    Object.assign(ac.createOscillator(), { type: 'sawtooth' as OscillatorType }),
    Object.assign(ac.createOscillator(), { type: 'sawtooth' as OscillatorType }),
    Object.assign(ac.createOscillator(), { type: 'square' as OscillatorType }),
  ]
  oscs[0].frequency.value = base
  oscs[1].frequency.value = base
  oscs[1].detune.value = 14
  oscs[2].frequency.value = base * 2
  const whine = ac.createGain()
  whine.gain.value = 0.25

  // Propeller flutter: amplitude LFO
  const flutter = ac.createOscillator()
  flutter.frequency.value = 18
  const flutterDepth = ac.createGain()
  flutterDepth.gain.value = 0.35
  const body = ac.createGain()
  body.gain.value = 0.65
  flutter.connect(flutterDepth).connect(body.gain)

  oscs[0].connect(filter)
  oscs[1].connect(filter)
  oscs[2].connect(whine).connect(filter)
  filter.connect(body).connect(master).connect(g.out)
  ;[...oscs, flutter].forEach((o) => o.start(now))

  let stopped = false
  const engine: EngineSound = {
    setMultiplier: (m) => {
      if (stopped) return
      const t = ac.currentTime
      const lift = Math.log2(Math.max(1, m)) // 1x=0, 2x=1, 4x=2 ...
      const f = base * (1 + Math.min(lift, 6) * 0.32)
      oscs[0].frequency.setTargetAtTime(f, t, 0.15)
      oscs[1].frequency.setTargetAtTime(f, t, 0.15)
      oscs[2].frequency.setTargetAtTime(f * 2, t, 0.15)
      flutter.frequency.setTargetAtTime(18 + Math.min(lift, 6) * 6, t, 0.2)
      filter.frequency.setTargetAtTime(500 + Math.min(lift, 6) * 380, t, 0.2)
    },
    stop: (crashed) => {
      if (stopped) return
      stopped = true
      const t = ac.currentTime
      master.gain.cancelScheduledValues(t)
      master.gain.setValueAtTime(Math.max(master.gain.value, 0.0001), t)
      master.gain.exponentialRampToValueAtTime(0.0001, t + (crashed ? 0.25 : 0.5))
      ;[...oscs, flutter].forEach((o) => o.stop(t + 0.6))
      if (activeEngine === engine) activeEngine = null
      if (crashed) playSound('crash')
    },
  }
  activeEngine = engine
  return engine
}
