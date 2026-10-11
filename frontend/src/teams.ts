/** Team identity colours (approximate livery colours), used only as small stripes next to a
 * driver or team name for recognition. Never used to encode data in charts, and the name
 * always appears beside the stripe, so nothing relies on colour alone. */
const TEAM_COLORS: Record<string, string> = {
  red_bull: '#3671c6',
  ferrari: '#e8002d',
  mercedes: '#27f4d2',
  mclaren: '#ff8000',
  aston_martin: '#229971',
  alpine: '#0093cc',
  williams: '#64c4ff',
  rb: '#6692ff',
  haas: '#b6babd',
  audi: '#bb0a30',
  sauber: '#52e252',
  cadillac: '#c9a227',
  // Historic names (archive pages).
  alphatauri: '#5e8faa',
  toro_rosso: '#469bff',
  alfa: '#c92d4b',
  racing_point: '#f596c8',
  force_india: '#f596c8',
  renault: '#fff500',
  lotus_f1: '#ffb800',
  manor: '#323232',
  marussia: '#6e0000',
  caterham: '#10518f',
}

export function teamColor(teamId: string | null | undefined): string {
  return (teamId && TEAM_COLORS[teamId]) || '#6b6b78'
}

/** Display name without the redundant suffix ("Haas F1 Team" -> "Haas"). */
export function teamName(name: string | null | undefined): string {
  return (name ?? '').replace(/ F1 Team$/, '').replace(/^RB$/, 'Racing Bulls')
}
