import type { DriverRef, Question, QuestionKind, RaceField } from './api/types'

export const KIND_LABEL: Record<QuestionKind, string> = {
  top_k: 'Finish in the top…',
  position: 'Finish exactly in position…',
  ahead: 'Finish ahead of another driver',
  team_top_k: 'Both team cars in the top…',
  team_wins: 'Winner drives for a team',
  podium_exact: 'Exact podium (P1, P2, P3)',
  dnf: 'Retire from the race (DNF)',
}

export interface Names {
  driver: (id: string | null | undefined) => string
  team: (id: string | null | undefined) => string
}

export function namesFor(field: RaceField | undefined): Names {
  const drivers = new Map(field?.drivers.map((d) => [d.id, d]))
  const teams = new Map(field?.teams.map((t) => [t.id, t.name]))
  return {
    driver: (id) => (id ? (drivers.get(id)?.name ?? id) : '?'),
    team: (id) => (id ? (teams.get(id) ?? id) : '?'),
  }
}

function topK(k: number | null | undefined): string {
  if (k === 1) return 'win'
  if (k === 3) return 'finish on the podium'
  if (k === 10) return 'score points (top 10)'
  return `finish in the top ${k}`
}

/** The question as a plain-English sentence. */
export function describe(q: Question, n: Names): string {
  switch (q.kind) {
    case 'top_k':
      return `Will ${n.driver(q.driver)} ${topK(q.k)}?`
    case 'position':
      return `Will ${n.driver(q.driver)} finish exactly P${q.k}?`
    case 'ahead':
      return `Will ${n.driver(q.driver)} finish ahead of ${n.driver(q.other)}?`
    case 'team_top_k':
      if (q.k === 2) return `Will ${n.team(q.team)} finish 1–2?`
      if (q.k === 3) return `Will both ${n.team(q.team)} cars reach the podium?`
      if (q.k === 10) return `Will both ${n.team(q.team)} cars score points?`
      return `Will both ${n.team(q.team)} cars finish in the top ${q.k}?`
    case 'team_wins':
      return `Will the winner drive for ${n.team(q.team)}?`
    case 'podium_exact': {
      const [a, b, c] = q.drivers ?? []
      return `Will the podium be exactly ${n.driver(a)}, ${n.driver(b)}, ${n.driver(c)}?`
    }
    case 'dnf':
      return `Will ${n.driver(q.driver)} retire?`
  }
}

/** Plain-language reading of a probability. */
export function verbal(p: number): string {
  if (p < 0.02) return 'very unlikely'
  if (p < 0.2) return `about 1 in ${Math.round(1 / p)}`
  if (p < 0.4) return 'unlikely'
  if (p < 0.6) return 'close to a coin flip'
  if (p < 0.8) return 'more likely than not'
  if (p < 0.97) return 'likely'
  return 'almost certain'
}

/** Starter questions built from the actual field: the favourites and a teammate battle. */
export function suggestions(field: RaceField, favourites: DriverRef[]): Question[] {
  const [first, second] = favourites
  const out: Question[] = []
  if (first) out.push({ kind: 'top_k', driver: first.id, k: 1 })
  if (first && second) out.push({ kind: 'ahead', driver: second.id, other: first.id })
  const team = first?.team_id
  if (team) out.push({ kind: 'team_top_k', team, k: 3 })
  const mates = field.drivers.filter((d) => d.team_id === second?.team_id && d.id !== second?.id)
  if (second && mates[0]) out.push({ kind: 'ahead', driver: mates[0].id, other: second.id })
  const midfield = favourites[5]
  if (midfield) out.push({ kind: 'top_k', driver: midfield.id, k: 3 })
  if (favourites.length >= 3)
    out.push({ kind: 'podium_exact', drivers: favourites.slice(0, 3).map((d) => d.id) })
  return out
}

export function questionKey(q: Question): string {
  return JSON.stringify([q.kind, q.driver ?? null, q.other ?? null, q.team ?? null, q.k ?? null, q.drivers ?? []])
}
