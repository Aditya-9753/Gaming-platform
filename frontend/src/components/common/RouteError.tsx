import React, { useEffect, useState } from 'react'
import { useRouteError } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { isChunkLoadError, reloadForNewVersion } from '../../utils/chunkReload'

/** Router error screen: a new deploy reloads itself; anything else gets a plain message and a reload button. */
export const RouteError: React.FC = () => {
  const error = useRouteError()
  const chunk = isChunkLoadError(error)
  const [reloading, setReloading] = useState(chunk)

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- the reload is a side effect; show the button only if it was refused
    if (chunk && !reloadForNewVersion()) setReloading(false)
  }, [chunk])

  return (
    <div className="flex min-h-screen items-center justify-center bg-dark-bg p-6">
      <div className="max-w-sm space-y-4 rounded-2xl border border-dark-border bg-dark-card p-6 text-center shadow-2xl">
        <h1 className="text-lg font-black text-white">{reloading ? 'Updating to the latest version…' : chunk ? 'A new version is available' : 'Something went wrong'}</h1>
        <p className="text-sm text-slate-400">
          {reloading ? 'One moment, the page reloads by itself.'
            : chunk ? 'The site was just updated. Reload the page to continue.'
              : 'This page could not be shown. Reload the page; if it keeps happening, contact support.'}
        </p>
        {!reloading && (
          <button type="button" onClick={() => window.location.reload()}
            className="inline-flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-blue-500">
            <RefreshCw className="h-4 w-4" />Reload
          </button>
        )}
      </div>
    </div>
  )
}
