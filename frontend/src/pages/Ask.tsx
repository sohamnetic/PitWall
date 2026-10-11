import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useRaceField, useSeasonRaces, useSimulation } from '../api/hooks'
import type { Answer, Question, QuestionKind, RaceField, RaceSummary, Scenario, SimulateResponse } from '../api/types'
import { ArrowDown, ArrowUp } from '../components/icons'
import { Badge, Card, ErrorState, Loading, Segmented, PageHeader } from '../components/ui'
import { chance, num } from '../format'
import { KIND_LABEL, describe, namesFor, questionKey, suggestions, verbal, type Names } from '../questions'
import { buttonClass } from '../styles'
import { usePageTitle } from '../usePageTitle'

const SEASON = new Date().getUTCFullYear()

function loadQuestions(raceId: string): Question[] {
  try {
    return JSON.parse(localStorage.getItem(`f1p.questions.${raceId}`) ?? '[]') as Question[]
  } catch {
    return []
  }
}

function saveQuestions(raceId: string, qs: Question[]) {
  try {
    localStorage.setItem(`f1p.questions.${raceId}`, JSON.stringify(qs))
  } catch {
    /* storage unavailable: questions live for this visit only */
  }
}

export default function Ask() {
  usePageTitle('Ask the model')
  const [params, setParams] = useSearchParams()
  const races = useSeasonRaces(SEASON)
  const askable = (races.data ?? []).filter(
    (r) => r.latest_predictions.post != null || r.latest_predictions.pre != null,
  )
  const defaultRace = askable.find((r) => r.status === 'upcoming') ?? askable[askable.length - 1]
  const raceId = params.get('race') ?? defaultRace?.id
  const race = askable.find((r) => r.id === raceId)
  const tab = params.get('tab') === 'whatif' ? 'whatif' : 'questions'

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    next.set(key, value)
    setParams(next, { replace: true })
  }

  if (races.isPending) return <Loading what="races" />
  if (races.error) return <ErrorState error={races.error} />

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="10,000 simulated races per answer"
        title="Ask the model"
        subtitle="Ask your own questions about a race, or change the starting grid and watch the race play out differently."
        actions={askable.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-ink-2">
            <span className="eyebrow">Race</span>
            <select
              value={raceId ?? ''}
              onChange={(e) => setParam('race', e.target.value)}
              className="max-w-[16rem] rounded-full border border-line-strong bg-card px-4 py-2 font-semibold text-ink"
            >
              {[...askable].reverse().map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name.replace(' Grand Prix', ' GP')}
                  {r.status === 'upcoming' ? ' (upcoming)' : ''}
                </option>
              ))}
            </select>
          </label>
        )}
      />

      {!race ? (
        <Card>
          <p className="text-ink-2">No predictions to ask about yet. Run <code>f1p predict</code> first.</p>
        </Card>
      ) : (
        <AskRace key={race.id} race={race} tab={tab} onTab={(t) => setParam('tab', t)} />
      )}
    </div>
  )
}

function AskRace({ race, tab, onTab }: { race: RaceSummary; tab: 'questions' | 'whatif'; onTab: (t: string) => void }) {
  const field = useRaceField(race.id)
  const [questions, setQuestions] = useState<Question[]>(() => loadQuestions(race.id))
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const debounced = useDebounced(scenario, 450)
  useEffect(() => saveQuestions(race.id, questions), [race.id, questions])

  const canWhatIf = field.data ? !field.data.completed : false
  const base = useSimulation(race.id, { questions })
  const sim = useSimulation(race.id, debounced && canWhatIf ? { scenario: debounced, questions } : null)
  const names = namesFor(field.data)
  // Match answers to questions by content: while a refetch runs, the previous response
  // (kept on screen) may hold a different set of questions.
  const byKey = (r?: SimulateResponse) => new Map(r?.answers.map((a) => [questionKey(a.question), a]))

  if (field.isPending) return <Loading what="the field" />
  if (field.error) return <ErrorState error={field.error} />
  const upcoming = !field.data.completed
  const active = scenario !== null && upcoming
  const shown = byKey(active && sim.data ? sim.data : base.data)
  const baseAnswers = byKey(base.data)

  const add = (q: Question) => {
    if (!questions.some((x) => questionKey(x) === questionKey(q))) setQuestions([q, ...questions].slice(0, 20))
  }
  const remove = (q: Question) => setQuestions(questions.filter((x) => questionKey(x) !== questionKey(q)))

  return (
    <div className="space-y-6">
      <Segmented
        label="Mode"
        value={tab}
        onChange={onTab}
        options={[
          { value: 'questions', label: 'Your questions' },
          { value: 'whatif', label: 'What if…' },
        ]}
      />

      {tab === 'whatif' && (
        <WhatIf
          field={field.data}
          scenario={scenario}
          onChange={setScenario}
          base={base.data}
          result={active ? sim.data : undefined}
          error={sim.error}
          busy={sim.isFetching || scenario !== debounced}
        />
      )}

      <Card
        title={tab === 'whatif' ? 'Your questions, under this what-if' : 'Your questions'}
        subtitle={
          field.data.completed
            ? 'This race has been run: each answer also says whether it came true.'
            : 'Answers update as you add questions or change the what-if.'
        }
        actions={active ? <Badge>With your what-if</Badge> : undefined}
      >
        <QuestionBuilder field={field.data} names={names} onAdd={add} />
        {base.data && (
          <Suggestions field={field.data} base={base.data} names={names} asked={questions} onAdd={add} />
        )}
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          {questions.map((q) => (
            <AnswerCard
              key={questionKey(q)}
              text={describe(q, names)}
              answer={shown.get(questionKey(q))}
              base={active ? baseAnswers.get(questionKey(q)) : undefined}
              onRemove={() => remove(q)}
            />
          ))}
        </div>
        {base.error && <div className="mt-3"><ErrorState error={base.error} /></div>}
      </Card>
    </div>
  )
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms)
    return () => window.clearTimeout(id)
  }, [value, ms])
  return v
}

// ------------------------------------------------------------------ question builder

const KINDS = Object.keys(KIND_LABEL) as QuestionKind[]
const K_PRESETS: Record<string, number[]> = {
  top_k: [1, 3, 5, 6, 10],
  team_top_k: [2, 3, 5, 10],
}

function QuestionBuilder({ field, names, onAdd }: { field: RaceField; names: Names; onAdd: (q: Question) => void }) {
  const drivers = [...field.drivers].sort((a, b) => a.name.localeCompare(b.name))
  const [kind, setKind] = useState<QuestionKind>('ahead')
  const [driver, setDriver] = useState(field.drivers[0]?.id ?? '')
  const [other, setOther] = useState(field.drivers[1]?.id ?? '')
  const [team, setTeam] = useState(field.teams[0]?.id ?? '')
  const [k, setK] = useState(3)
  const [podium, setPodium] = useState(field.drivers.slice(0, 3).map((d) => d.id))

  const q: Question = { kind }
  if (['top_k', 'position', 'ahead', 'dnf'].includes(kind)) q.driver = driver
  if (kind === 'ahead') q.other = other
  if (['team_top_k', 'team_wins'].includes(kind)) q.team = team
  if (['top_k', 'position', 'team_top_k'].includes(kind)) q.k = k
  if (kind === 'podium_exact') q.drivers = podium
  const invalid =
    (kind === 'ahead' && driver === other) || (kind === 'podium_exact' && new Set(podium).size < 3)

  const driverSelect = (value: string, set: (v: string) => void, label: string) => (
    <Select label={label} value={value} onChange={set}>
      {drivers.map((d) => (
        <option key={d.id} value={d.id}>{d.name}</option>
      ))}
    </Select>
  )

  return (
    <form
      className="flex flex-wrap items-end gap-3 rounded-2xl border border-line bg-black/20 p-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (!invalid) onAdd(q)
      }}
    >
      <Select label="Question" value={kind} onChange={(v) => {
        setKind(v as QuestionKind)
        if (v === 'team_top_k' && k === 1) setK(2)
      }}>
        {KINDS.map((x) => <option key={x} value={x}>{KIND_LABEL[x]}</option>)}
      </Select>
      {['top_k', 'position', 'ahead', 'dnf'].includes(kind) && driverSelect(driver, setDriver, 'Driver')}
      {kind === 'ahead' && driverSelect(other, setOther, 'Ahead of')}
      {['team_top_k', 'team_wins'].includes(kind) && (
        <Select label="Team" value={team} onChange={setTeam}>
          {field.teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </Select>
      )}
      {kind === 'position' && (
        <Select label="Position" value={String(k)} onChange={(v) => setK(Number(v))}>
          {field.drivers.map((_, i) => <option key={i} value={i + 1}>P{i + 1}</option>)}
        </Select>
      )}
      {(kind === 'top_k' || kind === 'team_top_k') && (
        <Select label="Top" value={String(k)} onChange={(v) => setK(Number(v))}>
          {K_PRESETS[kind].map((x) => (
            <option key={x} value={x}>
              {kind === 'top_k' && x === 1 ? '1 (win)' : x === 3 ? '3 (podium)' : x === 10 ? '10 (points)' : kind === 'team_top_k' && x === 2 ? '2 (one-two)' : x}
            </option>
          ))}
        </Select>
      )}
      {kind === 'podium_exact' &&
        [0, 1, 2].map((i) =>
          driverSelect(podium[i], (v) => setPodium(podium.map((p, j) => (j === i ? v : p))), `P${i + 1}`),
        )}
      <button
        type="submit"
        disabled={invalid}
        className={buttonClass.primary}
      >
        Ask
      </button>
      <p className="w-full text-sm text-ink-2">
        {invalid ? 'Pick different drivers.' : describe(q, names)}
      </p>
    </form>
  )
}

function Select({ label, value, onChange, children }: { label: string; value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-ink-2">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="max-w-[14rem] rounded-xl border border-line-strong bg-card px-3 py-2 text-sm text-ink"
      >
        {children}
      </select>
    </label>
  )
}

function Suggestions({
  field,
  base,
  names,
  asked,
  onAdd,
}: {
  field: RaceField
  base: SimulateResponse
  names: Names
  asked: Question[]
  onAdd: (q: Question) => void
}) {
  const taken = new Set(asked.map(questionKey))
  const left = suggestions(field, base.rows.map((r) => r.driver)).filter((q) => !taken.has(questionKey(q)))
  if (!left.length) return null
  return (
    <div className="mt-4">
      <p className="mb-2 text-sm text-ink-2">
        {asked.length ? 'More ideas:' : 'Not sure what to ask? Try one of these:'}
      </p>
      <div className="flex flex-wrap gap-2">
        {left.map((q) => (
          <button
            key={questionKey(q)}
            onClick={() => onAdd(q)}
            className="rounded-full border border-line-strong bg-white/[0.03] px-3.5 py-1.5 text-left text-sm transition-colors hover:border-brand/60 hover:bg-brand/10"
          >
            {describe(q, names)}
          </button>
        ))}
      </div>
    </div>
  )
}

function AnswerCard({ text, answer, base, onRemove }: { text: string; answer?: Answer; base?: Answer; onRemove: () => void }) {
  const p = answer?.probability
  const delta = p != null && base?.probability != null ? p - base.probability : null
  return (
    <div className="rise flex flex-col gap-2 rounded-2xl border border-line bg-black/20 p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-ink">{text}</p>
        <button onClick={onRemove} aria-label={`Remove: ${text}`} className="-mr-1 -mt-1 rounded px-1.5 text-muted hover:bg-hover hover:text-ink">
          ×
        </button>
      </div>
      {answer?.error ? (
        <p className="text-sm text-critical">{answer.error}</p>
      ) : p == null ? (
        <p className="text-sm text-muted">Working it out…</p>
      ) : (
        <>
          <div className="flex items-baseline gap-2">
            <span className="display text-4xl">{chance(p)}</span>
            <span className="text-sm text-ink-2">{verbal(p)}</span>
            {delta != null && Math.abs(delta) >= 0.005 && <Delta value={delta} />}
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.06]" aria-hidden>
            <div className="fill h-1.5 rounded-full bg-s1" style={{ width: `${p * 100}%` }} />
          </div>
          {answer?.happened != null &&
            (answer.happened ? (
              <span className="text-sm text-good">✓ It happened</span>
            ) : (
              <span className="text-sm text-ink-2">✗ It didn't happen</span>
            ))}
        </>
      )}
    </div>
  )
}

function Delta({ value, unit = 'pts' }: { value: number; unit?: string }) {
  const up = value > 0
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs ${up ? 'text-good' : 'text-critical'}`}>
      {up ? <ArrowUp /> : <ArrowDown />}
      {up ? '+' : '−'}
      {Math.abs(value * 100).toFixed(0)} {unit}
      <span className="sr-only">{up ? 'higher' : 'lower'} than the prediction without your what-if</span>
    </span>
  )
}

// ------------------------------------------------------------------- what-if editor

function WhatIf({
  field,
  scenario,
  onChange,
  base,
  result,
  error,
  busy,
}: {
  field: RaceField
  scenario: Scenario | null
  onChange: React.Dispatch<React.SetStateAction<Scenario | null>>
  base?: SimulateResponse
  result?: SimulateResponse
  error: Error | null
  busy: boolean
}) {
  const initial = field.drivers.map((d) => d.id)
  const grid = scenario?.grid ?? initial
  const s: Required<Scenario> = {
    grid,
    pit_lane: scenario?.pit_lane ?? [],
    out: scenario?.out ?? [],
    retire: scenario?.retire ?? [],
    chaos: scenario?.chaos ?? 1,
  }
  const byId = useMemo(() => new Map(field.drivers.map((d) => [d.id, d])), [field.drivers])

  if (field.completed) {
    return (
      <Card title="What if…">
        <p className="text-ink-2">
          What-ifs are for upcoming races. This race has been run, and today's model has already
          learned from its result, so a what-if here wouldn't be a fair test.
        </p>
      </Card>
    )
  }

  // Every change builds on the latest scenario (functional updates), so quick successive
  // edits (a toggle, then the slider) never overwrite each other.
  const full = (prev: Scenario | null): Required<Scenario> => ({
    grid: prev?.grid ?? initial,
    pit_lane: prev?.pit_lane ?? [],
    out: prev?.out ?? [],
    retire: prev?.retire ?? [],
    chaos: prev?.chaos ?? 1,
  })
  const update = (patch: (cur: Required<Scenario>) => Partial<Scenario>) =>
    onChange((prev) => {
      const cur = full(prev)
      return { ...cur, ...patch(cur) }
    })
  const move = (i: number, dir: -1 | 1) =>
    update((cur) => {
      const g = [...cur.grid!]
      const j = i + dir
      if (j < 0 || j >= g.length) return {}
      ;[g[i], g[j]] = [g[j], g[i]]
      return { grid: g }
    })
  const toggle = (key: 'pit_lane' | 'out' | 'retire', id: string) =>
    update((cur) => ({
      [key]: cur[key].includes(id) ? cur[key].filter((x) => x !== id) : [...cur[key], id],
    }))

  const baseRows = new Map(base?.rows.map((r) => [r.driver.id, r]))
  const rows = result?.rows ?? []

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Card
        title="Change the race"
        subtitle={
          field.grid_source === 'qualifying'
            ? 'Starting from the qualifying order. Move drivers, send them to the pit lane, or rule them out.'
            : 'No qualifying yet: this is the predicted order. Arrange it as a hypothetical qualifying result.'
        }
        actions={
          scenario && (
            <button onClick={() => onChange(null)} className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-hover">
              Reset
            </button>
          )
        }
      >
        <ol className="space-y-1">
          {grid.map((id, i) => {
            const d = byId.get(id)
            const isOut = s.out.includes(id)
            return (
              <li key={id} className={`flex items-center gap-2 rounded-lg px-1 py-1 ${isOut ? 'opacity-50' : 'hover:bg-hover'}`}>
                <span className="tabular w-7 text-right text-sm text-ink-2">{i + 1}</span>
                <div className="flex flex-col">
                  <button aria-label={`Move ${d?.name} up`} onClick={() => move(i, -1)} disabled={i === 0} className="rounded p-1 leading-none text-muted hover:bg-hover hover:text-ink disabled:opacity-30">
                    <ArrowUp />
                  </button>
                  <button aria-label={`Move ${d?.name} down`} onClick={() => move(i, 1)} disabled={i === grid.length - 1} className="rounded p-1 leading-none text-muted hover:bg-hover hover:text-ink disabled:opacity-30">
                    <ArrowDown />
                  </button>
                </div>
                <span className="min-w-0 flex-1 truncate text-sm">
                  <span className="font-semibold">{d?.code}</span>
                  <span className="ml-2 hidden text-ink-2 sm:inline">{d?.team_name}</span>
                </span>
                <Toggle on={s.pit_lane.includes(id)} onClick={() => toggle('pit_lane', id)} label="Pit lane" />
                <Toggle on={s.retire.includes(id)} onClick={() => toggle('retire', id)} label="Retires" />
                <Toggle on={isOut} onClick={() => toggle('out', id)} label="Out" />
              </li>
            )
          })}
        </ol>
        <label className="mt-5 block text-sm">
          <span className="flex justify-between text-ink-2">
            Race unpredictability
            <span className="text-ink">
              {s.chaos === 1 ? 'Normal' : s.chaos < 1 ? 'Calmer than usual' : s.chaos >= 2 ? 'Chaotic (rain, safety cars)' : 'Messier than usual'} ×{num(s.chaos, 2)}
            </span>
          </span>
          <input
            type="range"
            min={0.5}
            max={3}
            step={0.25}
            value={s.chaos}
            onChange={(e) => {
              const chaos = Number(e.target.value)
              update(() => ({ chaos }))
            }}
            className="mt-2 w-full accent-[var(--s1)]"
          />
        </label>
        <p className="mt-3 text-xs text-muted">
          Unpredictability is an assumption you set, not something the model learned. Big moves
          (the fastest car from the pit lane, say) have few precedents since 2014, so treat those
          answers as rough.
        </p>
      </Card>

      <Card
        // On phones the outcome comes first, so a change's effect is visible without scrolling.
        className={`order-first lg:order-none ${busy ? 'opacity-70' : ''} transition-opacity`}
        title="How the race plays out"
        subtitle={scenario ? 'Compared with the prediction without your changes.' : 'Make a change to see its effect.'}
      >
        {error ? (
          <ErrorState error={error} />
        ) : !scenario ? (
          <p className="text-sm text-ink-2">Move a driver, send someone to the pit lane, or turn up the chaos.</p>
        ) : !result ? (
          <Loading what="simulation" />
        ) : (
          <div className="-mx-4 overflow-x-auto sm:mx-0">
            <table className="w-full min-w-[360px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-ink-2">
                  <th className="py-2 pl-4 font-medium sm:pl-0">#</th>
                  <th className="px-2 font-medium">Driver</th>
                  <th className="px-2 text-right font-medium">Win</th>
                  <th className="px-2 pr-4 text-right font-medium sm:pr-0">Podium</th>
                </tr>
              </thead>
              <tbody>
                {rows.slice(0, 12).map((r) => {
                  const b = baseRows.get(r.driver.id)
                  return (
                    <tr key={r.driver.id} className="border-b border-line last:border-0">
                      <td className="tabular py-1.5 pl-4 text-ink-2 sm:pl-0">{r.pred_rank}</td>
                      <td className="px-2 font-semibold">{r.driver.code}</td>
                      <td className="tabular px-2 text-right">
                        {chance(r.p_win)} {b && Math.abs(r.p_win - b.p_win) >= 0.005 && <Delta value={r.p_win - b.p_win} />}
                      </td>
                      <td className="tabular px-2 pr-4 text-right sm:pr-0">
                        {chance(r.p_podium)} {b && Math.abs(r.p_podium - b.p_podium) >= 0.005 && <Delta value={r.p_podium - b.p_podium} />}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {rows.length > 12 && <p className="mt-2 text-xs text-muted">Top 12 shown.</p>}
          </div>
        )}
      </Card>
    </div>
  )
}

function Toggle({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={on}
      className={`rounded-md border px-2 py-0.5 text-xs transition-colors ${
        on ? 'border-ink bg-ink text-card' : 'border-line text-ink-2 hover:bg-hover'
      }`}
    >
      {label}
    </button>
  )
}
