/**
 * Read-only "view as partner" token. Kept only in memory (never localStorage / sessionStorage),
 * so no script or later visitor can read it from storage; reloading the tab ends the view.
 */
let token: string | null = null

export const impersonation = {
  get: (): string | null => token,
  set: (value: string) => { token = value },
  clear: () => { token = null },
  active: (): boolean => token !== null,
}
