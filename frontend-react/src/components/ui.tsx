import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Loader2, X, type LucideIcon } from 'lucide-react'
import {
  buttonClasses, BANNER_TONES, PILL_TONES,
  type BannerTone, type ButtonSize, type ButtonVariant, type PillTone,
} from './styles'

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

/** The one loading treatment: centered spinner, optional label. */
export function LoadingState({ label = 'Loading...', className = '' }: { label?: string; className?: string }) {
  return (
    <div className={`flex items-center justify-center gap-2 py-8 text-sm text-gray-500 ${className}`}>
      <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
      {label}
    </div>
  )
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  /** Optional leading icon, rendered at the standard control size. */
  icon?: LucideIcon
}

/** The one button. Variants keep the accent scarce: only `primary` is pink. */
export function Button({ variant = 'secondary', size = 'md', icon: Icon, className = '', type = 'button', children, ...props }: ButtonProps) {
  return (
    <button type={type} className={buttonClasses(variant, size, className)} {...props}>
      {Icon && <Icon className="w-4 h-4 shrink-0" aria-hidden />}
      {children}
    </button>
  )
}

/** Tone-tinted status pill. Pass backend status strings through untouched. */
export function StatusPill({ tone = 'neutral', className = '', children }: {
  tone?: PillTone
  className?: string
  children: ReactNode
}) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium whitespace-nowrap ${PILL_TONES[tone]} ${className}`}>
      {children}
    </span>
  )
}

/** Tone-styled result/error banner — replaces ad-hoc emoji-prefixed text banners. */
export function ResultBanner({ tone, className = '', onDismiss, children }: {
  tone: BannerTone
  className?: string
  onDismiss?: () => void
  children: ReactNode
}) {
  const { icon: Icon, classes, spin } = BANNER_TONES[tone]
  return (
    <div className={`p-3 border rounded-lg flex items-start gap-2.5 text-sm ${classes} ${className}`}>
      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${spin ? 'animate-spin' : ''}`} aria-hidden />
      <div className="flex-1 min-w-0">{children}</div>
      {onDismiss && (
        <button onClick={onDismiss} aria-label="Dismiss message" className="shrink-0 mt-0.5 text-gray-400 hover:text-gray-200 transition-colors">
          <X className="w-4 h-4" />
        </button>
      )}
    </div>
  )
}
