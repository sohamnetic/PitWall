import { useState } from 'react'
import type { PredictionRow } from '../api/types'
import { useThemeColors } from '../theme'
import { TooltipPanel } from './ui'
import { num } from '../format'
import { useElementWidth } from './useElementWidth'

const ROW_H = 24
const MARGIN = { top: 24, right: 16, bottom: 8, left: 56 }

/** Dumbbell: expected finishing position before vs after qualifying, per driver. */
export default function PrePostChart({ pre, post }: { pre: PredictionRow[]; post: PredictionRow[] }) {
  const c = useThemeColors()
  const [ref, width] = useElementWidth<HTMLDivElement>()
  const [hover, setHover] = useState<number | null>(null)

  const preById = new Map(pre.map((r) => [r.driver.id, r]))
  const rows = post
    .filter((r) => preById.has(r.driver.id))
    .map((r) => ({ driver: r.driver, post: r.expected_pos, pre: preById.get(r.driver.id)!.expected_pos }))
  const n = Math.max(post.length, pre.length)
  const plotW = Math.max(width - MARGIN.left - MARGIN.right, 100)
  const x = (pos: number) => MARGIN.left + ((pos - 1) / Math.max(n - 1, 1)) * plotW
  const height = MARGIN.top + rows.length * ROW_H + MARGIN.bottom
  const ticks = [1, 5, 10, 15, 20].filter((t) => t <= n)

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-4 text-xs text-ink-2">
        <LegendDot color={c.s1} label="Before qualifying" />
        <LegendDot color={c.s2} label="After qualifying" />
        <span className="text-muted">expected finishing position · left is better</span>
      </div>
      <div ref={ref} className="relative" onMouseLeave={() => setHover(null)}>
        <svg width={width} height={height} role="img" aria-label="Expected finishing position before and after qualifying for each driver">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={MARGIN.top - 6} y2={height - MARGIN.bottom} stroke={c.grid} strokeWidth={1} />
              <text x={x(t)} y={MARGIN.top - 10} textAnchor="middle" fontSize={11} fill={c.muted}>
                P{t}
              </text>
            </g>
          ))}
          {rows.map((r, i) => {
            const y = MARGIN.top + i * ROW_H + ROW_H / 2
            return (
              <g key={r.driver.id} onMouseEnter={() => setHover(i)}>
                <rect x={0} y={y - ROW_H / 2} width={width} height={ROW_H} fill={hover === i ? 'var(--hover)' : 'transparent'} />
                <text x={MARGIN.left - 10} y={y + 4} textAnchor="end" fontSize={12} fontWeight={600} fill={c.ink}>
                  {r.driver.code}
                </text>
                <line x1={x(r.pre)} x2={x(r.post)} y1={y} y2={y} stroke={c.axis} strokeWidth={2} strokeLinecap="round" />
                <circle cx={x(r.pre)} cy={y} r={5} fill={c.s1} stroke={c.card} strokeWidth={2} />
                <circle cx={x(r.post)} cy={y} r={5} fill={c.s2} stroke={c.card} strokeWidth={2} />
              </g>
            )
          })}
        </svg>
        {hover != null && rows[hover] && (
          <div
            className="absolute z-10"
            style={{
              left: Math.min(x(Math.min(rows[hover].pre, rows[hover].post)) + 8, Math.max(width - 220, 0)),
              top: MARGIN.top + (hover + 1) * ROW_H,
            }}
          >
            <TooltipPanel
              title={rows[hover].driver.name}
              rows={[
                { key: c.s1, label: 'before qualifying', value: num(rows[hover].pre, 1) },
                { key: c.s2, label: 'after qualifying', value: num(rows[hover].post, 1) },
              ]}
            />
          </div>
        )}
      </div>
    </div>
  )
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: color }} />
      {label}
    </span>
  )
}
