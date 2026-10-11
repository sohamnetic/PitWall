import { useEffect, useState } from 'react'

function parts(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000))
  return { d: Math.floor(s / 86400), h: Math.floor((s % 86400) / 3600), m: Math.floor((s % 3600) / 60), s: s % 60 }
}

/** Live countdown to a naive-UTC timestamp. Renders nothing once it has passed.
 *  ``variant="hero"`` draws timing-screen digit blocks. */
export default function Countdown({
  to,
  label,
  variant = 'inline',
}: {
  to: string
  label: string
  variant?: 'inline' | 'hero'
}) {
  const target = new Date(to.endsWith('Z') ? to : `${to}Z`).getTime()
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [])
  const left = target - now
  if (left <= 0) return null
  const { d, h, m, s } = parts(left)
  const units: [number, string][] = d > 0 ? [[d, 'days'], [h, 'hrs'], [m, 'min']] : [[h, 'hrs'], [m, 'min'], [s, 'sec']]
  const aria = `${label}: ${d} days ${h} hours ${m} minutes`

  if (variant === 'hero') {
    return (
      <div aria-label={aria}>
        <div className="eyebrow mb-2">{label}</div>
        <div className="flex gap-2">
          {units.map(([v, u]) => (
            <div key={u} className="min-w-16 rounded-xl border border-line-strong bg-black/40 px-3 py-2 text-center">
              <div className="display tabular text-3xl leading-none sm:text-4xl">{String(v).padStart(2, '0')}</div>
              <div className="eyebrow mt-1 text-[0.6rem]">{u}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }
  return (
    <span className="inline-flex items-baseline gap-2" aria-label={aria}>
      <span className="eyebrow">{label}</span>
      <span className="display tabular text-lg">
        {units.map(([v, u]) => (
          <span key={u} className="mr-1.5">
            {String(v).padStart(2, '0')}
            <span className="text-xs font-normal text-ink-2">{u[0]}</span>
          </span>
        ))}
      </span>
    </span>
  )
}
