/**
 * Server time synchronization helper
 * Calculates the clock drift between client machine and the game server
 */
let serverOffsetMs = 0
let isSynchronized = false

export function setServerTime(serverTimestampMs: number, clientSendTimeMs?: number) {
  const now = Date.now()
  if (clientSendTimeMs) {
    // Round trip time compensation (NTP-style)
    const rtt = Math.max(0, now - clientSendTimeMs)
    serverOffsetMs = serverTimestampMs + rtt / 2 - now
  } else {
    serverOffsetMs = serverTimestampMs - now
  }
  isSynchronized = true
}

export function getSyncedServerTime(): number {
  return Date.now() + serverOffsetMs
}

export function getServerOffset(): number {
  return serverOffsetMs
}

export function isTimeSynced(): boolean {
  return isSynchronized
}
