import { useSyncExternalStore } from 'react'

/** The 'Beat the model' player for this browser. The token is the only credential. */
export interface StoredPlayer {
  id: number
  nickname: string
  token: string
}

const KEY = 'f1p.player'
const listeners = new Set<() => void>()

function read(): StoredPlayer | null {
  try {
    const raw = localStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as StoredPlayer) : null
  } catch {
    return null
  }
}

let current = read()

export function setPlayer(p: StoredPlayer | null) {
  current = p
  try {
    if (p) localStorage.setItem(KEY, JSON.stringify(p))
    else localStorage.removeItem(KEY)
  } catch {
    /* private mode: keep it in memory for this visit */
  }
  listeners.forEach((l) => l())
}

export function usePlayer(): StoredPlayer | null {
  return useSyncExternalStore(
    (l) => {
      listeners.add(l)
      return () => listeners.delete(l)
    },
    () => current,
  )
}
