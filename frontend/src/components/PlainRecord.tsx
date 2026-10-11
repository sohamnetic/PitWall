import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import type { HonestyBand, PlainSummary, Stage, TrackRecordEntry } from '../api/types'
import { BASELINE_LABEL, chance, num, pct } from '../format'
import { Badge, Card, DriverLabel } from './ui'

/** The Track record page in plain English: the model against the obvious guess, in counts. */

const GUESS: Record<string, { name: string; rule: string; winner: string }> = {
  grid: { name: 'Grid order', rule: 'everyone finishes where they start', winner: 'Backing the pole-sitter' },
  championship: {
    name: 'Championship order',
    rule: 'the race finishes in championship order',
    winner: 'Backing the championship leader',
  },
}

function guessFor(p: PlainSummary) {
  const name = BASELINE_LABEL[p.baseline] ?? p.baseline
  return GUESS[p.baseline] ?? { name, rule: name.toLowerCase(), winner: name }
}

export function Verdict({ p }: { p: PlainSummary }) {
  const g = guessFor(p)
  const h = p.head_to_head
  const share = h.model / Math.max(1, h.model + h.baseline)
  const headline =
    share >= 0.6
      ? 'Yes. It beats the obvious guess.'
      : share >= 0.52
        ? 'Mostly. It edges the obvious guess.'
        : 'Not really. The obvious guess does as well.'
  return (
    <section className="panel rise relative overflow-hidden p-5 sm:p-8">
      <div className="kerb absolute inset-x-0 top-0" aria-hidden />
      <div className="eyebrow">The short answer</div>
      <h2 className="display mt-1 text-3xl uppercase leading-tight sm:text-5xl">{headline}</h2>
      <p className="mt-3 max-w-2xl text-ink-2">
        In <strong className="text-ink">{h.model} of {p.races} races</strong>, the model's predicted
        order was closer to the real result than simply assuming {g.rule}. The guess was closer in{' '}
        {h.baseline}
        {h.tie ? `, and ${h.tie} were a tie` : ''}.
      </p>
      <div className="mt-6">
        <div
          className="flex h-5 overflow-hidden rounded-full bg-white/[0.06]"
          role="img"
          aria-label={`Model closer in ${h.model} races, guess closer in ${h.baseline}, ${h.tie} ties`}
        >
          <span className="fill h-full bg-s1" style={{ width: `${(h.model / p.races) * 100}%` }} />
          <span className="h-full bg-white/25" style={{ width: `${(h.tie / p.races) * 100}%` }} />
          <span className="h-full bg-white/[0.12]" style={{ width: `${(h.baseline / p.races) * 100}%` }} />
        </div>
        <div className="mt-2 flex justify-between gap-4 text-sm">
          <span>
            <span className="display text-lg text-ink">{h.model}</span> <span className="text-ink-2">model closer</span>
          </span>
          <span className="text-right">
            <span className="text-ink-2">{g.name.toLowerCase()} closer</span>{' '}
            <span className="display text-lg text-ink">{h.baseline}</span>
          </span>
        </div>
      </div>
    </section>
  )
}

type Tag = 'better' | 'same' | 'worse'

function compare(model: number, base: number, tolerance: number, higherIsBetter = true): Tag {
  const d = higherIsBetter ? model - base : base - model
  return Math.abs(d) <= tolerance ? 'same' : d > 0 ? 'better' : 'worse'
}

function TagBadge({ tag }: { tag: Tag }) {
  if (tag === 'better') return <Badge tone="good">✓ Better</Badge>
  if (tag === 'same') return <Badge>≈ About the same</Badge>
  return <Badge>Guess does better</Badge>
}

function honestyGap(bands: HonestyBand[]): number {
  const n = bands.reduce((a, b) => a + b.n, 0)
  return n ? bands.reduce((a, b) => a + b.n * Math.abs(b.said - b.happened), 0) / n : 0
}

export function PlainCards({ p }: { p: PlainSummary }) {
  const g = guessFor(p)
  const gap = honestyGap(p.honesty)
  const mid = p.honesty.find((b) => b.low >= 0.2 && b.high <= 0.4)
  const cards: { label: string; value: ReactNode; detail: string; vs: string; tag?: Tag }[] = [
    {
      label: 'Picks the winner',
      value: <>{p.winners.model} <span className="text-lg text-ink-2">of {p.races}</span></>,
      detail: `Its favourite won ${pct(p.winners.model / p.races)} of races.`,
      vs: `${g.winner}: ${p.winners.baseline} (${pct(p.winners.baseline / p.races)})`,
      tag: compare(p.winners.model, p.winners.baseline, p.races * 0.02),
    },
    {
      label: 'Names the podium',
      value: <>{num(p.podium_drivers.model, 1)} <span className="text-lg text-ink-2">of 3</span></>,
      detail: 'Of the three drivers it puts on the podium, how many really finish there, on average.',
      vs: `${g.name}: ${num(p.podium_drivers.baseline, 1)} of 3`,
      tag: compare(p.podium_drivers.model, p.podium_drivers.baseline, 0.05),
    },
    {
      label: 'Typical miss',
      value: <>{num(p.avg_miss.model, 1)} <span className="text-lg text-ink-2">places</span></>,
      detail: 'How far, on average, each driver finished from where the model put them.',
      vs: `${g.name}: ${num(p.avg_miss.baseline, 1)} places`,
      tag: compare(p.avg_miss.model, p.avg_miss.baseline, 0.05, false),
    },
    {
      label: 'Honest odds?',
      value: gap < 0.03 ? 'Yes' : gap < 0.06 ? 'Roughly' : 'Not quite',
      detail: mid
        ? `When it says about ${pct(mid.said)}, it happens ${pct(mid.happened)} of the time.`
        : 'Its percentages match how often things really happen.',
      vs: `Off by ${num(gap * 100, 1)} percentage points on average`,
    },
  ]
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card, i) => (
        <div key={card.label} className="panel rise flex flex-col p-4 sm:p-5" style={{ animationDelay: `${i * 60}ms` }}>
          <div className="eyebrow">{card.label}</div>
          <div className="display mt-2 text-4xl">{card.value}</div>
          <p className="mt-2 mb-4 text-sm text-ink-2">{card.detail}</p>
          <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-xs text-ink-2">
            <span>{card.vs}</span>
            {card.tag && <TagBadge tag={card.tag} />}
          </div>
        </div>
      ))}
    </div>
  )
}

export function SeasonStrip({ p }: { p: PlainSummary }) {
  const g = guessFor(p)
  const won = p.seasons.filter((s) => s.h2h_model > s.h2h_baseline).length
  return (
    <Card
      eyebrow="Season by season"
      title={`Closer than the guess in ${won} of ${p.seasons.length} seasons`}
      subtitle={`For each season, the number of races where the model's order beat "${g.rule}".`}
    >
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {p.seasons.map((s) => {
          const beat = s.h2h_model > s.h2h_baseline
          const level = s.h2h_model === s.h2h_baseline
          return (
            <div key={s.season} className={`rounded-xl border p-4 ${beat ? 'border-good/40 bg-good/5' : 'border-line bg-black/20'}`}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="display text-2xl">{s.season}</span>
                <span className={`text-xs ${beat ? 'text-good' : 'text-ink-2'}`}>
                  {beat ? '✓ model' : level ? '= level' : '✗ guess'}
                </span>
              </div>
              <div className="mt-2 flex h-2 overflow-hidden rounded-full bg-white/[0.06]" aria-hidden>
                <span className="h-full bg-s1" style={{ width: `${(s.h2h_model / s.races) * 100}%` }} />
                <span className="h-full bg-white/25" style={{ width: `${(s.h2h_tie / s.races) * 100}%` }} />
              </div>
              <div className="mt-2 text-sm text-ink-2">
                Closer in <span className="font-semibold text-ink">{s.h2h_model}</span> of {s.races}
              </div>
              <div className="text-xs text-muted">
                Winners: {s.model_winners} vs {s.baseline_winners} for the guess
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

export function HonestOdds({ bands }: { bands: HonestyBand[] }) {
  if (!bands.length) return null
  return (
    <Card
      eyebrow="Honest odds"
      title="When it says 30%, does it happen 30% of the time?"
      subtitle="Every chance it gave (to win, to make the podium, to score points), grouped by size, next to how often it really happened. When the bars match, you can take its percentages at face value."
    >
      <div className="space-y-3">
        <div className="flex flex-wrap gap-4 text-xs text-ink-2">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-3 w-5 rounded-sm border border-s1" /> it said
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-1.5 w-5 rounded-sm bg-s1" /> it happened
          </span>
        </div>
        {bands.map((b) => (
          <div
            key={b.low}
            className="grid grid-cols-[5.5rem_minmax(0,1fr)] items-center gap-x-3 gap-y-1 text-sm sm:grid-cols-[8rem_minmax(0,1fr)_auto]"
          >
            <span className="text-ink-2">{b.low === 0 ? `Under ${pct(b.high)}` : `${pct(b.low)} to ${pct(b.high)}`}</span>
            <div className="relative h-5">
              <span className="absolute inset-y-0 left-0 rounded-sm border border-s1/80" style={{ width: `${b.said * 100}%` }} aria-hidden />
              <span className="fill absolute left-0 top-1/2 h-1.5 -translate-y-1/2 rounded-sm bg-s1" style={{ width: `${b.happened * 100}%` }} aria-hidden />
            </div>
            <span className="tabular col-start-2 text-xs text-ink-2 sm:col-start-auto sm:whitespace-nowrap sm:text-right sm:text-sm">
              said <span className="text-ink">{chance(b.said)}</span> · happened{' '}
              <span className="font-semibold text-ink">{chance(b.happened, b.happened < 0.01 ? 1 : 0)}</span>
              <span className="text-muted"> · {b.n.toLocaleString()} times</span>
            </span>
          </div>
        ))}
      </div>
    </Card>
  )
}

export function RecentForecasts({ entries, stage }: { entries: TrackRecordEntry[]; stage: Stage }) {
  const [all, setAll] = useState(false)
  // One row per race: its latest forecast at this stage, newest race first.
  const latest = new Map<string, TrackRecordEntry>()
  for (const e of entries) if (e.stage === stage) latest.set(e.race_id, e)
  const rows = [...latest.values()].reverse()
  const shown = all ? rows : rows.slice(0, 8)
  const scored = rows.filter((e) => e.winner)
  const called = scored.filter((e) => e.pick?.id === e.winner?.id).length
  const live = rows.filter((e) => e.live).length
  return (
    <Card
      eyebrow="Real forecasts"
      title="Its favourite for every race this season"
      subtitle={
        <>
          {scored.length > 0 && `Its favourite won ${called} of ${scored.length} races. `}
          <strong className="text-ink">Live</strong> forecasts were published before the session, so
          they couldn't peek; <strong className="text-ink">backfill</strong> ones were made later, using
          only data from before the race.{live > 0 && ` ${live} live so far.`}
        </>
      }
    >
      {rows.length === 0 ? (
        <p className="text-ink-2">No forecasts saved yet.</p>
      ) : (
        <>
          <div className="-mx-4 overflow-x-auto sm:mx-0">
            <table className="w-full min-w-[480px] text-sm">
              <thead>
                <tr className="border-b border-line text-left">
                  <th className="eyebrow py-2 pl-4 font-medium sm:pl-0">Race</th>
                  <th className="eyebrow px-2 font-medium">Favourite</th>
                  <th className="eyebrow px-2 font-medium">Winner</th>
                  <th className="eyebrow px-2 font-medium">Result</th>
                  <th className="eyebrow px-2 pr-4 font-medium sm:pr-0">Type</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((e) => {
                  const hit = e.pick && e.winner ? e.pick.id === e.winner.id : null
                  return (
                    <tr key={e.snapshot_id} className="border-b border-line last:border-0 hover:bg-hover">
                      <td className="py-2 pl-4 sm:pl-0">
                        <Link to={`/races/${e.race_id}`} className="hover:underline">
                          {e.race_name.replace(' Grand Prix', '')}
                        </Link>
                      </td>
                      <td className="px-2">
                        {e.pick ? (
                          <span className="inline-flex items-center gap-1">
                            <DriverLabel driver={e.pick} showName={false} />
                            <span className="tabular text-ink-2">{chance(e.pick_p_win)}</span>
                          </span>
                        ) : (
                          '–'
                        )}
                      </td>
                      <td className="px-2">
                        {e.winner ? <DriverLabel driver={e.winner} showName={false} /> : <span className="text-muted">to come</span>}
                      </td>
                      <td className="px-2">
                        {hit === true ? (
                          <Badge tone="good">✓ Called it</Badge>
                        ) : hit === false ? (
                          <span className="text-ink-2">✗ Missed</span>
                        ) : (
                          <span className="text-muted">awaiting result</span>
                        )}
                      </td>
                      <td className="px-2 pr-4 sm:pr-0">
                        {e.live ? <Badge tone="live">Live</Badge> : <span className="text-xs text-muted">backfill</span>}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {rows.length > shown.length && (
            <button onClick={() => setAll(true)} className="mt-3 text-sm text-ink-2 underline hover:text-ink">
              Show all {rows.length} races
            </button>
          )}
        </>
      )}
    </Card>
  )
}
