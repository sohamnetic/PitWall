import type { PredictionRow } from '../api/types'
import { num } from '../format'
import { teamName } from '../teams'
import { DriverLabel, ProbBar } from './ui'

/** Timing-tower style: position, team stripe + driver, then the three headline chances. */
export default function ProbabilityTable({ rows }: { rows: PredictionRow[] }) {
  const hasActual = rows.some((r) => r.actual_position != null)
  const th = 'eyebrow py-2 font-medium'
  return (
    <div className="-mx-4 overflow-x-auto sm:mx-0">
      <table className="w-full min-w-[540px] text-sm">
        <thead>
          <tr className="border-b border-line text-left">
            <th className={`${th} w-10 pl-4 sm:pl-0`}>Pos</th>
            <th className={`${th} px-2`}>Driver</th>
            <th className={`${th} hidden px-2 xl:table-cell`}>Team</th>
            <th className={`${th} px-2 text-right`}>Win</th>
            <th className={`${th} px-2 text-right`}>Podium</th>
            <th className={`${th} px-2 text-right`}>Points</th>
            <th className={`${th} px-2 text-right`} title="Expected finishing position">Exp.</th>
            {hasActual && <th className={`${th} pl-2 pr-4 text-right sm:pr-0`}>Actual</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => {
            const diff = r.actual_position != null ? r.actual_position - r.pred_rank : null
            return (
              <tr
                key={r.driver.id}
                className={`rise border-b border-line transition-colors last:border-0 hover:bg-hover ${i < 3 ? 'bg-white/[0.02]' : ''}`}
                style={{ animationDelay: `${Math.min(i, 12) * 25}ms` }}
              >
                <td className="display tabular py-2.5 pl-4 text-lg text-ink-2 sm:pl-0">{r.pred_rank}</td>
                <td className="px-2"><DriverLabel driver={r.driver} /></td>
                <td className="hidden whitespace-nowrap px-2 text-ink-2 xl:table-cell">{teamName(r.driver.team_name)}</td>
                <td className="px-2"><ProbBar p={r.p_win} label={`${r.driver.name}: chance to win`} /></td>
                <td className="px-2"><ProbBar p={r.p_podium} label={`${r.driver.name}: chance of a podium`} /></td>
                <td className="px-2"><ProbBar p={r.p_points} label={`${r.driver.name}: chance to score points`} width="w-14" /></td>
                <td className="tabular px-2 text-right text-ink-2">{num(r.expected_pos, 1)}</td>
                {hasActual && (
                  <td className="tabular pl-2 pr-4 text-right sm:pr-0">
                    <span className="display text-base">{r.actual_position ?? '–'}</span>
                    {diff != null && diff !== 0 && (
                      <span className="ml-1 text-xs text-muted">({diff > 0 ? `+${diff}` : diff})</span>
                    )}
                  </td>
                )}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
