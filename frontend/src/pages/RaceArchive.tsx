import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { useSeasonRaces, useSeasons } from '../api/hooks'
import type { DriverRef, RaceSummary } from '../api/types'
import CircuitMap from '../components/CircuitMap'
import { Badge, ErrorState, Loading, PageHeader, StatTile, TeamStripe } from '../components/ui'
import { chance, pct, shortDate } from '../format'
import { teamColor } from '../teams'
import { usePageTitle } from '../usePageTitle'

export default function RaceArchive() {
  usePageTitle('Races')
  const seasons = useSeasons()
  const [params, setParams] = useSearchParams()
  const latest = seasons.data?.[seasons.data.length - 1]
  const [season, setSeason] = useState<number | undefined>(Number(params.get('season')) || undefined)
  useEffect(() => {
    if (season === undefined && latest) setSeason(latest)
  }, [season, latest])
  const races = useSeasonRaces(season)

  const choose = (s: number) => {
    setSeason(s)
    setParams({ season: String(s) }, { replace: true })
  }

  if (seasons.error) return <ErrorState error={seasons.error} />
  const rows = races.data ?? []
  const done = rows.filter((r) => r.status === 'completed')
  const called = rows.filter((r) => r.winner && r.favourite)
  const hits = called.filter((r) => r.winner!.id === r.favourite!.driver.id).length
  const nextId = rows.find((r) => r.status === 'upcoming')?.id

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Calendar"
        title="Races"
        subtitle="Every round of the season: who won, who the model backed, and whether it called it. Races marked backfill were predicted after the fact from data available beforehand."
        actions={
          <label className="flex items-center gap-2 text-sm text-ink-2">
            <span className="eyebrow">Season</span>
            <select
              value={season ?? ''}
              onChange={(e) => choose(Number(e.target.value))}
              className="rounded-full border border-line-strong bg-card px-4 py-2 font-semibold text-ink"
            >
              {[...(seasons.data ?? [])].reverse().map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
        }
      />

      {races.isPending ? (
        <Loading what="races" />
      ) : races.error ? (
        <ErrorState error={races.error} />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatTile label="Rounds" value={`${done.length} / ${rows.length}`} detail="completed" />
            <StatTile label="Predicted" value={String(called.length)} detail="races with a forecast and a result" />
            <StatTile
              label="Favourite won"
              value={called.length ? `${hits} of ${called.length}` : '–'}
              detail={called.length ? `${pct(hits / called.length)} of predicted races` : 'no scored forecasts yet'}
            />
          </div>
          <div className={`grid gap-4 sm:grid-cols-2 lg:grid-cols-3 ${races.isPlaceholderData ? 'opacity-60' : ''}`}>
            {rows.map((r, i) => (
              <RaceCard key={r.id} race={r} next={r.id === nextId} delay={i * 30} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function RaceCard({ race: r, next, delay }: { race: RaceSummary; next: boolean; delay: number }) {
  const hit = r.winner && r.favourite ? r.winner.id === r.favourite.driver.id : null
  return (
    <Link
      to={`/races/${r.id}`}
      className={`panel rise group relative block overflow-hidden p-5 transition-all hover:-translate-y-0.5 hover:border-line-strong ${
        next ? 'border-brand/60 shadow-[0_0_40px_-12px_rgba(225,6,0,0.6)]' : ''
      }`}
      style={{ animationDelay: `${Math.min(delay, 400)}ms` }}
    >
      <span className="display pointer-events-none absolute -bottom-6 -right-2 text-8xl text-white/[0.04]" aria-hidden>
        {String(r.round).padStart(2, '0')}
      </span>
      <div className="relative flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="eyebrow flex flex-wrap items-center gap-x-2">
            <span className="whitespace-nowrap">Round {r.round} · {shortDate(r.race_date)}</span>
            {r.weekend_format === 'sprint' && <span className="text-brand-hot">Sprint</span>}
          </div>
          <h2 className="display mt-1 text-2xl uppercase leading-tight group-hover:text-white">
            {r.name.replace(' Grand Prix', '')}
          </h2>
          <div className="mt-1 text-sm text-ink-2">{r.locality ?? r.circuit_name}{r.country ? `, ${r.country}` : ''}</div>
        </div>
        {/* The winner's team colour once the race is run. */}
        <CircuitMap
          circuitId={r.circuit_id}
          label={r.circuit_name}
          color={r.winner ? teamColor(r.winner.team_id) : 'var(--brand-hot)'}
          lap={next ? 'always' : 'hover'}
          className="h-20 w-24 shrink-0 text-ink-2 transition-colors group-hover:text-ink"
        />
      </div>

      <div className="mt-4 space-y-2 text-sm">
        <Row label="Winner" driver={r.winner} empty={next ? 'Next race' : r.status === 'upcoming' ? 'Upcoming' : '–'} />
        <Row
          label="Model"
          driver={r.favourite?.driver ?? null}
          extra={r.favourite ? chance(r.favourite.p_win) : undefined}
          empty="No forecast"
        />
      </div>
      <div className="mt-4 flex items-center gap-2">
        {next && <Badge tone="live">Next up</Badge>}
        {hit === true && <Badge tone="good">✓ Called it</Badge>}
        {hit === false && <Badge>✗ Missed</Badge>}
        {r.favourite && !r.favourite.live && (
          <span className="text-xs text-muted" title="Predicted after the fact, using only data available before the race">
            backfill
          </span>
        )}
      </div>
    </Link>
  )
}

function Row({ label, driver, extra, empty }: { label: string; driver: DriverRef | null; extra?: string; empty: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="eyebrow w-14">{label}</span>
      {driver ? (
        <span className="flex min-w-0 flex-1 items-center gap-2">
          <TeamStripe teamId={driver.team_id} className="h-4" />
          <span className="truncate font-medium">{driver.name}</span>
          {extra && <span className="tabular ml-auto text-ink-2">{extra}</span>}
        </span>
      ) : (
        <span className="flex-1 text-muted">{empty}</span>
      )}
    </div>
  )
}
