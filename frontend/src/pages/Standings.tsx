import type { ReactNode } from 'react'
import { useSearchParams } from 'react-router'
import { CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useAccent } from '../accent'
import { useSeasons, useStandings } from '../api/hooks'
import type { ConstructorStanding, DriverStanding, Standings as Table } from '../api/types'
import { Card, DriverLabel, ErrorState, Loading, PageHeader, Segmented, TeamStripe, TooltipPanel } from '../components/ui'
import { teamColor, teamName } from '../teams'
import { useThemeColors } from '../theme'
import { usePageTitle } from '../usePageTitle'

type View = 'drivers' | 'constructors'

const pts = (p: number) => (p % 1 ? p.toFixed(1) : String(p))
const short = (name: string) => name.replace(' Grand Prix', '')

export default function Standings() {
  usePageTitle('Standings')
  const seasons = useSeasons()
  const [params, setParams] = useSearchParams()
  const season = Number(params.get('season')) || seasons.data?.[seasons.data.length - 1]
  const view: View = params.get('view') === 'constructors' ? 'constructors' : 'drivers'
  const q = useStandings(season)
  const s = q.data
  const leaderTeam = view === 'drivers' ? s?.drivers[0]?.driver.team_id : s?.constructors[0]?.team_id
  useAccent(leaderTeam ? teamColor(leaderTeam) : null) // floodlights in the leader's colours

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }

  if (seasons.error) return <ErrorState error={seasons.error} />
  const over = s ? s.rounds_done === s.rounds_total : false

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Championship"
        title="Standings"
        subtitle={
          !s
            ? undefined
            : over
              ? `Final standings after all ${s.rounds_total} rounds.`
              : `After ${s.rounds_done} of ${s.rounds_total} rounds. Grands Prix and sprints both count.`
        }
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <Segmented
              label="Championship"
              value={view}
              onChange={(v) => set('view', v)}
              options={[
                { value: 'drivers', label: 'Drivers' },
                { value: 'constructors', label: 'Constructors' },
              ]}
            />
            <label className="flex items-center gap-2 text-sm text-ink-2">
              <span className="eyebrow">Season</span>
              <select
                value={season ?? ''}
                onChange={(e) => set('season', e.target.value)}
                className="rounded-full border border-line-strong bg-card px-4 py-2 font-semibold text-ink"
              >
                {[...(seasons.data ?? [])].reverse().map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </label>
          </div>
        }
      />

      {q.isPending ? (
        <Loading what="standings" />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : !s!.drivers.length ? (
        <Card>
          <p className="text-ink-2">No results yet this season.</p>
        </Card>
      ) : (
        <div className={`space-y-8 ${q.isPlaceholderData ? 'opacity-60' : ''}`}>
          {view === 'drivers' ? <DriverChampionship s={s!} over={over} /> : <ConstructorChampionship s={s!} over={over} />}
          {s!.provisional && (
            <p className="text-xs text-muted">
              Includes provisional results rebuilt from lap timing; they're replaced when the official
              classification is published.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// --------------------------------------------------------------------------------- drivers

function DriverChampionship({ s, over }: { s: Table; over: boolean }) {
  const [leader, second] = s.drivers
  const alive = s.drivers.filter((d) => d.in_contention).length
  return (
    <>
      <LeaderCard
        over={over}
        teamId={leader.driver.team_id}
        bigNumber={leader.driver.number != null ? String(leader.driver.number) : '1'}
        name={leader.driver.name}
        sub={teamName(leader.driver.team_name)}
        points={leader.points}
        stats={[
          {
            label: over ? 'Won by' : 'Lead',
            value: second ? `${pts(leader.points - second.points)} pts` : '–',
            detail: second ? `over ${second.driver.name}` : undefined,
          },
          { label: 'Wins · Podiums', value: `${leader.wins} · ${leader.podiums}`, detail: `from ${s.rounds_done} Grands Prix` },
          fightStat(over, alive, s.points_left_driver, 'drivers'),
        ]}
      />
      <Card eyebrow="Drivers' championship" title="The table" subtitle={tableNote(over, s.points_left_driver)}>
        <div className="-mx-4 overflow-x-auto sm:mx-0">
          <table className="w-full min-w-[420px] text-sm">
            <thead>
              <tr className="border-b border-line text-left">
                <Th className="w-10 pl-4 sm:pl-0">Pos</Th>
                <Th>Driver</Th>
                <Th className="hidden xl:table-cell">Team</Th>
                <Th className="text-right">Points</Th>
                <Th className="text-right">Gap</Th>
                <Th className="text-right">Wins</Th>
                <Th className="hidden text-right sm:table-cell">Podiums</Th>
                <Th className="hidden pr-4 md:table-cell sm:pr-0">Last 5 races</Th>
              </tr>
            </thead>
            <tbody>
              {s.drivers.map((d, i) => (
                <DriverRow key={d.driver.id} d={d} s={s} leader={leader.points} i={i} cutoff={!over && isCutoff(s.drivers, i)} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <PointsRace
        title="How the title fight unfolded"
        rounds={s.rounds}
        progression={s.driver_progression}
        entries={s.drivers.map((d) => ({ id: d.driver.id, label: d.driver.code ?? d.driver.name }))}
      />
    </>
  )
}

function DriverRow({ d, s, leader, i, cutoff }: { d: DriverStanding; s: Table; leader: number; i: number; cutoff: boolean }) {
  const names = new Map(s.rounds.map((r) => [r.round, r.name]))
  return (
    <>
      <tr className={`rise border-b border-line last:border-0 hover:bg-hover ${i < 3 ? 'bg-white/[0.02]' : ''}`} style={{ animationDelay: `${Math.min(i, 12) * 25}ms` }}>
        <td className="display tabular py-2.5 pl-4 text-lg text-ink-2 sm:pl-0">{d.position}</td>
        <td className="px-2"><DriverLabel driver={d.driver} /></td>
        <td className="hidden whitespace-nowrap px-2 text-ink-2 xl:table-cell">{teamName(d.driver.team_name)}</td>
        <td className="px-2"><PointsBar points={d.points} leader={leader} /></td>
        <td className="tabular px-2 text-right text-ink-2">{d.gap ? `−${pts(d.gap)}` : '–'}</td>
        <td className="tabular px-2 text-right">{d.wins || ''}</td>
        <td className="tabular hidden px-2 text-right text-ink-2 sm:table-cell">{d.podiums || ''}</td>
        <td className="hidden px-2 pr-4 md:table-cell sm:pr-0">
          <div className="flex gap-1">
            {d.form.map((f) => <FormChip key={f.round} text={f.text} race={names.get(f.round)} />)}
          </div>
        </td>
      </tr>
      {cutoff && <CutoffRow cols={8} />}
    </>
  )
}

// ---------------------------------------------------------------------------- constructors

function ConstructorChampionship({ s, over }: { s: Table; over: boolean }) {
  const [leader, second] = s.constructors
  const alive = s.constructors.filter((t) => t.in_contention).length
  return (
    <>
      <LeaderCard
        over={over}
        teamId={leader.team_id}
        bigNumber="1"
        name={teamName(leader.team_name)}
        sub={leader.drivers.map((d) => d.name).join(' · ')}
        points={leader.points}
        stats={[
          {
            label: over ? 'Won by' : 'Lead',
            value: second ? `${pts(leader.points - second.points)} pts` : '–',
            detail: second ? `over ${teamName(second.team_name)}` : undefined,
          },
          { label: 'Wins · Podiums', value: `${leader.wins} · ${leader.podiums}`, detail: 'podiums count each car' },
          fightStat(over, alive, s.points_left_team, 'teams'),
        ]}
      />
      <Card eyebrow="Constructors' championship" title="The table" subtitle={tableNote(over, s.points_left_team)}>
        <div className="-mx-4 overflow-x-auto sm:mx-0">
          <table className="w-full min-w-[420px] text-sm">
            <thead>
              <tr className="border-b border-line text-left">
                <Th className="w-10 pl-4 sm:pl-0">Pos</Th>
                <Th>Team</Th>
                <Th className="text-right">Points</Th>
                <Th className="text-right">Gap</Th>
                <Th className="text-right">Wins</Th>
                <Th className="hidden pr-4 text-right sm:table-cell sm:pr-0">Podiums</Th>
              </tr>
            </thead>
            <tbody>
              {s.constructors.map((t, i) => (
                <TeamRow key={t.team_id} t={t} leader={leader.points} i={i} cutoff={!over && isCutoff(s.constructors, i)} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <PointsRace
        title="How the constructors' fight unfolded"
        rounds={s.rounds}
        progression={s.team_progression}
        entries={s.constructors.map((t) => ({ id: t.team_id, label: teamName(t.team_name) }))}
      />
    </>
  )
}

function TeamRow({ t, leader, i, cutoff }: { t: ConstructorStanding; leader: number; i: number; cutoff: boolean }) {
  return (
    <>
      <tr className={`rise border-b border-line last:border-0 hover:bg-hover ${i < 3 ? 'bg-white/[0.02]' : ''}`} style={{ animationDelay: `${i * 30}ms` }}>
        <td className="display tabular py-3 pl-4 text-lg text-ink-2 sm:pl-0">{t.position}</td>
        <td className="px-2">
          <div className="flex items-center gap-2.5">
            <TeamStripe teamId={t.team_id} className="h-8" />
            <div className="min-w-0">
              <div className="font-semibold">{teamName(t.team_name)}</div>
              <div className="truncate text-xs text-ink-2">{t.drivers.map((d) => d.code).join(' · ')}</div>
            </div>
          </div>
        </td>
        <td className="px-2"><PointsBar points={t.points} leader={leader} /></td>
        <td className="tabular px-2 text-right text-ink-2">{t.gap ? `−${pts(t.gap)}` : '–'}</td>
        <td className="tabular px-2 text-right">{t.wins || ''}</td>
        <td className="tabular hidden px-2 pr-4 text-right text-ink-2 sm:table-cell sm:pr-0">{t.podiums || ''}</td>
      </tr>
      {cutoff && <CutoffRow cols={6} />}
    </>
  )
}

// ---------------------------------------------------------------------------------- shared

function isCutoff(rows: { in_contention: boolean }[], i: number) {
  // The last row that can still win, when someone below it can't.
  return rows[i].in_contention && rows[i + 1] != null && !rows[i + 1].in_contention
}

function tableNote(over: boolean, left: number) {
  return over ? 'Ties are split on countback: most wins, then most second places, and so on.' : `${left} points still to play for.`
}

function fightStat(over: boolean, alive: number, left: number, who: 'drivers' | 'teams') {
  if (over) return { label: 'Season', value: 'Complete', detail: 'every round has been run' }
  if (alive === 1) return { label: 'Title fight', value: 'Decided', detail: `nobody can catch them with ${left} points left` }
  return { label: 'Still in the fight', value: `${alive} ${who}`, detail: `can still win it, with ${left} points left` }
}

function Th({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <th className={`eyebrow px-2 py-2 font-medium ${className}`}>{children}</th>
}

function CutoffRow({ cols }: { cols: number }) {
  return (
    <tr aria-hidden>
      <td colSpan={cols} className="py-1.5">
        <div className="flex items-center gap-3 text-[11px] uppercase tracking-wider text-brand-hot">
          <span className="h-px flex-1 bg-brand/50" />
          Out of the title fight below this line
          <span className="h-px flex-1 bg-brand/50" />
        </div>
      </td>
    </tr>
  )
}

function PointsBar({ points, leader }: { points: number; leader: number }) {
  return (
    <div className="flex items-center justify-end gap-2">
      <span className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-white/[0.06] sm:block" aria-hidden>
        <span className="fill block h-1.5 rounded-full bg-s1" style={{ width: `${leader ? (points / leader) * 100 : 0}%` }} />
      </span>
      <span className="display tabular w-12 text-right text-base">{pts(points)}</span>
    </div>
  )
}

function FormChip({ text, race }: { text: string; race?: string }) {
  const n = Number(text)
  const finished = Number.isFinite(n)
  const style = !finished
    ? 'border-critical/50 text-critical'
    : n === 1
      ? 'border-transparent bg-[#f5c542] text-black'
      : n <= 3
        ? 'border-transparent bg-white/85 text-black'
        : n <= 10
          ? 'border-line-strong text-ink'
          : 'border-line text-muted'
  return (
    <span
      title={`${race ? short(race) : ''}: ${finished ? `P${n}` : 'did not finish'}`}
      className={`display tabular inline-flex h-6 w-7 items-center justify-center rounded border text-xs ${style}`}
    >
      {finished ? n : text}
    </span>
  )
}

function LeaderCard({
  over,
  teamId,
  bigNumber,
  name,
  sub,
  points,
  stats,
}: {
  over: boolean
  teamId: string | null | undefined
  bigNumber: string
  name: string
  sub: string
  points: number
  stats: { label: string; value: string; detail?: string }[]
}) {
  const color = teamColor(teamId)
  return (
    <section className="panel rise relative overflow-hidden p-5 sm:p-8">
      <div className="kerb absolute inset-x-0 top-0" aria-hidden />
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: `radial-gradient(700px 300px at 0% 0%, ${color}45, transparent 70%)` }}
        aria-hidden
      />
      <span
        className="display pointer-events-none absolute -bottom-12 right-4 text-[11rem] leading-none opacity-15 sm:text-[15rem]"
        style={{ color }}
        aria-hidden
      >
        {bigNumber}
      </span>
      <div className="relative flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="eyebrow">{over ? 'Champion' : 'Championship leader'}</div>
          <h2 className="display mt-1 text-4xl uppercase leading-none sm:text-6xl">{name}</h2>
          <div className="mt-2 flex items-center gap-2 text-ink-2">
            <TeamStripe teamId={teamId} className="h-4" />
            {sub}
          </div>
        </div>
        <div className="text-right">
          <div className="display tabular text-6xl leading-none sm:text-7xl">{pts(points)}</div>
          <div className="eyebrow mt-1">points</div>
        </div>
      </div>
      <div className="relative mt-6 grid gap-3 sm:grid-cols-3">
        {stats.map((st) => (
          <div key={st.label} className="rounded-xl border border-line bg-black/25 px-4 py-3">
            <div className="eyebrow">{st.label}</div>
            <div className="display mt-1 text-2xl">{st.value}</div>
            {st.detail && <div className="text-sm text-ink-2">{st.detail}</div>}
          </div>
        ))}
      </div>
    </section>
  )
}

/** Cumulative points after each round. The top three get colour and a label at the line's
 *  end; everyone else is a faint grey line for context. */
function PointsRace({
  title,
  rounds,
  progression,
  entries,
}: {
  title: string
  rounds: Table['rounds']
  progression: Record<string, number[]>
  entries: { id: string; label: string }[]
}) {
  const c = useThemeColors()
  if (rounds.length < 2) return null
  const top = entries.slice(0, 3)
  const colors = [c.s1, c.s2, c.s3]
  const label = new Map(entries.map((e) => [e.id, e.label]))
  const data = rounds.map((r, i) => ({
    round: r.round,
    name: short(r.name),
    ...Object.fromEntries(entries.map((e) => [e.id, progression[e.id]?.[i] ?? 0])),
  }))
  const last = data.length - 1
  return (
    <Card eyebrow="Points race" title={title} subtitle="Total points after each round. The top three are highlighted.">
      <div className="mb-2 flex flex-wrap gap-4 text-xs text-ink-2">
        {top.map((e, i) => (
          <span key={e.id} className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded" style={{ background: colors[i] }} />
            {e.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5 text-muted">
          <span className="h-0.5 w-4 rounded" style={{ background: c.neutralMark }} />
          everyone else
        </span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={data} margin={{ left: 0, right: 72, top: 8, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke={c.grid} />
          <XAxis dataKey="round" tickFormatter={(v) => `R${v}`} tick={{ fill: c.muted, fontSize: 12 }} axisLine={{ stroke: c.axis }} tickLine={false} />
          <YAxis width={40} tick={{ fill: c.muted, fontSize: 12 }} axisLine={{ stroke: c.axis }} tickLine={false} />
          <Tooltip
            cursor={{ stroke: c.axis }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const row = payload[0].payload as Record<string, number | string>
              const leaders = entries
                .map((e) => ({ id: e.id, v: Number(row[e.id]) }))
                .sort((a, b) => b.v - a.v)
                .slice(0, 5)
              return (
                <TooltipPanel
                  title={`Round ${row.round}: ${row.name}`}
                  rows={leaders.map((l) => ({ key: l.id, label: label.get(l.id) ?? l.id, value: pts(l.v) }))}
                />
              )
            }}
          />
          {entries.slice(3).map((e) => (
            <Line key={e.id} dataKey={e.id} stroke={c.neutralMark} strokeOpacity={0.5} strokeWidth={1} dot={false} activeDot={false} isAnimationActive={false} />
          ))}
          {top.map((e, i) => (
            <Line key={e.id} dataKey={e.id} stroke={colors[i]} strokeWidth={2.5} dot={false} activeDot={{ r: 4, stroke: c.card, strokeWidth: 2 }} isAnimationActive={false}>
              <LabelList
                dataKey={e.id}
                content={(p) =>
                  p.index === last ? (
                    <text x={Number(p.x) + 6} y={Number(p.y)} dy={4} fill={colors[i]} fontSize={12} fontWeight={700}>
                      {e.label.length > 10 ? e.label.slice(0, 9) + '…' : e.label}
                    </text>
                  ) : null
                }
              />
            </Line>
          ))}
        </LineChart>
      </ResponsiveContainer>
    </Card>
  )
}
