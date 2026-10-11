import { Link, useParams } from 'react-router'
import { usePageTitle } from '../usePageTitle'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { isNotFound, useDriver } from '../api/hooks'
import type { DriverResult } from '../api/types'
import { Card, ErrorState, Loading, StatTile, TooltipPanel } from '../components/ui'
import { STAGE_LABEL, num, pct } from '../format'
import { teamColor, teamName } from '../teams'
import { useThemeColors } from '../theme'

export default function Driver() {
  const { driverId } = useParams()
  const q = useDriver(driverId)
  const c = useThemeColors()
  usePageTitle(q.data?.driver.name)

  if (q.isPending) return <Loading what="driver" />
  if (isNotFound(q.error)) return <p className="text-ink-2">No driver with id {driverId}.</p>
  if (q.error) return <ErrorState error={q.error} />
  const d = q.data

  const recent = [...d.recent_results].reverse() // oldest -> newest for the chart
  const finished = d.recent_results.filter((r) => r.position != null)
  const avgFinish = finished.length ? finished.reduce((a, r) => a + r.position!, 0) / finished.length : null
  const dnfs = d.recent_results.length - finished.length
  const chart = recent.map((r: DriverResult) => ({
    race: r.race_name.replace(' Grand Prix', ''),
    finish: r.position,
    grid: r.grid || null,
    text: r.position_text,
  }))

  return (
    <div className="space-y-8">
      <Link to="/drivers" className="eyebrow hover:text-ink">← All drivers</Link>
      <header className="panel rise relative overflow-hidden p-6 sm:p-8">
        <div
          className="pointer-events-none absolute inset-0"
          style={{ background: `radial-gradient(600px 240px at 0% 0%, ${teamColor(d.driver.team_id)}40, transparent 70%)` }}
          aria-hidden
        />
        <span
          className="display pointer-events-none absolute -bottom-10 right-2 text-[10rem] leading-none opacity-20 sm:text-[14rem]"
          style={{ color: teamColor(d.driver.team_id) }}
          aria-hidden
        >
          {d.driver.number ?? ''}
        </span>
        <div className="relative">
          <div className="eyebrow flex items-center gap-2">
            <span className="h-3 w-1 rounded-full" style={{ background: teamColor(d.driver.team_id) }} aria-hidden />
            {teamName(d.driver.team_name)}
            {d.nationality && <span>· {d.nationality}</span>}
          </div>
          <h1 className="display mt-2 text-4xl uppercase leading-none sm:text-6xl">
            {d.driver.name.split(' ').slice(0, -1).join(' ')}{' '}
            <span className="block">{d.driver.name.split(' ').slice(-1)}</span>
          </h1>
          <div className="mt-3 flex gap-3 text-sm text-ink-2">
            {d.driver.code && <span className="display text-lg text-ink">{d.driver.code}</span>}
            {d.driver.number != null && <span className="display text-lg">#{d.driver.number}</span>}
          </div>
        </div>
      </header>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile label={`${d.season} points`} value={num(d.season_points, 0)} detail="races and sprints" />
        <StatTile
          label={`Average finish, last ${d.recent_results.length}`}
          value={avgFinish ? `P${num(avgFinish, 1)}` : '–'}
          detail={`classified finishes only · ${dnfs} DNF${dnfs === 1 ? '' : 's'}`}
        />
        <StatTile
          label="Predictions made"
          value={String(d.predictions.length)}
          detail={d.predictions[0] ? `latest: ${pct(d.predictions[0].p_win)} to win` : 'none yet'}
        />
      </div>

      {chart.length > 0 && (
        <Card eyebrow="Form guide" title="Recent form" subtitle="Starting and finishing position, last races. Higher on the chart is better; gaps are retirements.">
          <div className="mb-2 flex flex-wrap gap-4 text-xs text-ink-2">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded" style={{ background: c.s1 }} /> Finish
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded" style={{ background: c.s2 }} /> Grid
            </span>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chart} margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={c.grid} />
              <XAxis dataKey="race" tick={{ fill: c.muted, fontSize: 11 }} axisLine={{ stroke: c.axis }} tickLine={false} interval={0} angle={-30} textAnchor="end" height={56} />
              <YAxis reversed domain={[1, 22]} ticks={[1, 5, 10, 15, 20]} tickFormatter={(v) => `P${v}`} width={40} tick={{ fill: c.muted, fontSize: 12 }} axisLine={{ stroke: c.axis }} tickLine={false} />
              <Tooltip
                cursor={{ stroke: c.axis }}
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <TooltipPanel
                      title={String(label)}
                      rows={[
                        { key: c.s1, label: 'finish', value: payload[0].payload.finish ? `P${payload[0].payload.finish}` : payload[0].payload.text },
                        { key: c.s2, label: 'grid', value: payload[0].payload.grid ? `P${payload[0].payload.grid}` : 'pit lane' },
                      ]}
                    />
                  ) : null
                }
              />
              <Line dataKey="grid" stroke={c.s2} strokeWidth={2} dot={{ r: 4, fill: c.s2, stroke: c.card, strokeWidth: 2 }} isAnimationActive={false} />
              <Line dataKey="finish" stroke={c.s1} strokeWidth={2} dot={{ r: 4, fill: c.s1, stroke: c.card, strokeWidth: 2 }} connectNulls={false} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      )}

      <Card eyebrow="Model vs reality" title="Prediction history" subtitle="What the model expected for this driver, and what happened.">
        {d.predictions.length === 0 ? (
          <p className="text-ink-2">No predictions include this driver yet.</p>
        ) : (
          <div className="-mx-4 overflow-x-auto sm:mx-0">
            <table className="tabular w-full min-w-[480px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-ink-2">
                  <th className="py-2 pl-4 font-medium sm:pl-0">Race</th>
                  <th className="px-2 font-medium">Stage</th>
                  <th className="px-2 text-right font-medium">Predicted</th>
                  <th className="px-2 text-right font-medium">Win</th>
                  <th className="px-2 text-right font-medium">Podium</th>
                  <th className="px-2 pr-4 text-right font-medium sm:pr-0">Actual</th>
                </tr>
              </thead>
              <tbody>
                {d.predictions.map((p) => (
                  <tr key={p.snapshot_id} className="border-b border-line last:border-0">
                    <td className="py-2 pl-4 sm:pl-0">
                      <Link to={`/races/${p.race_id}`} className="hover:underline">{p.race_id}</Link>
                    </td>
                    <td className="px-2 text-ink-2">{STAGE_LABEL[p.stage]}</td>
                    <td className="px-2 text-right">P{p.pred_rank}</td>
                    <td className="px-2 text-right">{pct(p.p_win)}</td>
                    <td className="px-2 text-right">{pct(p.p_podium)}</td>
                    <td className="px-2 pr-4 text-right sm:pr-0">{p.actual_position ? `P${p.actual_position}` : '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
