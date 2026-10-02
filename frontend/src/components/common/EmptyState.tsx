import React from 'react'
import { FolderOpen } from 'lucide-react'

export interface EmptyStateProps {
  icon?: React.ReactNode
  title: string
  description?: string
  action?: React.ReactNode
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
}) => {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center space-y-3">
      <div className="w-12 h-12 rounded-2xl bg-dark-elevated border border-dark-border flex items-center justify-center text-slate-500">
        {icon || <FolderOpen className="w-6 h-6" />}
      </div>
      <div>
        <h4 className="text-sm font-bold text-slate-200">{title}</h4>
        {description && <p className="text-xs text-slate-500 mt-1 max-w-sm">{description}</p>}
      </div>
      {action && <div className="pt-2">{action}</div>}
    </div>
  )
}

