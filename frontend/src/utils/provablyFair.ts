/**
 * Independent, in-browser re-implementation of the server's provably-fair maths
 * (backend: app/utils/rng.py, app/games/wingo/rules.py, app/games/aviator/rules.py).
 * Uses only WebCrypto, so a player never has to trust our API to check a result.
 */

const enc = new TextEncoder()

const toHex = (bytes: ArrayBuffer | Uint8Array) =>
  Array.from(bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes)).map((b) => b.toString(16).padStart(2, '0')).join('')

export async function sha256Hex(text: string): Promise<string> {
  return toHex(await crypto.subtle.digest('SHA-256', enc.encode(text)))
}

/** HMAC-SHA256(key = serverSeed, message = `${clientSeed}:${nonce}`) */
export async function roundHmac(serverSeed: string, clientSeed: string, nonce: number): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey('raw', enc.encode(serverSeed), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'])
  return new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(`${clientSeed}:${nonce}`)))
}

/** First 4 bytes as a big-endian uint32, divided by 2^32 → [0, 1). */
export async function deriveFloat(serverSeed: string, clientSeed: string, nonce: number): Promise<number> {
  const digest = await roundHmac(serverSeed, clientSeed, nonce)
  const uint32 = new DataView(digest.buffer).getUint32(0, false)
  return uint32 / 2 ** 32
}

export const NUMBER_COLOURS = (n: number): string[] =>
  n === 0 ? ['RED', 'VIOLET'] : n === 5 ? ['GREEN', 'VIOLET'] : n % 2 ? ['GREEN'] : ['RED']

/** WinGo: number 0..9 */
export function wingoNumber(r: number): number {
  return Math.min(9, Math.floor(r * 10))
}

/**
 * Aviator crash point ×100 (100 = 1.00x … 10000 = 100.00x), house edge in basis points.
 * formula 1 = rounds before the fix (extra instant-crash rule), 2 = current (edge applied once).
 * Each round stores its version as result.crash_formula (missing = 1).
 */
export function aviatorCrashX100(r: number, houseEdgeBp = 300, formula = 1): number {
  if (formula === 1) {
    const modulus = houseEdgeBp ? Math.floor(10_000 / houseEdgeBp) : 0
    const discrete = Math.trunc(r * 2 ** 32)
    if (modulus && discrete % modulus === 0) return 100
  }
  const safeR = Math.min(r, 1.0 - 1e-9)
  const raw = (10_000 - houseEdgeBp) / (10_000 * (1.0 - safeR)) * 100
  return Math.max(100, Math.min(Math.trunc(raw), 10_000))
}

export interface ManualVerification {
  hashMatches: boolean
  computedHash: string
  float: number
  outcome: string
  details: Record<string, string | number>
}

export async function verifyManually(input: {
  game: 'wingo' | 'aviator'
  serverSeed: string
  serverSeedHash: string
  clientSeed: string
  nonce: number
  houseEdgeBp?: number
  crashFormula?: number
}): Promise<ManualVerification> {
  const computedHash = await sha256Hex(input.serverSeed.trim())
  const r = await deriveFloat(input.serverSeed.trim(), input.clientSeed.trim(), input.nonce)
  const hashMatches = computedHash === input.serverSeedHash.trim().toLowerCase()
  if (input.game === 'wingo') {
    const n = wingoNumber(r)
    return { hashMatches, computedHash, float: r, outcome: `Number ${n}`, details: { number: n, size: n >= 5 ? 'BIG' : 'SMALL', colours: NUMBER_COLOURS(n).join(' + ') } }
  }
  const crash = aviatorCrashX100(r, input.houseEdgeBp ?? 300, input.crashFormula ?? 1)
  return { hashMatches, computedHash, float: r, outcome: `Crash at ${(crash / 100).toFixed(2)}x`, details: { crash_point_x100: crash, crash_point: (crash / 100).toFixed(2) } }
}
