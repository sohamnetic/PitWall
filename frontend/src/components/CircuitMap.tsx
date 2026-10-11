import circuits from '../data/circuits.json'

interface Outline {
  d: string
  w: number
  h: number
}

// Outlines from github.com/bacinger/f1-circuits (MIT), built by scripts/make_circuits.py.
const MAPS = circuits as Record<string, Outline>

/** A circuit's layout, north up, with an optional car lapping it.
 *  lap: 'always' animates continuously; 'hover' only while a parent `.group` is hovered. */
export default function CircuitMap({
  circuitId,
  color = 'var(--brand-hot)',
  lap,
  label,
  className = '',
}: {
  circuitId: string | null | undefined
  color?: string
  lap?: 'always' | 'hover'
  label?: string
  className?: string
}) {
  const c = circuitId ? MAPS[circuitId] : undefined
  if (!c) return null
  const pad = 6
  const stroke = { fill: 'none', strokeLinejoin: 'round' as const, vectorEffect: 'non-scaling-stroke' as const }
  return (
    <svg
      viewBox={`${-pad} ${-pad} ${c.w + 2 * pad} ${c.h + 2 * pad}`}
      className={className}
      role="img"
      aria-label={label ? `${label} circuit layout` : 'Circuit layout'}
    >
      <path d={c.d} {...stroke} stroke={color} strokeOpacity={0.22} strokeWidth={8} />
      <path d={c.d} {...stroke} stroke="currentColor" strokeOpacity={0.9} strokeWidth={2} />
      {lap && (
        <path
          d={c.d}
          {...stroke}
          pathLength={1000}
          stroke={color}
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray="70 930"
          className={lap === 'hover' ? 'lap lap-hover' : 'lap'}
          style={{ animationDuration: '5s' }}
        />
      )}
    </svg>
  )
}
