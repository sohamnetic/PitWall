import { useState } from 'react'
import { isNotFound, useRace, useSnapshot } from '../api/hooks'
import type { PredictionRow, RaceDetail, Score, Snapshot, Stage } from '../api/types'
import { BASELINE_LABEL, STAGE_LABEL, chance, localTime, num, pct } from '../format'
import { teamColor } from '../teams'
import { useAccent } from '../accent'
import { usePageTitle } from '../usePageTitle'
import CircuitMap from './CircuitMap'
import Countdown from './Countdown'
import PositionHeatmap from './PositionHeatmap'
import PrePostChart from './PrePostChart'
import ProbabilityTable from './ProbabilityTable'
import { Badge, ButtonLink, Card, DriverLabel, ErrorState, Loading, Segmented, StatTile } from './ui'

export default function RaceView({ raceId }: { raceId: string }) {
  const race = useRace(raceId)
  const ids = race.data?.race.latest_predictions
  const defaultStage: Stage = ids?.post != null ? 'post' : 'pre'
  const [chosen, setChosen] = useState<Stage | null>(null)
  const stage = chosen ?? defaultStage
  const snap = useSnapshot(ids?.[stage])
  const other = useSnapshot(stage === 'post' ? ids?.pre : ids?.post)
  usePageTitle(race.data?.race.name)
  // Floodlights take the favourite's team colour.
  useAccent(snap.data ? teamColor(snap.data.rows[0]?.driver.team_id) : null)

  if (race.isPending) return <Loading what="race" />
  if (race.error) {
    if (isNotFound(race.error)) return <p className="text-ink-2">No race with id {raceId}.</p>
    return <ErrorState error={race.error} />
  }
  const d = race.data
  const hasAny = ids?.pre != null || ids?.post != null
  const pre = stage === 'pre' ? snap.data : other.data
  const post = stage === 'post' ? snap.data : other.data

  return (
    <div className="space-y-8">
      <RaceHero d={d} color={snap.data ? teamColor(snap.data.rows[0]?.driver.team_id) : undefined} />

      {!hasAny ? (
        <Card>
          <p className="text-ink-2">
            No prediction for this race yet. Run <code>f1p predict --race {d.race.id}</code> after
            practice (or after qualifying).
          </p>
        </Card>
      ) : (
        <>
          <div className="rise flex flex-wrap items-center gap-x-4 gap-y-3">
            <Segmented
              label="Prediction stage"
              value={stage}
              onChange={setChosen}
              options={(['pre', 'post'] as const).map((s) => ({
                value: s,
                label: STAGE_LABEL[s],
                disabled: ids?.[s] == null,
              }))}
            />
            {snap.data && <SnapshotNote s={snap.data} quali={d.race.qualifying_source} />}
          </div>

          {snap.error && <ErrorState error={snap.error} />}
          {snap.data && (
            <div className={`space-y-8 transition-opacity ${snap.isPlaceholderData ? 'opacity-60' : ''}`}>
              <PodiumForecast s={snap.data} />
              {snap.data.score && <ScoreCard score={snap.data.score} />}
              <Card
                eyebrow="Timing tower"
                title="Chances for every driver"
                subtitle="From 10,000 simulated races. Ordered by predicted finish."
              >
                <ProbabilityTable rows={snap.data.rows} />
              </Card>
              <Card
                eyebrow="Finishing positions"
                title="Where each driver is likely to finish"
                subtitle="Each row is a driver, each column a finishing position. Brighter means more likely."
              >
                <PositionHeatmap rows={snap.data.rows} />
              </Card>
              {pre && post && (
                <Card
                  eyebrow="Qualifying effect"
                  title="What qualifying changed"
                  subtitle="Expected finishing position before and after qualifying. Left is better."
                >
                  <PrePostChart pre={pre.rows} post={post.rows} />
                </Card>
              )}
            </div>
          )}
        </>
      )}

      {(d.results.length > 0 || d.qualifying.length > 0) && <Classification d={d} />}
    </div>
  )
}

function RaceHero({ d, color }: { d: RaceDetail; color?: string }) {
  const r = d.race
  const [place, ...rest] = r.name.replace(' Grand Prix', '|Grand Prix').split('|')
  return (
    <section className="panel rise relative overflow-hidden p-5 pt-7 sm:p-8 sm:pt-10">
      <div className="kerb absolute inset-x-0 top-0" aria-hidden />
      <div className="chequer pointer-events-none absolute right-0 top-0 h-40 w-64 opacity-[0.07]" aria-hidden />
      <div className="speed-stripes pointer-events-none absolute inset-0 opacity-70" aria-hidden />
      <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-brand/20 blur-3xl" aria-hidden />
      {/* The circuit, with a car in the favourite's team colour lapping it. */}
      <CircuitMap
        circuitId={r.circuit_id}
        label={r.circuit_name}
        color={color}
        lap="always"
        className="pointer-events-none absolute right-3 top-8 h-24 w-32 text-ink opacity-40 sm:right-8 sm:top-10 sm:h-44 sm:w-60 sm:opacity-90 lg:h-52 lg:w-72"
      />
      <div className="relative">
        <div className="eyebrow flex flex-wrap items-center gap-x-2">
          <span>{r.season} season</span>
          <span className="text-brand-hot">/</span>
          <span>Round {r.round}</span>
          {r.weekend_format === 'sprint' && (
            <>
              <span className="text-brand-hot">/</span>
              <span>Sprint weekend</span>
            </>
          )}
        </div>
        <h1 className="display mt-2 text-5xl uppercase leading-[0.9] sm:text-7xl">
          {place}
          {rest.length > 0 && <span className="block text-2xl text-ink-2 sm:text-3xl">{rest.join(' ')}</span>}
        </h1>
        <p className="mt-3 text-ink-2">
          {r.circuit_name}
          {r.locality && `, ${r.locality}`}
          <span className="mx-2 text-muted">·</span>
          Race {localTime(r.race_start_utc ?? `${r.race_date}T00:00:00`)}
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {r.status === 'completed' ? <Badge>Race run</Badge> : <Badge tone="live">Upcoming</Badge>}
          {r.qualifying_source === 'provisional' && <Badge>Qualifying provisional (from lap timing)</Badge>}
        </div>

        {r.status === 'upcoming' && (
          <div className="mt-6 flex flex-wrap items-end justify-between gap-6">
            {r.race_start_utc && <Countdown to={r.race_start_utc} label="Lights out in" variant="hero" />}
            <div className="flex flex-wrap gap-2">
              <ButtonLink to={`/play?race=${r.id}`} variant="primary">
                Pick your podium →
              </ButtonLink>
              <ButtonLink to={`/ask?race=${r.id}`}>Ask the model</ButtonLink>
              <ButtonLink to={`/ask?race=${r.id}&tab=whatif`}>What if…</ButtonLink>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}

function SnapshotNote({ s, quali }: { s: Snapshot; quali: string }) {
  const cutoff = s.stage === 'pre' ? 'qualifying' : 'the race'
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-ink-2">
      {s.made_before_cutoff ? <Badge tone="live">Live forecast</Badge> : <Badge>Backfill</Badge>}
      <span>
        Made {localTime(s.created_at)}
        {s.made_before_cutoff ? `, before ${cutoff}.` : `, after ${cutoff}, from data available before it.`}{' '}
        Trained on races up to {s.model_trained_through}.
        {s.stage === 'post' && quali === 'provisional' && ' Grid assumed to match qualifying.'}
      </span>
    </p>
  )
}

function PodiumForecast({ s }: { s: Snapshot }) {
  const [p1, p2, p3] = s.rows
  const fav = s.rows[0]
  const contenders = s.rows.filter((r) => r.p_win >= 0.1).length
  return (
    <section className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="panel rise p-4 sm:p-6">
        <div className="eyebrow">Predicted podium</div>
        <h2 className="display mt-1 text-xl sm:text-2xl">The most likely top three</h2>
        <div className="mt-6 grid grid-cols-3 items-end gap-2 sm:gap-3">
          {p2 && <PodiumStep row={p2} place={2} height="h-24 sm:h-28" />}
          {p1 && <PodiumStep row={p1} place={1} height="h-36 sm:h-40" />}
          {p3 && <PodiumStep row={p3} place={3} height="h-16 sm:h-20" />}
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1">
        <StatTile
          label="Favourite to win"
          value={
            <span>
              {chance(fav.p_win)} <span className="text-lg text-ink-2">{fav.driver.code}</span>
            </span>
          }
          detail={`${fav.driver.name} · expected P${num(fav.expected_pos, 1)}`}
          accent={teamColor(fav.driver.team_id)}
        />
        <StatTile
          label="Upset chance"
          value={chance(1 - fav.p_win)}
          detail={`someone other than ${fav.driver.code} wins · ${contenders} driver${contenders === 1 ? '' : 's'} with a 10%+ shot`}
        />
      </div>
    </section>
  )
}

function PodiumStep({ row, place, height }: { row: PredictionRow; place: number; height: string }) {
  const color = teamColor(row.driver.team_id)
  return (
    <div className="flex flex-col items-center text-center" style={{ animationDelay: `${(3 - place) * 80}ms` }}>
      <div className="display text-2xl sm:text-4xl">{row.driver.code}</div>
      <div className="mt-0.5 hidden max-w-full truncate text-xs text-ink-2 sm:block">{row.driver.name}</div>
      <div className="mt-1 text-xs text-ink-2">
        <span className="tabular font-semibold text-ink">{chance(row.p_podium)}</span> podium
      </div>
      <div
        className={`relative mt-3 w-full rounded-t-xl border border-b-0 border-line-strong ${height}`}
        style={{ background: `linear-gradient(180deg, ${color}55, transparent 85%)` }}
      >
        <span className="absolute inset-x-0 top-0 h-1 rounded-t-xl" style={{ background: color }} aria-hidden />
        <span className="display absolute inset-x-0 top-2 text-3xl text-white/90 sm:text-5xl">{place}</span>
      </div>
    </div>
  )
}

function ScoreCard({ score }: { score: Score }) {
  const base = BASELINE_LABEL[score.baseline_name] ?? score.baseline_name
  const rows: { label: string; key: keyof Score['model']; fmt: (v: number) => string; higher: boolean }[] = [
    { label: 'Order correlation', key: 'spearman', fmt: (v) => num(v, 3), higher: true },
    { label: 'Winner called', key: 'winner_hit', fmt: (v) => (v ? 'Yes' : 'No'), higher: true },
    { label: 'Top-3 overlap', key: 'top3_hit', fmt: (v) => pct(v), higher: true },
    { label: 'Top-10 overlap', key: 'top10_hit', fmt: (v) => pct(v), higher: true },
    { label: 'Win log-loss (lower = better)', key: 'win_logloss', fmt: (v) => num(v, 2), higher: false },
    { label: 'Podium Brier (lower = better)', key: 'podium_brier', fmt: (v) => num(v, 3), higher: false },
  ]
  const wins = rows.filter((r) => (r.higher ? score.model[r.key] > score.baseline[r.key] : score.model[r.key] < score.baseline[r.key])).length
  return (
    <Card eyebrow="Post-race verdict" title={`The model won ${wins} of ${rows.length} measures`} subtitle={`Against ${base.toLowerCase()} on this race.`}>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((r) => {
          const m = score.model[r.key]
          const b = score.baseline[r.key]
          const better = r.higher ? m > b : m < b
          const tie = m === b
          return (
            <div key={r.key} className={`rounded-xl border p-3 ${better ? 'border-good/40 bg-good/5' : 'border-line'}`}>
              <div className="eyebrow">{r.label}</div>
              <div className="mt-1 flex items-baseline justify-between gap-2">
                <span className="display tabular text-2xl">{r.fmt(m)}</span>
                <span className="text-xs text-ink-2">
                  vs <span className="tabular">{r.fmt(b)}</span>
                  {better ? <span className="ml-1 text-good">✓ better</span> : tie ? <span className="ml-1">= tie</span> : null}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function Classification({ d }: { d: RaceDetail }) {
  const [tab, setTab] = useState<'race' | 'quali' | 'sprint'>(d.results.length ? 'race' : 'quali')
  const opts = [
    { value: 'race' as const, label: 'Race', disabled: !d.results.length },
    { value: 'quali' as const, label: 'Qualifying', disabled: !d.qualifying.length },
    { value: 'sprint' as const, label: 'Sprint', disabled: !d.sprint.length },
  ]
  const results = tab === 'sprint' ? d.sprint : d.results
  const th = 'py-2 text-left font-medium eyebrow'
  return (
    <Card eyebrow="Official timing" title="Classification" actions={<Segmented label="Session" value={tab} onChange={setTab} options={opts} />}>
      <div className="-mx-4 overflow-x-auto sm:mx-0">
        {tab === 'quali' ? (
          <table className="w-full min-w-[440px] text-sm">
            <thead>
              <tr className="border-b border-line">
                <th className={`${th} pl-4 sm:pl-0`}>Pos</th>
                <th className={`${th} px-2`}>Driver</th>
                <th className={`${th} px-2 text-right`}>Q1</th>
                <th className={`${th} px-2 text-right`}>Q2</th>
                <th className={`${th} px-2 pr-4 text-right sm:pr-0`}>Q3</th>
              </tr>
            </thead>
            <tbody>
              {d.qualifying.map((q) => (
                <tr key={q.driver.id} className="border-b border-line last:border-0 hover:bg-hover">
                  <td className="display tabular py-2 pl-4 text-lg sm:pl-0">{q.position}</td>
                  <td className="px-2"><DriverLabel driver={q.driver} /></td>
                  {[q.q1_s, q.q2_s, q.q3_s].map((t, i) => (
                    <td key={i} className="tabular px-2 text-right last:pr-4 sm:last:pr-0">{lapTime(t)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="w-full min-w-[440px] text-sm">
            <thead>
              <tr className="border-b border-line">
                <th className={`${th} pl-4 sm:pl-0`}>Pos</th>
                <th className={`${th} px-2`}>Driver</th>
                <th className={`${th} px-2 text-right`}>Grid</th>
                <th className={`${th} px-2 text-right`}>Pts</th>
                <th className={`${th} px-2 pr-4 sm:pr-0`}>Status</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.driver.id} className="border-b border-line last:border-0 hover:bg-hover">
                  <td className="display tabular py-2 pl-4 text-lg sm:pl-0">{r.position_text}</td>
                  <td className="px-2"><DriverLabel driver={r.driver} /></td>
                  <td className="tabular px-2 text-right text-ink-2">{r.grid === 0 ? 'Pit' : (r.grid ?? '–')}</td>
                  <td className="tabular px-2 text-right">{r.points || ''}</td>
                  <td className="px-2 pr-4 text-ink-2 sm:pr-0">{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {(tab === 'quali' ? d.qualifying : results).some((r) => r.source === 'fastf1') && (
        <p className="mt-3 text-xs text-muted">Provisional: rebuilt from lap timing until the official classification is published.</p>
      )}
    </Card>
  )
}

function lapTime(s: number | null): string {
  if (s == null) return ''
  const m = Math.floor(s / 60)
  return `${m}:${(s - m * 60).toFixed(3).padStart(6, '0')}`
}
