/**
 * After a deploy the page files get new names. A tab opened before the deploy still asks
 * for the old ones, which no longer exist ("Failed to fetch dynamically imported module").
 * Reloading picks up the new version; the timestamp guard stops a reload loop if the
 * server is really broken.
 */
const KEY = 'chunk-reload-at'
const GUARD_MS = 30_000

const CHUNK_ERROR = /failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed|loading (css )?chunk [\w-]+ failed|unable to preload css/i

export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? `${error.name} ${error.message}` : String(error ?? '')
  return CHUNK_ERROR.test(message)
}

/** Reload once to fetch the new version. Returns false when a reload just happened (give up). */
export function reloadForNewVersion(): boolean {
  let last = 0
  try { last = Number(sessionStorage.getItem(KEY) || 0) } catch { /* storage blocked */ }
  if (Date.now() - last < GUARD_MS) return false
  try { sessionStorage.setItem(KEY, String(Date.now())) } catch { /* storage blocked */ }
  window.location.reload()
  return true
}
