import { useRef, useState } from 'react'
import type { PredictionRow } from '../api/types'
import { seqFill } from '../theme'
import { Segmented, TooltipPanel } from './ui'
import { chance } from '../format'

const LABEL_MIN = 0.2 // label only the cells that matter; the rest live in tooltip + table

interface Hover {
  row: PredictionRow
  pos: number
  x: number
  y: number
}

/** Driver x finishing position probability grid (sequential, single hue). */
export default function PositionHeatmap({ rows }: { rows: PredictionRow[] }) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const [hover, setHover] = useState<Hover | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const onCell = (row: PredictionRow, pos: number, clientX: number, clientY: number) => {
    const box = boxRef.current
    if (!box) return
    const rect = box.getBoundingClientRect()
    const x = clientX - rect.left + box.scrollLeft
    // Flip to the left of the pointer near the right edge so the tooltip stays visible.
    const flip = clientX - rect.left > rect.width - 220
    setHover({ row, pos, x: flip ? x - 220 : x + 12, y: clientY - rect.top + 12 })
  }
  const n = rows[0]?.position_probs.length ?? 0
  const positions = Array.from({ length: n }, (_, i) => i + 1)
  const hasActual = rows.some((r) => r.actual_position != null)

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <Legend hasActual={hasActual} />
        <Segmented
          label="Heatmap view"
          value={view}
          onChange={setView}
          options={[
            { value: 'chart', label: 'Chart' },
            { value: 'table', label: 'Table' },
          ]}
        />
      </div>

      {view === 'table' ? (
        <div className="overflow-x-auto">
          <table className="tabular text-xs">
            <thead>
              <tr className="text-ink-2">
                <th className="sticky left-0 bg-card px-2 py-1 text-left font-medium">Driver</th>
                {positions.map((p) => (
                  <th key={p} className="px-1.5 py-1 text-right font-medium">P{p}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.driver.id} className="border-t border-line">
                  <td className="sticky left-0 bg-card px-2 py-1 font-semibold">{r.driver.code}</td>
                  {r.position_probs.map((p, i) => (
                    <td key={i} className="px-1.5 py-1 text-right text-ink">
                      {p >= 0.005 ? chance(p) : <span className="text-muted">&lt;1</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div ref={boxRef} className="relative overflow-x-auto" onMouseLeave={() => setHover(null)}>
          <div
            role="img"
            aria-label="Probability of each driver finishing in each position. Use the table view for exact values."
            className="grid min-w-[640px] gap-[2px] bg-card text-xs"
            style={{ gridTemplateColumns: `3.25rem repeat(${n}, minmax(1.5rem, 1fr))` }}
          >
            <div />
            {positions.map((p) => (
              <div key={p} className="tabular pb-1 text-center text-muted">
                {p}
              </div>
            ))}
            {rows.map((r) => (
              <Row key={r.driver.id} row={r} onCell={onCell} />
            ))}
          </div>
          {hover && (
            <div
              className="absolute z-10"
              style={{ left: hover.x, top: hover.y }}
            >
              <TooltipPanel
                title={`${hover.row.driver.name} · P${hover.pos}`}
                rows={[
                  { label: `chance to finish P${hover.pos}`, value: chance(hover.row.position_probs[hover.pos - 1], 1) },
                  ...(hover.row.actual_position === hover.pos ? [{ label: 'actual finish', value: '✓' }] : []),
                ]}
              />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Row({
  row,
  onCell,
}: {
  row: PredictionRow
  onCell: (row: PredictionRow, pos: number, clientX: number, clientY: number) => void
}) {
  return (
    <>
      <div className="flex items-center pr-2 font-semibold text-ink">{row.driver.code}</div>
      {row.position_probs.map((p, i) => {
        const pos = i + 1
        const actual = row.actual_position === pos
        return (
          <div
            key={i}
            onMouseMove={(e) => onCell(row, pos, e.clientX, e.clientY)}
            className="tabular flex h-6 items-center justify-center rounded-[3px] hover:brightness-110"
            style={{
              background: seqFill(p),
              color: 'var(--ink)', // ink clears contrast on every step of the ramp, both modes
              boxShadow: actual ? 'inset 0 0 0 2px var(--ink)' : undefined,
            }}
          >
            {p >= LABEL_MIN ? Math.round(p * 100) : ''}
          </div>
        )
      })}
    </>
  )
}

function Legend({ hasActual }: { hasActual: boolean }) {
  const stops = [0, 0.05, 0.15, 0.3, 0.5, 0.75, 1].map((p) => `${seqFill(p)} ${Math.sqrt(p) * 100}%`)
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs text-ink-2">
      <div className="flex items-center gap-2">
        <span>0%</span>
        <span className="h-2.5 w-32 rounded-sm" style={{ background: `linear-gradient(to right, ${stops.join(', ')})` }} />
        <span>100%</span>
        <span className="text-muted">chance of finishing in that position · numbers are %</span>
      </div>
      <span className="w-full text-muted">
        Nothing is ruled out: a dark cell means fewer than 1 in 200 simulated races ended that way.
      </span>
      {hasActual && (
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-[3px]" style={{ boxShadow: 'inset 0 0 0 2px var(--ink)' }} />
          actual finish
        </div>
      )}
    </div>
  )
}
