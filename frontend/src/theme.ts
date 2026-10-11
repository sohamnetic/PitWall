/** Theme roles used by the SVG charts. */
export interface ThemeColors {
  card: string
  ink: string
  ink2: string
  muted: string
  grid: string
  axis: string
  s1: string
  s2: string
  s3: string
  neutralMark: string
}

/** Chart colors as CSS variable references. SVG attributes resolve var() themselves, so
 * charts follow light/dark switches without re-reading styles in JS. */
const COLORS: ThemeColors = {
  card: 'var(--card)',
  ink: 'var(--ink)',
  ink2: 'var(--ink-2)',
  muted: 'var(--muted)',
  grid: 'var(--grid)',
  axis: 'var(--axis)',
  s1: 'var(--s1)',
  s2: 'var(--s2)',
  s3: 'var(--s3)',
  neutralMark: 'var(--neutral-mark)',
}

export function useThemeColors(): ThemeColors {
  return COLORS
}

/** Sequential single-hue fill: probability 0 recedes into the card, 1 is the full blue. */
export function seqFill(p: number): string {
  const pct = Math.round(Math.min(1, Math.sqrt(p)) * 100)
  return `color-mix(in oklab, var(--s1) ${pct}%, var(--card))`
}
