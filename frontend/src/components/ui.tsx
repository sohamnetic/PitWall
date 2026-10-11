import type { ReactNode } from 'react'
import { Link } from 'react-router'
import type { DriverRef } from '../api/types'
import { pct } from '../format'
import { teamColor } from '../teams'

// ---------------------------------------------------------------- layout

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions,
}: {
  eyebrow?: ReactNode
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <header className="rise flex flex-wrap items-end justify-between gap-4">
      <div>
        {eyebrow && <div className="eyebrow mb-1 flex items-center gap-2">{eyebrow}</div>}
        <h1 className="display text-3xl uppercase sm:text-5xl">{title}</h1>
        {subtitle && <p className="mt-2 max-w-2xl text-ink-2">{subtitle}</p>}
      </div>
      {actions}
    </header>
  )
}

export function Card({
  title,
  eyebrow,
  subtitle,
  actions,
  children,
  className = '',
}: {
  title?: ReactNode
  eyebrow?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <section className={`panel rise p-4 sm:p-6 ${className}`}>
      {(title || actions || eyebrow) && (
        <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
          <div>
            {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
            {title && <h2 className="display text-xl text-ink sm:text-2xl">{title}</h2>}
            {subtitle && <p className="mt-1 text-sm text-ink-2">{subtitle}</p>}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function StatTile({
  label,
  value,
  detail,
  accent,
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  accent?: string
}) {
  return (
    <div className="panel rise relative overflow-hidden px-4 py-3 sm:px-5 sm:py-4">
      {accent && <span className="absolute inset-y-0 left-0 w-1" style={{ background: accent }} aria-hidden />}
      <div className="eyebrow">{label}</div>
      <div className="display mt-1 text-2xl text-ink sm:text-3xl">{value}</div>
      {detail && <div className="mt-1 text-sm text-ink-2">{detail}</div>}
    </div>
  )
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: { value: T; label: string; disabled?: boolean }[]
  onChange: (v: T) => void
  label: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-full border border-line bg-card p-1">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          disabled={o.disabled}
          onClick={() => onChange(o.value)}
          className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
            value === o.value ? 'bg-brand text-white shadow-[0_0_20px_-4px_rgba(225,6,0,0.7)]' : 'text-ink-2 hover:text-ink'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'good' | 'warn' | 'live' }) {
  const tones = {
    neutral: 'border-line-strong text-ink-2',
    good: 'border-good/40 text-good',
    warn: 'border-critical/40 text-critical',
    live: 'border-brand/50 bg-brand/10 text-ink',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}>
      {tone === 'live' && <span className="live-dot h-1.5 w-1.5 rounded-full bg-brand-hot" aria-hidden />}
      {children}
    </span>
  )
}

export function ButtonLink({
  to,
  children,
  variant = 'secondary',
}: {
  to: string
  children: ReactNode
  variant?: 'primary' | 'secondary'
}) {
  return (
    <Link
      to={to}
      className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition-all ${
        variant === 'primary'
          ? 'bg-brand text-white shadow-[0_8px_24px_-8px_rgba(225,6,0,0.8)] hover:bg-brand-hot'
          : 'border border-line-strong text-ink hover:border-ink-2 hover:bg-hover'
      }`}
    >
      {children}
    </Link>
  )
}

/** Team identity stripe: a thin bar in the team's colour. Always shown beside the name. */
export function TeamStripe({ teamId, className = 'h-5' }: { teamId: string | null | undefined; className?: string }) {
  return <span className={`inline-block w-1 shrink-0 rounded-full ${className}`} style={{ background: teamColor(teamId) }} aria-hidden />
}

/** Driver code + name with the team stripe, as on a timing tower. */
export function DriverLabel({ driver, showName = true, link = true }: { driver: DriverRef; showName?: boolean; link?: boolean }) {
  const inner = (
    <span className="inline-flex items-center gap-2.5">
      <TeamStripe teamId={driver.team_id} />
      <span className="display w-10 text-base">{driver.code}</span>
      {showName && <span className="hidden whitespace-nowrap text-ink-2 sm:inline">{driver.name}</span>}
    </span>
  )
  return link ? (
    <Link to={`/drivers/${driver.id}`} className="hover:text-white">
      {inner}
    </Link>
  ) : (
    inner
  )
}

export function Loading({ what = 'data' }: { what?: string }) {
  return (
    <div role="status" aria-live="polite" className="space-y-4 py-2">
      <span className="sr-only">Loading {what}…</span>
      <div className="h-9 w-2/3 max-w-md animate-pulse rounded-lg bg-hover" />
      <div className="h-4 w-1/2 max-w-xs animate-pulse rounded bg-hover" />
      <div className="grid gap-4 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="panel h-24 animate-pulse" />
        ))}
      </div>
      <div className="panel h-72 animate-pulse" />
    </div>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : String(error)
  return (
    <div className="panel border-critical/40 p-4 text-sm">
      <p className="font-semibold text-critical">Couldn't load this.</p>
      <p className="mt-1 text-ink-2">
        {msg}. Is the API running? Start it with <code>uvicorn f1p.api.main:app --app-dir backend</code>.
      </p>
    </div>
  )
}

/** Probability bar for table cells (single series, slot 1); fills in on arrival. */
export function ProbBar({ p, label, width = 'w-20' }: { p: number; label: string; width?: string }) {
  return (
    <div className="flex items-center justify-end gap-2.5" title={label}>
      <span className="tabular w-10 text-right font-medium text-ink">{pct(p)}</span>
      <span className={`hidden h-1.5 ${width} overflow-hidden rounded-full bg-white/[0.06] sm:block`} aria-hidden>
        <span className="fill block h-1.5 rounded-full bg-s1" style={{ width: `${Math.max(p * 100, 0)}%` }} />
      </span>
    </div>
  )
}

/** Chart tooltip panel: value leads, label follows; series keyed by a short line. */
export function TooltipPanel({
  title,
  rows,
}: {
  title?: string
  rows: { key?: string; label: string; value: string }[]
}) {
  return (
    <div className="pointer-events-none rounded-xl border border-line-strong bg-card-2/95 px-3 py-2 text-sm shadow-2xl backdrop-blur">
      {title && <div className="mb-1 font-semibold text-ink">{title}</div>}
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2">
          {r.key && <span className="h-0.5 w-3 rounded" style={{ background: r.key }} />}
          <span className="tabular font-semibold text-ink">{r.value}</span>
          <span className="text-ink-2">{r.label}</span>
        </div>
      ))}
    </div>
  )
}
