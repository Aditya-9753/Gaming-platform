/**
 * Game sound effects, synthesised with the Web Audio API (no audio files to download).
 *
 * Browsers only allow audio after a user gesture; the context is created/resumed lazily
 * on the first play() after a tap or click. Sounds can be muted from the header; the
 * choice is remembered per browser.
 */

export type SoundName = 'win' | 'bigWin' | 'lose' | 'bet' | 'gem' | 'bomb' | 'cashout' | 'tick'

const STORAGE_KEY = 'rudra247.sound.muted'
let ctx: AudioContext | null = null
let muted = readMuted()
const listeners = new Set<(muted: boolean) => void>()

function readMuted(): boolean {
  try { return localStorage.getItem(STORAGE_KEY) === '1' } catch { return false }
}

export function isMuted(): boolean { return muted }

export function setMuted(value: boolean): void {
  muted = value
  try { localStorage.setItem(STORAGE_KEY, value ? '1' : '0') } catch { /* private mode */ }
  listeners.forEach((fn) => fn(value))
}

export function onMutedChange(fn: (muted: boolean) => void): () => void {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

function audio(): AudioContext | null {
  if (typeof window === 'undefined') return null
  const Ctor = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
  if (!Ctor) return null
  if (!ctx) ctx = new Ctor()
  if (ctx.state === 'suspended') void ctx.resume()
  return ctx
}

/** One shaped note: frequency glide, attack/decay envelope. */
function tone(ac: AudioContext, opts: { at: number; freq: number; to?: number; dur: number; type?: OscillatorType; gain?: number }) {
  const osc = ac.createOscillator()
  const amp = ac.createGain()
  const start = ac.currentTime + opts.at
  const peak = opts.gain ?? 0.18
  osc.type = opts.type ?? 'sine'
  osc.frequency.setValueAtTime(opts.freq, start)
  if (opts.to) osc.frequency.exponentialRampToValueAtTime(opts.to, start + opts.dur)
  amp.gain.setValueAtTime(0.0001, start)
  amp.gain.exponentialRampToValueAtTime(peak, start + 0.015)
  amp.gain.exponentialRampToValueAtTime(0.0001, start + opts.dur)
  osc.connect(amp).connect(ac.destination)
  osc.start(start)
  osc.stop(start + opts.dur + 0.02)
}

function noiseBurst(ac: AudioContext, at: number, dur: number, gain = 0.25) {
  const buffer = ac.createBuffer(1, Math.floor(ac.sampleRate * dur), ac.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length) ** 2
  const src = ac.createBufferSource()
  const filter = ac.createBiquadFilter()
  const amp = ac.createGain()
  filter.type = 'lowpass'
  filter.frequency.value = 900
  amp.gain.value = gain
  src.buffer = buffer
  src.connect(filter).connect(amp).connect(ac.destination)
  src.start(ac.currentTime + at)
}

const SOUNDS: Record<SoundName, (ac: AudioContext) => void> = {
  // Rising major arpeggio
  win: (ac) => [523, 659, 784, 1047].forEach((f, i) => tone(ac, { at: i * 0.09, freq: f, dur: 0.22, type: 'triangle' })),
  // Longer fanfare with a sparkle on top
  bigWin: (ac) => {
    [523, 659, 784, 1047, 1319].forEach((f, i) => tone(ac, { at: i * 0.08, freq: f, dur: 0.3, type: 'triangle', gain: 0.2 }))
    ;[1568, 2093, 2637].forEach((f, i) => tone(ac, { at: 0.45 + i * 0.07, freq: f, dur: 0.18, type: 'sine', gain: 0.08 }))
  },
  // Falling minor phrase
  lose: (ac) => [392, 330, 262].forEach((f, i) => tone(ac, { at: i * 0.14, freq: f, to: f * 0.94, dur: 0.28, type: 'sawtooth', gain: 0.07 })),
  bet: (ac) => tone(ac, { at: 0, freq: 880, to: 1320, dur: 0.08, type: 'square', gain: 0.05 }),
  gem: (ac) => { tone(ac, { at: 0, freq: 1319, dur: 0.12, type: 'sine', gain: 0.14 }); tone(ac, { at: 0.06, freq: 1976, dur: 0.16, type: 'sine', gain: 0.09 }) },
  bomb: (ac) => { noiseBurst(ac, 0, 0.6, 0.35); tone(ac, { at: 0, freq: 140, to: 40, dur: 0.5, type: 'sine', gain: 0.3 }) },
  cashout: (ac) => [988, 1319].forEach((f, i) => tone(ac, { at: i * 0.07, freq: f, dur: 0.14, type: 'triangle', gain: 0.15 })),
  tick: (ac) => tone(ac, { at: 0, freq: 1200, dur: 0.03, type: 'square', gain: 0.03 }),
}

export function playSound(name: SoundName): void {
  if (muted) return
  try {
    const ac = audio()
    if (ac) SOUNDS[name](ac)
  } catch { /* audio is a nicety; never break the game */ }
}

/** Win sound sized to the result: a fanfare for 5x or more. */
export function playWinFor(payoutPaise: number, stakePaise: number): void {
  playSound(stakePaise > 0 && payoutPaise >= stakePaise * 5 ? 'bigWin' : 'win')
}
