import { useState } from 'react'
import { usePageTitle } from '../usePageTitle'
import { Link } from 'react-router'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { usePerformance } from '../api/hooks'
import type { CalibrationBin, StageBacktest, Stage, TrackRecordEntry } from '../api/types'
import { HonestOdds, PlainCards, RecentForecasts, SeasonStrip, Verdict } from '../components/PlainRecord'
import { Badge, Card, ErrorState, Loading, Segmented, StatTile, TooltipPanel, PageHeader } from '../components/ui'
import { BASELINE_LABEL, STAGE_LABEL, num, pct } from '../format'
import { useThemeColors, type ThemeColors } from '../theme'

const label = (m: string) => BASELINE_LABEL[m] ?? m
const axisProps = (c: ThemeColors) => ({
  tick: { fill: c.muted, fontSize: 12 },
  axisLine: { stroke: c.axis },
  tickLine: false,
})

export default function ModelPerformance() {
  usePageTitle('Track record')
  const perf = usePerformance()
  const [stage, setStage] = useState<Stage>('post')
  const c = useThemeColors()

  if (perf.isPending) return <Loading what="performance" />
  if (perf.error) return <ErrorState error={perf.error} />
  const bt = perf.data.backtest[stage]

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Is the model any good?"
        title="Track record"
        subtitle={`We replayed every race since ${bt?.plain?.seasons[0]?.season ?? 'the backtest start'}. Each time the model only knew what was known before that race, just like a real forecast. Here's how it did against the obvious guess.`}
        actions={
          <Segmented
            label="Prediction stage"
            value={stage}
            onChange={setStage}
            options={(['post', 'pre'] as const).map((s) => ({ value: s, label: STAGE_LABEL[s] }))}
          />
        }
      />

      {!bt ? (
        <Card>
          <p className="text-ink-2">No backtest results yet. Run <code>f1p backtest</code>.</p>
        </Card>
      ) : (
        bt.plain && (
          <>
            <Verdict p={bt.plain} />
            <PlainCards p={bt.plain} />
            <SeasonStrip p={bt.plain} />
            <HonestOdds bands={bt.plain.honesty} />
          </>
        )
      )}
      <RecentForecasts entries={perf.data.track_record} stage={stage} />

      {/* The technical view, folded away: every method, every measure. */}
      <details className="panel group/nerd p-4 sm:p-6">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
          <span>
            <span className="eyebrow block">For the curious</span>
            <span className="display block text-xl sm:text-2xl">The full numbers</span>
            <span className="mt-1 block text-sm text-ink-2">
              Every method and measure, the calibration chart and each saved forecast's score.
            </span>
          </span>
          <span className="display text-3xl text-ink-2 transition-transform group-open/nerd:rotate-45" aria-hidden>
            +
          </span>
        </summary>
        <div className="mt-6 space-y-8">
          {bt && (
            <>
              <Headline bt={bt} />
              <div className="grid gap-6 lg:grid-cols-2">
                <AccuracyBars bt={bt} c={c} />
                <SeasonLines bt={bt} c={c} stage={stage} />
              </div>
              <Calibration calibration={bt.calibration} c={c} />
              <SummaryTable bt={bt} />
            </>
          )}
          <TrackRecord entries={perf.data.track_record} />
        </div>
      </details>
    </div>
  )
}

function bestBaseline(bt: StageBacktest) {
  return bt.summary.filter((s) => s.model !== 'model' && s.model !== 'uniform')[0]
}

function Headline({ bt }: { bt: StageBacktest }) {
  const model = bt.summary.find((s) => s.model === 'model')!
  const base = bestBaseline(bt)
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <StatTile
        label="Order correlation"
        value={num(model.metrics.spearman, 3)}
        detail={`vs ${num(base.metrics.spearman, 3)} for ${label(base.model).toLowerCase()} · ${model.races} races`}
      />
      <StatTile
        label="Winner called"
        value={pct(model.metrics.winner_hit)}
        detail={`vs ${pct(base.metrics.winner_hit)} for ${label(base.model).toLowerCase()}`}
      />
      <StatTile
        label="Win log-loss (lower is better)"
        value={num(model.metrics.win_logloss, 2)}
        detail={`vs ${num(base.metrics.win_logloss, 2)} for ${label(base.model).toLowerCase()}`}
      />
    </div>
  )
}

function AccuracyBars({ bt, c }: { bt: StageBacktest; c: ThemeColors }) {
  const data = bt.summary.map((s) => ({ model: s.model, name: label(s.model), value: s.metrics.spearman }))
  return (
    <Card title="Order correlation by method" subtitle="Spearman correlation of predicted vs actual finishing order. Higher is better.">
      <ResponsiveContainer width="100%" height={data.length * 40 + 30}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 48, top: 0, bottom: 0 }}>
          <CartesianGrid horizontal={false} stroke={c.grid} />
          <XAxis type="number" domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} {...axisProps(c)} />
          <YAxis type="category" dataKey="name" width={150} {...axisProps(c)} tick={{ fill: c.ink2, fontSize: 12 }} />
          <Tooltip
            cursor={{ fill: 'var(--hover)' }}
            content={({ active, payload }) =>
              active && payload?.length ? (
                <TooltipPanel title={payload[0].payload.name} rows={[{ label: 'order correlation', value: num(payload[0].payload.value, 3) }]} />
              ) : null
            }
          />
          <Bar dataKey="value" barSize={16} radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.model} fill={d.model === 'model' ? c.s1 : c.neutralMark} />
            ))}
            <LabelList dataKey="value" position="right" formatter={(v: unknown) => num(Number(v), 3)} fill={c.ink2} fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  )
}

function SeasonLines({ bt, c, stage }: { bt: StageBacktest; c: ThemeColors; stage: Stage }) {
  const compare = stage === 'post' ? ['model', 'grid', 'championship'] : ['model', 'championship', 'practice']
  const colors = [c.s1, c.s2, c.s3]
  const seasons = [...new Set(bt.by_season.map((p) => p.season))].sort()
  const data = seasons.map((season) => {
    const row: Record<string, number> = { season }
    for (const m of compare) {
      const p = bt.by_season.find((x) => x.model === m && x.season === season)
      if (p) row[m] = p.spearman
    }
    return row
  })
  return (
    <Card title="Season by season" subtitle="Order correlation per season for the model and the strongest rules.">
      <div className="mb-2 flex flex-wrap gap-4 text-xs text-ink-2">
        {compare.map((m, i) => (
          <span key={m} className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded" style={{ background: colors[i] }} />
            {label(m)}
          </span>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ left: 0, right: 16, top: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={c.grid} />
          <XAxis dataKey="season" {...axisProps(c)} />
          <YAxis domain={[0.4, 0.8]} ticks={[0.4, 0.5, 0.6, 0.7, 0.8]} width={36} {...axisProps(c)} />
          <Tooltip
            cursor={{ stroke: c.axis }}
            content={({ active, payload, label: season }) =>
              active && payload?.length ? (
                <TooltipPanel
                  title={String(season)}
                  rows={payload.map((p) => ({ key: String(p.color), label: label(String(p.dataKey)), value: num(Number(p.value), 3) }))}
                />
              ) : null
            }
          />
          {compare.map((m, i) => (
            <Line
              key={m}
              dataKey={m}
              stroke={colors[i]}
              strokeWidth={2}
              dot={{ r: 4, fill: colors[i], stroke: c.card, strokeWidth: 2 }}
              activeDot={{ r: 5, stroke: c.card, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Card>
  )
}

function Calibration({ calibration, c }: { calibration: Record<string, CalibrationBin[]>; c: ThemeColors }) {
  const series = [
    { key: 'win', name: 'Win', color: c.s1 },
    { key: 'podium', name: 'Podium', color: c.s2 },
    { key: 'points', name: 'Points', color: c.s3 },
  ].filter((s) => calibration[s.key]?.length)
  const [table, setTable] = useState(false)
  return (
    <Card
      title="Are the probabilities honest?"
      subtitle="Predictions grouped by stated probability: how often the event actually happened. On the diagonal = calibrated."
      actions={
        <Segmented
          label="Calibration view"
          value={table ? 'table' : 'chart'}
          onChange={(v) => setTable(v === 'table')}
          options={[{ value: 'chart', label: 'Chart' }, { value: 'table', label: 'Table' }]}
        />
      }
    >
      {table ? (
        <div className="overflow-x-auto">
          <table className="tabular w-full max-w-xl text-sm">
            <thead>
              <tr className="border-b border-line text-left text-ink-2">
                <th className="py-2 font-medium">Event</th>
                <th className="px-2 text-right font-medium">Predicted</th>
                <th className="px-2 text-right font-medium">Happened</th>
                <th className="px-2 text-right font-medium">Driver-races</th>
              </tr>
            </thead>
            <tbody>
              {series.flatMap((s) =>
                calibration[s.key].map((b, i) => (
                  <tr key={`${s.key}${i}`} className="border-b border-line last:border-0">
                    <td className="py-1.5 text-ink-2">{s.name}</td>
                    <td className="px-2 text-right">{pct(b.predicted)}</td>
                    <td className="px-2 text-right">{pct(b.observed)}</td>
                    <td className="px-2 text-right text-ink-2">{b.n}</td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap gap-4 text-xs text-ink-2">
            {series.map((s) => (
              <span key={s.key} className="inline-flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
                {s.name}
              </span>
            ))}
            <span className="text-muted">dot = one probability band</span>
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <ScatterChart margin={{ left: 0, right: 16, top: 8, bottom: 16 }}>
              <CartesianGrid stroke={c.grid} />
              <XAxis
                type="number"
                dataKey="predicted"
                domain={[0, 1]}
                ticks={[0, 0.25, 0.5, 0.75, 1]}
                tickFormatter={(v) => pct(v)}
                label={{ value: 'Predicted probability', position: 'insideBottom', offset: -10, fill: c.muted, fontSize: 12 }}
                {...axisProps(c)}
              />
              <YAxis
                type="number"
                dataKey="observed"
                domain={[0, 1]}
                ticks={[0, 0.25, 0.5, 0.75, 1]}
                tickFormatter={(v) => pct(v)}
                width={44}
                {...axisProps(c)}
              />
              <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke={c.axis} strokeWidth={1} />
              <Tooltip
                cursor={false}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const b = payload[0].payload as CalibrationBin & { series: string }
                  return (
                    <TooltipPanel
                      title={`${b.series}: predicted ${pct(b.predicted)}`}
                      rows={[
                        { label: 'actually happened', value: pct(b.observed) },
                        { label: 'driver-races', value: String(b.n) },
                      ]}
                    />
                  )
                }}
              />
              {series.map((s) => (
                <Scatter
                  key={s.key}
                  name={s.name}
                  data={calibration[s.key].map((b) => ({ ...b, series: s.name }))}
                  fill={s.color}
                  stroke={c.card}
                  strokeWidth={2}
                  shape="circle"
                  isAnimationActive={false}
                />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </>
      )}
    </Card>
  )
}

function SummaryTable({ bt }: { bt: StageBacktest }) {
  return (
    <Card title="All methods, all measures" subtitle="Averages over every backtest race.">
      <div className="-mx-4 overflow-x-auto sm:mx-0">
        <table className="tabular w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-ink-2">
              <th className="py-2 pl-4 font-medium sm:pl-0">Method</th>
              <th className="px-2 text-right font-medium">Order corr.</th>
              <th className="px-2 text-right font-medium">Avg. position error</th>
              <th className="px-2 text-right font-medium">Winner</th>
              <th className="px-2 text-right font-medium">Top-3</th>
              <th className="px-2 text-right font-medium">Win log-loss</th>
              <th className="px-2 pr-4 text-right font-medium sm:pr-0">Podium Brier</th>
            </tr>
          </thead>
          <tbody>
            {bt.summary.map((s) => (
              <tr key={s.model} className={`border-b border-line last:border-0 ${s.model === 'model' ? 'font-semibold' : ''}`}>
                <td className="py-2 pl-4 sm:pl-0">{label(s.model)}</td>
                <td className="px-2 text-right">{num(s.metrics.spearman, 3)}</td>
                <td className="px-2 text-right">{num(s.metrics.pos_mae, 2)}</td>
                <td className="px-2 text-right">{pct(s.metrics.winner_hit)}</td>
                <td className="px-2 text-right">{pct(s.metrics.top3_hit)}</td>
                <td className="px-2 text-right">{num(s.metrics.win_logloss, 2)}</td>
                <td className="px-2 pr-4 text-right sm:pr-0">{num(s.metrics.podium_brier, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function TrackRecord({ entries }: { entries: TrackRecordEntry[] }) {
  const scored = entries.filter((e) => e.spearman != null)
  const live = scored.filter((e) => e.live)
  return (
    <Card
      title="Every saved forecast, scored"
      subtitle={
        live.length
          ? `${live.length} live forecast${live.length === 1 ? '' : 's'} scored so far.`
          : 'Every saved prediction. Live = made before qualifying / the race; backfill = made afterwards from data available at the time.'
      }
    >
      {entries.length === 0 ? (
        <p className="text-ink-2">No predictions saved yet.</p>
      ) : (
        <div className="-mx-4 overflow-x-auto sm:mx-0">
          <table className="tabular w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-ink-2">
                <th className="py-2 pl-4 font-medium sm:pl-0">Race</th>
                <th className="px-2 font-medium">Stage</th>
                <th className="px-2 font-medium">Type</th>
                <th className="px-2 text-right font-medium">Order corr.</th>
                <th className="px-2 text-right font-medium">Baseline</th>
                <th className="px-2 text-right font-medium">Winner</th>
                <th className="px-2 pr-4 text-right font-medium sm:pr-0">Win log-loss</th>
              </tr>
            </thead>
            <tbody>
              {[...entries].reverse().map((e) => (
                <tr key={e.snapshot_id} className="border-b border-line last:border-0">
                  <td className="py-2 pl-4 sm:pl-0">
                    <Link to={`/races/${e.race_id}`} className="hover:underline">{e.race_name}</Link>
                  </td>
                  <td className="px-2 text-ink-2">{STAGE_LABEL[e.stage]}</td>
                  <td className="px-2">{e.live ? <Badge tone="good">Live</Badge> : <Badge>Backfill</Badge>}</td>
                  {e.spearman == null ? (
                    <td colSpan={4} className="px-2 pr-4 text-right text-muted sm:pr-0">awaiting result</td>
                  ) : (
                    <>
                      <td className="px-2 text-right font-semibold">{num(e.spearman, 3)}</td>
                      <td className="px-2 text-right text-ink-2">
                        {num(e.baseline_spearman, 3)} <span className="text-xs">({label(e.baseline_name ?? '').toLowerCase()})</span>
                      </td>
                      <td className="px-2 text-right">{e.winner_hit ? '✓' : '✗'}</td>
                      <td className="px-2 pr-4 text-right sm:pr-0">
                        {num(e.win_logloss, 2)} <span className="text-ink-2">vs {num(e.baseline_win_logloss, 2)}</span>
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}
