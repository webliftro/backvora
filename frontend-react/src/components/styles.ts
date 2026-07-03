import { AlertCircle, AlertTriangle, CheckCircle2, Info, Loader2, type LucideIcon } from 'lucide-react'

// Shared class/tone vocabulary for the ui.tsx primitives. Lives outside
// ui.tsx so that file only exports components (react-refresh constraint).

/** The one treatment for filter-bar / toolbar inputs and selects. */
export const filterFieldClass = 'px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-pink-500'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'xs' | 'sm' | 'md'

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-pink-600 hover:bg-pink-700 active:bg-pink-800 text-white font-medium',
  secondary: 'bg-gray-700 hover:bg-gray-600 active:bg-gray-600 text-gray-100',
  ghost: 'text-gray-400 hover:text-gray-100 hover:bg-gray-700/50',
  danger: 'bg-red-600 hover:bg-red-700 active:bg-red-700 text-white font-medium',
}

const BUTTON_SIZES: Record<ButtonSize, string> = {
  xs: 'px-2 py-1 text-xs rounded',
  sm: 'px-3 py-1 text-sm rounded-md',
  md: 'px-4 py-2 text-sm rounded-lg',
}

/**
 * The shared button treatment as a class string — for `<Link>`s and other
 * elements that must look like a Button but aren't a `<button>`.
 */
export function buttonClasses(variant: ButtonVariant = 'secondary', size: ButtonSize = 'md', className = ''): string {
  return `inline-flex items-center justify-center gap-1.5 transition-colors select-none active:translate-y-px disabled:opacity-50 disabled:pointer-events-none disabled:active:translate-y-0 ${BUTTON_VARIANTS[variant]} ${BUTTON_SIZES[size]} ${className}`
}

export type PillTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'brand'

export const PILL_TONES: Record<PillTone, string> = {
  success: 'bg-green-600/15 text-green-400 border-green-600/30',
  warning: 'bg-yellow-600/15 text-yellow-400 border-yellow-600/30',
  danger: 'bg-red-600/15 text-red-400 border-red-600/30',
  info: 'bg-blue-600/15 text-blue-400 border-blue-600/30',
  neutral: 'bg-gray-600/25 text-gray-300 border-gray-600/40',
  brand: 'bg-pink-600/15 text-pink-400 border-pink-600/30',
}

/**
 * The one place backend status strings map to pill tones. Strings are styled
 * by value only — never renamed or remapped before display.
 */
const STATUS_TONES: Record<string, PillTone> = {
  // Domain statuses
  new: 'neutral',
  analyzing: 'brand',
  analyzed: 'brand',
  contacted: 'warning',
  replied: 'success',
  negotiating: 'warning',
  deal_closed: 'success',
  blacklisted: 'danger',
  // Campaign statuses
  active: 'success',
  paused: 'warning',
  completed: 'neutral',
  // Order statuses
  draft: 'neutral',
  content_ready: 'info',
  pending_review: 'warning',
  sent: 'warning',
  payment_sent: 'info',
  paid: 'info',
  published: 'success',
  live: 'success',
  offline: 'danger',
  monitored: 'info',
  // Shared
  rejected: 'danger',
}

export function statusTone(status?: string | null): PillTone {
  return STATUS_TONES[(status || '').toLowerCase()] || 'neutral'
}

export type BannerTone = 'success' | 'error' | 'warning' | 'info' | 'progress'

export const BANNER_TONES: Record<BannerTone, { icon: LucideIcon; classes: string; spin?: boolean }> = {
  success: { icon: CheckCircle2, classes: 'bg-green-900/30 border-green-700 text-green-300' },
  error: { icon: AlertCircle, classes: 'bg-red-900/30 border-red-700 text-red-300' },
  warning: { icon: AlertTriangle, classes: 'bg-yellow-900/30 border-yellow-700 text-yellow-300' },
  info: { icon: Info, classes: 'bg-blue-900/30 border-blue-700 text-blue-300' },
  progress: { icon: Loader2, classes: 'bg-gray-800 border-gray-700 text-gray-300', spin: true },
}
