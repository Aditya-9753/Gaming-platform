import React from 'react'
import { Link } from 'react-router-dom'
import { Home, Compass } from 'lucide-react'
import { Button } from '../../components/common/Button'
import { t as tr } from '../../i18n'

export const NotFound: React.FC = () => {
  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center text-center p-6 space-y-4">
      <div className="w-16 h-16 rounded-3xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
        <Compass className="w-8 h-8" />
      </div>
      <h1 className="text-4xl font-black text-white">404</h1>
      <h3 className="text-lg font-bold text-slate-300">{tr('Page Not Found')}</h3>
      <p className="text-xs text-slate-500 max-w-sm">
        {tr("The page you are looking for doesn't exist or has been moved.")}
      </p>
      <Link to="/">
        <Button variant="primary" size="sm" leftIcon={<Home className="w-4 h-4" />}>
          {tr('Back to Home')}
        </Button>
      </Link>
    </div>
  )
}

