import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

/** Standard page top: title on the left, actions on the right. */
export function PageHeader({ title, description, actions }: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-gray-400">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Raised surface panel — the one card treatment used everywhere. */
export function Card({ className = '', children }: { className?: string; children: ReactNode }) {
  return (
    <div className={`bg-gray-800 border border-gray-700 rounded-lg ${className}`}>
      {children}
    </div>
  )
}

/** Empty list/table state: names the situation and points at the next action. */
export function EmptyState({ icon: Icon, title, hint, action }: {
  icon?: LucideIcon
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      {Icon && <Icon className="w-8 h-8 text-gray-600" aria-hidden />}
      <div className="text-sm font-medium text-gray-300">{title}</div>
      {hint && <div className="text-sm text-gray-500 max-w-sm">{hint}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
