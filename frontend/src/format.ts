/** Formatting helpers and display labels shared across pages. */

export function pct(p: number | null | undefined, digits = 0): string {
  if (p == null || Number.isNaN(p)) return '–'
  if (p > 0 && p < 0.005) return '<1%'
  if (p > 0.995 && p < 1) return '>99%'
  return `${(p * 100).toFixed(digits)}%`
}

/** A simulated chance. Never "0%" or "100%": a place no simulated race produced is unlikely,
 *  not impossible (10,000 races can't show a 1-in-50,000 outcome), so tiny values read "<1%". */
export function chance(p: number | null | undefined, digits = 0): string {
  if (p == null || Number.isNaN(p)) return '–'
  const step = digits ? 10 ** -digits : 1 // smallest value shown, in percent
  const v = p * 100
  if (v < step / 2) return `<${step}%`
  if (v > 100 - step / 2) return `>${100 - step}%`
  return `${v.toFixed(digits)}%`
}

export function num(v: number | null | undefined, digits = 2): string {
  if (v == null || Number.isNaN(v)) return '–'
  return v.toFixed(digits)
}

/** Local date and time for a naive-UTC timestamp from the API. */
export function localTime(utc: string | null | undefined, withDate = true): string {
  if (!utc) return '–'
  const d = new Date(utc.endsWith('Z') ? utc : `${utc}Z`)
  return d.toLocaleString(undefined, {
    ...(withDate ? { weekday: 'short', day: 'numeric', month: 'short' } : {}),
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function shortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
  })
}

export const BASELINE_LABEL: Record<string, string> = {
  model: 'Model',
  grid: 'Grid order',
  championship: 'Championship order',
  practice: 'Fastest in practice',
  team_form: 'Team form',
  last_race: 'Last race order',
  uniform: 'Uniform (knows nothing)',
}

export const STAGE_LABEL = { pre: 'Before qualifying', post: 'After qualifying' } as const

