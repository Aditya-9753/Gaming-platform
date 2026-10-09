/**
 * Game sound effects, synthesised with the Web Audio API (no audio files to download).
 *
 * Everything goes through one master chain (gain -> compressor -> speakers) with a
 * short echo send, so effects sound full without clipping. Browsers only allow audio
 * after a user gesture; the context is created/resumed lazily. Sounds can be muted
 * from the header; the choice is remembered per browser.
 */

export type SoundName =
  | 'win' | 'bigWin' | 'lose' | 'bet' | 'gem' | 'bomb' | 'cashout' | 'tick' | 'takeoff' | 'crash' | 'roundOpen' | 'countdown'

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
  // Jet spool-up when the plane starts rolling: rising turbine plus a rush of air
  takeoff: (g) => {
    note(g, { freq: 180, to: 620, dur: 1.3, type: 'triangle', gain: 0.05, cutoff: 900, cutoffTo: 3200, attack: 0.25 })
    note(g, { freq: 55, to: 82, dur: 1.2, type: 'sine', gain: 0.16, attack: 0.2 })
    noise(g, { dur: 1.3, gain: 0.12, cutoff: 400, cutoffTo: 3000, type: 'bandpass' })
  },
  // Plane flies away: a Doppler drop as it passes and vanishes, then a distant rumble
  crash: (g) => {
    noise(g, { dur: 0.9, gain: 0.3, cutoff: 4200, cutoffTo: 180, type: 'bandpass' })
    note(g, { freq: 980, to: 140, dur: 0.8, type: 'triangle', gain: 0.08, cutoff: 3000, cutoffTo: 300, echo: true })
    note(g, { freq: 1320, to: 210, dur: 0.75, type: 'sine', gain: 0.04 })
    note(g, { at: 0.5, freq: 70, to: 34, dur: 0.9, type: 'sine', gain: 0.28 })
    noise(g, { at: 0.5, dur: 0.9, gain: 0.12, cutoff: 260, cutoffTo: 60 })
  },
  // New round: two soft rising chimes ("place your bets")
  roundOpen: (g) => { bell(g, 0, 880, 0.08, 0.5); bell(g, 0.12, 1318.5, 0.07, 0.6) },
  // Last seconds of betting: a short wooden tick
  countdown: (g) => {
    note(g, { freq: 1046.5, dur: 0.06, type: 'triangle', gain: 0.07 })
    noise(g, { dur: 0.03, gain: 0.08, cutoff: 3500, type: 'bandpass' })
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

/** Looping white-noise source (for the rush of air around the plane). */
function noiseLoop(ac: AudioContext): AudioBufferSourceNode {
  const buffer = ac.createBuffer(1, ac.sampleRate * 2, ac.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  const src = ac.createBufferSource()
  src.buffer = buffer
  src.loop = true
  return src
}

/**
 * Jet engine for a flying round. Returns null when muted.
 *  - air rush: looping noise through a band-pass that opens up as the plane climbs
 *  - turbine: a soft triangle + sine pair whose pitch rises with the multiplier
 *  - rumble: a low sine body, with a slow vibrato so it never sounds static
 */
export function startEngine(): EngineSound | null {
  if (muted) return null
  activeEngine?.stop(false)
  const g = getGraph()
  if (!g) return null
  const { ac } = g
  const now = ac.currentTime

  const master = ac.createGain()
  master.gain.setValueAtTime(0.0001, now)
  master.gain.exponentialRampToValueAtTime(0.16, now + 0.9)
  master.connect(g.out)

  // Air rush
  const air = noiseLoop(ac)
  const airBand = ac.createBiquadFilter()
  airBand.type = 'bandpass'
  airBand.frequency.value = 700
  airBand.Q.value = 0.7
  const airGain = ac.createGain()
  airGain.gain.value = 0.55
  air.connect(airBand).connect(airGain).connect(master)

  // Turbine whine (soft waveforms: no harsh buzz)
  const turbine = ac.createOscillator()
  turbine.type = 'triangle'
  turbine.frequency.value = 220
  const turbine2 = ac.createOscillator()
  turbine2.type = 'sine'
  turbine2.frequency.value = 330
  const turbineGain = ac.createGain()
  turbineGain.gain.value = 0.12
  const turbineTone = ac.createBiquadFilter()
  turbineTone.type = 'lowpass'
  turbineTone.frequency.value = 1400
  turbine.connect(turbineTone)
  turbine2.connect(turbineTone)
  turbineTone.connect(turbineGain).connect(master)

  // Rumble with a slow vibrato
  const rumble = ac.createOscillator()
  rumble.type = 'sine'
  rumble.frequency.value = 58
  const rumbleGain = ac.createGain()
  rumbleGain.gain.value = 0.5
  rumble.connect(rumbleGain).connect(master)
  const vibrato = ac.createOscillator()
  vibrato.frequency.value = 5.5
  const vibratoDepth = ac.createGain()
  vibratoDepth.gain.value = 6
  vibrato.connect(vibratoDepth)
  vibratoDepth.connect(turbine.frequency)
  vibratoDepth.connect(turbine2.frequency)

  const sources: Array<AudioScheduledSourceNode> = [air, turbine, turbine2, rumble, vibrato]
  sources.forEach((o) => o.start(now))

  let stopped = false
  const engine: EngineSound = {
    setMultiplier: (m) => {
      if (stopped) return
      const t = ac.currentTime
      const lift = Math.min(Math.log2(Math.max(1, m)), 7) // 1x=0, 2x=1, 4x=2 ... capped
      turbine.frequency.setTargetAtTime(220 * (1 + lift * 0.28), t, 0.25)
      turbine2.frequency.setTargetAtTime(330 * (1 + lift * 0.28), t, 0.25)
      turbineTone.frequency.setTargetAtTime(1400 + lift * 450, t, 0.3)
      airBand.frequency.setTargetAtTime(700 + lift * 520, t, 0.3)
      airGain.gain.setTargetAtTime(0.55 + lift * 0.06, t, 0.4)
      rumble.frequency.setTargetAtTime(58 + lift * 6, t, 0.3)
      vibrato.frequency.setTargetAtTime(5.5 + lift * 0.8, t, 0.4)
    },
    stop: (crashed) => {
      if (stopped) return
      stopped = true
      const t = ac.currentTime
      master.gain.cancelScheduledValues(t)
      master.gain.setValueAtTime(Math.max(master.gain.value, 0.0001), t)
      master.gain.exponentialRampToValueAtTime(0.0001, t + (crashed ? 0.3 : 0.6))
      sources.forEach((o) => o.stop(t + 0.7))
      if (activeEngine === engine) activeEngine = null
      if (crashed) playSound('crash')
    },
  }
  activeEngine = engine
  return engine
}

/** Multipliers that ring a milestone chime while the plane climbs. */
export const AVIATOR_MILESTONES = [2, 5, 10, 20, 50, 100]

/** Rising chime for passing 2x, 5x, 10x ... (higher milestones ring brighter). */
export function playMilestone(multiplier: number): void {
  if (muted) return
  try {
    const g = getGraph()
    if (!g) return
    const step = Math.max(0, AVIATOR_MILESTONES.indexOf(multiplier))
    const root = 659.25 * Math.pow(1.122, step)
    bell(g, 0, root, 0.07, 0.45)
    bell(g, 0.08, root * 1.5, 0.06, 0.55)
    if (step >= 2) coins(g, 0.15, 3 + step, 0.05)
  } catch { /* audio is a nicety */ }
}

/** Cash-out "ka-ching": pitch rises with the multiplier the player took. */
export function playCashout(multiplier: number): void {
  if (muted) return
  try {
    const g = getGraph()
    if (!g) return
    const lift = Math.min(Math.log2(Math.max(1, multiplier)), 6)
    const root = 784 * Math.pow(2, lift / 12)
    note(g, { freq: root, dur: 0.18, type: 'triangle', gain: 0.1, echo: true })
    note(g, { at: 0.09, freq: root * 1.5, dur: 0.35, type: 'triangle', gain: 0.1, echo: true })
    coins(g, 0.12, 6 + Math.round(lift * 2), 0.07)
  } catch { /* audio is a nicety */ }
}
