import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'
import { apiGet } from '../api/client'
import {
  ApiError,
  isNotFound,
  useCreatePlayer,
  useLeaderboard,
  useMyPick,
  useMyPicks,
  useNextRace,
  usePicksSummary,
  useRaceField,
  useSavePick,
  useSeasonRaces,
} from '../api/hooks'
import type { DriverRef, RaceSummary } from '../api/types'
import Countdown from '../components/Countdown'
import { Badge, Card, ErrorState, Loading, PageHeader } from '../components/ui'
import { localTime } from '../format'
import { setPlayer, usePlayer } from '../player'
import { buttonClass } from '../styles'
import { teamColor, teamName } from '../teams'
import { usePageTitle } from '../usePageTitle'

const SEASON = new Date().getUTCFullYear()

export default function Play() {
  usePageTitle('Beat the model')
  const player = usePlayer()
  const [params] = useSearchParams()
  const next = useNextRace()
  const races = useSeasonRaces(SEASON)
  const requested = races.data?.find((r) => r.id === params.get('race'))
  const race: RaceSummary | undefined = requested ?? next.data

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Prediction game"
        title="Beat the model"
        subtitle="Pick the podium before every race and see if you can out-predict 10,000 simulations."
      />
      <ol className="grid gap-3 sm:grid-cols-3">
        {[
          ['01', 'Pick', 'Choose your P1, P2 and P3 before lights out.'],
          ['02', 'Lock', 'Picks lock when the race starts. Then the model reveals its podium.'],
          ['03', 'Score', '10 pts per exact spot, 4 for a driver on the podium, +10 for a perfect podium.'],
        ].map(([n, t, d]) => (
          <li key={n} className="panel rise flex gap-3 p-4">
            <span className="display text-3xl text-brand-hot">{n}</span>
            <span>
              <span className="display block text-lg uppercase">{t}</span>
              <span className="text-sm text-ink-2">{d}</span>
            </span>
          </li>
        ))}
      </ol>

      {!player ? <Join /> : <PlayerBar />}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          {next.isPending ? (
            <Loading what="the next race" />
          ) : race ? (
            <>
              <PickCard race={race} />
              <CrowdCard race={race} />
            </>
          ) : (
            <Card title="Season over">
              <p className="text-ink-2">No race left to pick this season. Check the leaderboard.</p>
            </Card>
          )}
          {player && <History />}
        </div>
        <Leaderboard />
      </div>
    </div>
  )
}

function Join() {
  const create = useCreatePlayer()
  const [nickname, setNickname] = useState('')
  const [key, setKey] = useState('')
  const [keyError, setKeyError] = useState<string | null>(null)
  const [showKey, setShowKey] = useState(false)

  const signInWithKey = async () => {
    setKeyError(null)
    try {
      const me = await apiGet<{ id: number; nickname: string }>('/players/me', { 'X-Player-Token': key.trim() })
      setPlayer({ ...me, token: key.trim() })
    } catch (e) {
      setKeyError(e instanceof ApiError && e.status === 401 ? "That key doesn't match a player." : String(e))
    }
  }

  return (
    <Card title="Join the game" subtitle="No account needed: pick a nickname. Your player key stays in this browser.">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate(nickname.trim(), { onSuccess: (p) => setPlayer(p) })
        }}
      >
        <label className="flex flex-col gap-1 text-xs text-ink-2">
          Nickname
          <input
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            minLength={3}
            maxLength={20}
            required
            placeholder="e.g. Lights Out"
            className="w-56 rounded-lg border border-line bg-card px-3 py-2 text-sm text-ink"
          />
        </label>
        <button
          type="submit"
          disabled={create.isPending || nickname.trim().length < 3}
          className={buttonClass.primary}
        >
          {create.isPending ? 'Joining…' : 'Join'}
        </button>
        {create.error && <p className="w-full text-sm text-critical">{create.error.message}</p>}
      </form>
      <button onClick={() => setShowKey(!showKey)} className="mt-4 text-sm text-ink-2 underline">
        Already playing on another device?
      </button>
      {showKey && (
        <div className="mt-2 flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-ink-2">
            Player key
            <input
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className="w-72 rounded-lg border border-line bg-card px-3 py-2 font-mono text-sm text-ink"
            />
          </label>
          <button onClick={signInWithKey} disabled={!key.trim()} className="rounded-lg border border-line px-4 py-2 text-sm hover:bg-hover disabled:opacity-40">
            Use key
          </button>
          {keyError && <p className="w-full text-sm text-critical">{keyError}</p>}
        </div>
      )}
    </Card>
  )
}

function PlayerBar() {
  const player = usePlayer()!
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(player.token)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 2000)
    } catch {
      window.prompt('Copy your player key:', player.token)
    }
  }
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-card px-4 py-3 text-sm">
      <span>
        Playing as <span className="font-semibold">{player.nickname}</span>
      </span>
      <button onClick={copy} className="rounded-lg border border-line px-3 py-1 hover:bg-hover">
        {copied ? 'Copied ✓' : 'Copy player key'}
      </button>
      <span className="text-xs text-muted">Use the key to play from another device. Keep it private.</span>
      <button
        onClick={() => {
          if (window.confirm('Forget this player on this device? You can come back with your player key.')) setPlayer(null)
        }}
        className="ml-auto text-ink-2 underline"
      >
        Sign out
      </button>
    </div>
  )
}

function PickCard({ race }: { race: RaceSummary }) {
  const player = usePlayer()
  const field = useRaceField(race.id)
  const mine = useMyPick(race.id)
  const save = useSavePick(race.id)
  const summary = usePicksSummary(race.id)
  const [podium, setPodium] = useState<string[]>(['', '', ''])
  useEffect(() => {
    if (mine.data) setPodium(mine.data.podium.map((d) => d.id))
  }, [mine.data])

  const locked = summary.data?.locked ?? race.status === 'completed'
  const drivers = [...(field.data?.drivers ?? [])].sort((a, b) => a.name.localeCompare(b.name))
  const valid = podium.every(Boolean) && new Set(podium).size === 3
  const changed = !mine.data || mine.data.podium.some((d, i) => d.id !== podium[i])

  return (
    <Card
      title={`Your podium: ${race.name}`}
      subtitle={
        locked
          ? 'Picks are locked.'
          : summary.data?.lock_at_utc
            ? `Picks lock at lights out, ${localTime(summary.data.lock_at_utc)}.`
            : undefined
      }
      actions={!locked && race.race_start_utc ? <Countdown to={race.race_start_utc} label="Locks in" /> : undefined}
    >
      {!player ? (
        <p className="text-ink-2">Join above to make your pick.</p>
      ) : field.isPending || mine.isPending ? (
        <Loading what="your pick" />
      ) : locked ? (
        mine.data ? (
          <LockedPick podium={mine.data.podium} points={mine.data.points} actual={summary.data?.actual_podium} />
        ) : (
          <p className="text-ink-2">You didn't pick for this race.</p>
        )
      ) : (
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (valid) save.mutate(podium as [string, string, string])
          }}
          className="space-y-3"
        >
          {/* Podium order on screen: P2, P1, P3 (sm and up), with P1 raised. */}
          <div className="grid gap-3 sm:grid-cols-3 sm:items-end">
            {[1, 0, 2].map((i) => {
              const chosen = drivers.find((d) => d.id === podium[i])
              return (
                <label
                  key={i}
                  className={`relative flex flex-col gap-2 overflow-hidden rounded-2xl border border-line-strong bg-black/25 p-4 ${
                    i === 0 ? 'sm:order-2 sm:pb-8' : i === 1 ? 'sm:order-1' : 'sm:order-3'
                  }`}
                >
                  <span className="h-1 absolute inset-x-0 top-0" style={{ background: chosen ? teamColor(chosen.team_id) : 'transparent' }} aria-hidden />
                  <span className="flex items-baseline justify-between">
                    <span className="display text-4xl text-white/90">P{i + 1}</span>
                    <span className="eyebrow">{['Winner', 'Second', 'Third'][i]}</span>
                  </span>
                  <span className="display h-7 text-xl">{chosen?.code ?? '—'}</span>
                  <select
                    value={podium[i]}
                    onChange={(e) => setPodium(podium.map((p, j) => (j === i ? e.target.value : p)))}
                    aria-label={`${['Winner', 'Second', 'Third'][i]} (P${i + 1})`}
                    className="rounded-xl border border-line-strong bg-card px-3 py-2 text-sm text-ink"
                  >
                    <option value="">Choose a driver…</option>
                    {drivers.map((d) => (
                      <option key={d.id} value={d.id} disabled={podium.includes(d.id) && podium[i] !== d.id}>
                        {d.name} ({teamName(d.team_name)})
                      </option>
                    ))}
                  </select>
                </label>
              )
            })}
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={!valid || !changed || save.isPending}
              className={buttonClass.primary}
            >
              {save.isPending ? 'Saving…' : mine.data ? 'Update pick' : 'Lock in my pick'}
            </button>
            {mine.data && !changed && <span className="text-sm text-good">✓ Saved. You can change it until lights out.</span>}
            {save.error && <span className="text-sm text-critical">{save.error.message}</span>}
            {mine.error && !isNotFound(mine.error) && <span className="text-sm text-critical">{mine.error.message}</span>}
          </div>
        </form>
      )}
    </Card>
  )
}

function LockedPick({ podium, points, actual }: { podium: DriverRef[]; points: number | null; actual?: DriverRef[] | null }) {
  return (
    <div className="space-y-3">
      <Podium drivers={podium} actual={actual ?? undefined} />
      {points != null ? (
        <p className="text-sm">
          You scored <span className="text-lg font-semibold">{points}</span> <span className="text-ink-2">of 40</span>
        </p>
      ) : (
        <p className="text-sm text-ink-2">Waiting for the official result.</p>
      )}
    </div>
  )
}

function Podium({ drivers, actual }: { drivers: DriverRef[]; actual?: DriverRef[] }) {
  return (
    <ol className="grid gap-2 sm:grid-cols-3">
      {drivers.map((d, i) => {
        const exact = actual?.[i]?.id === d.id
        const onPodium = actual?.some((a) => a.id === d.id)
        return (
          <li key={d.id} className="relative overflow-hidden rounded-2xl border border-line-strong bg-black/25 p-4">
            <span className="absolute inset-x-0 top-0 h-1" style={{ background: teamColor(d.team_id) }} aria-hidden />
            <div className="display text-3xl text-white/90">P{i + 1}</div>
            <div className="display text-xl">{d.code}</div>
            <div className="text-sm text-ink-2">{d.name}</div>
            {actual && (
              <div className={`text-xs ${exact ? 'text-good' : onPodium ? 'text-ink' : 'text-muted'}`}>
                {exact ? '✓ exact (+10)' : onPodium ? 'on podium (+4)' : 'missed'}
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}

function CrowdCard({ race }: { race: RaceSummary }) {
  const s = usePicksSummary(race.id)
  if (s.isPending) return null
  if (s.error) return <ErrorState error={s.error} />
  const d = s.data
  const max = Math.max(1, ...d.winner_picks.map((w) => w.count))
  return (
    <Card
      title="The crowd vs the model"
      subtitle={`${d.n_players} player${d.n_players === 1 ? '' : 's'} picked this race.`}
    >
      {d.n_players === 0 ? (
        <p className="text-sm text-ink-2">No picks yet. Be the first.</p>
      ) : (
        <>
          <h3 className="mb-2 text-sm font-medium text-ink-2">Who the crowd picked to win</h3>
          <ul className="space-y-1.5">
            {d.winner_picks.slice(0, 6).map((w) => (
              <li key={w.driver.id} className="flex items-center gap-3 text-sm">
                <span className="w-32 truncate">{w.driver.name}</span>
                <span className="h-2 flex-1 rounded-r bg-hover">
                  <span className="block h-2 rounded-r bg-s1" style={{ width: `${(w.count / max) * 100}%` }} />
                </span>
                <span className="tabular w-8 text-right">{w.count}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="mt-5 grid gap-4 sm:grid-cols-3">
        <PodiumList title="Crowd's podium" drivers={d.crowd_podium} />
        <PodiumList
          title="Model's podium"
          drivers={d.model_podium}
          empty={d.locked ? 'No live forecast' : 'Revealed at lights out'}
          extra={d.model_points != null ? `${d.model_points} pts` : undefined}
        />
        <PodiumList title="Actual podium" drivers={d.actual_podium} empty="After the race" extra={d.crowd_avg_points != null ? `crowd avg ${d.crowd_avg_points.toFixed(1)} pts` : undefined} />
      </div>
    </Card>
  )
}

function PodiumList({ title, drivers, empty = '–', extra }: { title: string; drivers: DriverRef[] | null; empty?: string; extra?: string }) {
  return (
    <div>
      <div className="mb-1 text-sm font-medium text-ink-2">{title}</div>
      {drivers && drivers.length ? (
        <ol className="space-y-0.5 text-sm">
          {drivers.map((d, i) => (
            <li key={d.id}>
              <span className="tabular mr-2 text-ink-2">{i + 1}</span>
              {d.name}
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-muted">{empty}</p>
      )}
      {extra && <p className="mt-1 text-xs text-ink-2">{extra}</p>}
    </div>
  )
}

function Leaderboard() {
  const board = useLeaderboard(SEASON)
  const player = usePlayer()
  return (
    <Card title={`${SEASON} leaderboard`} subtitle="Points from completed races. The model's entry uses its last forecast before lights out.">
      {board.isPending ? (
        <Loading what="leaderboard" />
      ) : board.error ? (
        <ErrorState error={board.error} />
      ) : board.data.length === 0 ? (
        <p className="text-sm text-ink-2">No scored races yet. Scores appear once a race result is official.</p>
      ) : (
        <table className="tabular w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-ink-2">
              <th className="py-2 font-medium">#</th>
              <th className="px-2 font-medium">Player</th>
              <th className="px-2 text-right font-medium">Points</th>
              <th className="px-2 text-right font-medium">Races</th>
              <th className="text-right font-medium">Exact</th>
            </tr>
          </thead>
          <tbody>
            {board.data.map((e) => (
              <tr key={e.name} className={`border-b border-line last:border-0 ${e.name === player?.nickname ? 'font-semibold' : ''}`}>
                <td className="py-2"><RankBadge rank={e.rank} /></td>
                <td className="px-2">
                  {e.name} {e.is_model && <Badge>model</Badge>}
                  {e.name === player?.nickname && <span className="ml-1 text-xs text-ink-2">(you)</span>}
                </td>
                <td className="px-2 text-right">{e.points}</td>
                <td className="px-2 text-right text-ink-2">{e.races}</td>
                <td className="text-right text-ink-2">{e.exact}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  )
}

function History() {
  const picks = useMyPicks()
  if (picks.isPending || picks.error || !picks.data.length) return null
  return (
    <Card title="Your picks">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-ink-2">
            <th className="py-2 font-medium">Race</th>
            <th className="px-2 font-medium">Your podium</th>
            <th className="text-right font-medium">Points</th>
          </tr>
        </thead>
        <tbody>
          {picks.data.map((p) => (
            <tr key={p.race_id} className="border-b border-line last:border-0">
              <td className="py-1.5">{p.race_name.replace(' Grand Prix', ' GP')}</td>
              <td className="px-2 text-ink-2">{p.podium.map((d) => d.code).join(' · ')}</td>
              <td className="tabular text-right">{p.points ?? (p.locked ? 'pending' : 'open')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}

const MEDALS = ['#f5c542', '#c7ccd6', '#d08a4f'] // gold, silver, bronze (decorative; rank number shown)

function RankBadge({ rank }: { rank: number }) {
  const medal = MEDALS[rank - 1]
  return (
    <span
      className="display inline-flex h-7 w-7 items-center justify-center rounded-full text-sm"
      style={medal ? { background: medal, color: '#111' } : { border: '1px solid var(--line-strong)', color: 'var(--ink-2)' }}
    >
      {rank}
    </span>
  )
}
