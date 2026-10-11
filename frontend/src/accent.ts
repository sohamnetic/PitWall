import { useEffect, useSyncExternalStore } from 'react'

/** The backdrop's accent light: brand red by default, a team colour on race and driver pages. */
const DEFAULT = '#e10600'
let accent = DEFAULT
const listeners = new Set<() => void>()

function set(color: string) {
  if (color === accent) return
  accent = color
  listeners.forEach((l) => l())
}

export function useAccentColor(): string {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => accent,
  )
}

/** Tint the backdrop while this page is shown; back to brand red when it leaves. */
export function useAccent(color: string | null | undefined) {
  useEffect(() => {
    if (!color) return
    set(color)
    return () => set(DEFAULT)
  }, [color])
}
