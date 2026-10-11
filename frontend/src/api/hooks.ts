import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { usePlayer } from '../player'
import { ApiError, apiGet, apiSend } from './client'
import type {
  DriverDetail,
  DriverRef,
  LeaderboardEntry,
  Performance,
  PickHistoryEntry,
  PickOut,
  PicksSummary,
  PlayerCreated,
  RaceDetail,
  RaceField,
  RaceSummary,
  SimulateRequest,
  SimulateResponse,
  Snapshot,
  Stage,
} from './types'

export { ApiError }

export const isNotFound = (e: unknown) => e instanceof ApiError && e.status === 404

const noRetryOnClientError = (count: number, error: Error) =>
  !(error instanceof ApiError && error.status < 500) && count < 2

export const useSeasons = () =>
  useQuery({ queryKey: ['seasons'], queryFn: () => apiGet<number[]>('/seasons') })

export const useNextRace = () =>
  useQuery({
    queryKey: ['races', 'next'],
    queryFn: () => apiGet<RaceSummary>('/races/next'),
    retry: noRetryOnClientError,
  })

export const useSeasonRaces = (season: number | undefined) =>
  useQuery({
    queryKey: ['seasons', season, 'races'],
    queryFn: () => apiGet<RaceSummary[]>(`/seasons/${season}/races`),
    enabled: season !== undefined,
    placeholderData: keepPreviousData,
  })

export const useRace = (raceId: string | undefined) =>
  useQuery({
    queryKey: ['races', raceId],
    queryFn: () => apiGet<RaceDetail>(`/races/${encodeURIComponent(raceId!)}`),
    enabled: !!raceId,
    retry: noRetryOnClientError,
  })

export const useSnapshot = (id: number | null | undefined) =>
  useQuery({
    queryKey: ['predictions', id],
    queryFn: () => apiGet<Snapshot>(`/predictions/${id}`),
    enabled: id != null,
    placeholderData: keepPreviousData,
  })

export const usePerformance = () =>
  useQuery({ queryKey: ['performance'], queryFn: () => apiGet<Performance>('/performance') })

export const useDrivers = (season?: number) =>
  useQuery({
    queryKey: ['drivers', season],
    queryFn: () => apiGet<DriverRef[]>(season ? `/drivers?season=${season}` : '/drivers'),
  })

export const useDriver = (driverId: string | undefined) =>
  useQuery({
    queryKey: ['drivers', 'detail', driverId],
    queryFn: () => apiGet<DriverDetail>(`/drivers/${encodeURIComponent(driverId!)}`),
    enabled: !!driverId,
    retry: noRetryOnClientError,
  })

// ------------------------------------------------------------ ask the model / what-if

export const useRaceField = (raceId: string | undefined) =>
  useQuery({
    queryKey: ['races', raceId, 'field'],
    queryFn: () => apiGet<RaceField>(`/races/${encodeURIComponent(raceId!)}/field`),
    enabled: !!raceId,
    retry: noRetryOnClientError,
  })

/** Simulation results are a pure function of the request, so they cache by its content. */
export const useSimulation = (raceId: string | undefined, body: SimulateRequest | null) =>
  useQuery({
    queryKey: ['simulate', raceId, body],
    queryFn: () =>
      apiSend<SimulateResponse>('POST', `/races/${encodeURIComponent(raceId!)}/simulate`, body),
    enabled: !!raceId && body !== null,
    placeholderData: keepPreviousData,
    retry: noRetryOnClientError,
    staleTime: 5 * 60_000,
  })

// ------------------------------------------------------------------- beat the model

function authHeaders(token: string | undefined): Record<string, string> {
  return token ? { 'X-Player-Token': token } : {}
}

export const useCreatePlayer = () =>
  useMutation({
    mutationFn: (nickname: string) => apiSend<PlayerCreated>('POST', '/players', { nickname }),
  })

export const useMyPick = (raceId: string | undefined) => {
  const player = usePlayer()
  return useQuery({
    queryKey: ['picks', raceId, player?.id],
    queryFn: () =>
      apiGet<PickOut>(`/races/${encodeURIComponent(raceId!)}/picks/me`, authHeaders(player?.token)),
    enabled: !!raceId && !!player,
    retry: noRetryOnClientError,
  })
}

export const useMyPicks = () => {
  const player = usePlayer()
  return useQuery({
    queryKey: ['picks', 'mine', player?.id],
    queryFn: () => apiGet<PickHistoryEntry[]>('/players/me/picks', authHeaders(player?.token)),
    enabled: !!player,
    retry: noRetryOnClientError,
  })
}

export const useSavePick = (raceId: string | undefined) => {
  const player = usePlayer()
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (podium: [string, string, string]) =>
      apiSend<PickOut>(
        'PUT',
        `/races/${encodeURIComponent(raceId!)}/picks/me`,
        { p1: podium[0], p2: podium[1], p3: podium[2] },
        authHeaders(player?.token),
      ),
    onSuccess: (pick) => {
      qc.setQueryData(['picks', raceId, player?.id], pick)
      qc.invalidateQueries({ queryKey: ['picks', 'summary', raceId] })
      qc.invalidateQueries({ queryKey: ['picks', 'mine'] })
    },
  })
}

export const usePicksSummary = (raceId: string | undefined) =>
  useQuery({
    queryKey: ['picks', 'summary', raceId],
    queryFn: () => apiGet<PicksSummary>(`/races/${encodeURIComponent(raceId!)}/picks/summary`),
    enabled: !!raceId,
  })

export const useLeaderboard = (season?: number) =>
  useQuery({
    queryKey: ['leaderboard', season],
    queryFn: () => apiGet<LeaderboardEntry[]>(season ? `/leaderboard?season=${season}` : '/leaderboard'),
  })

export type { Stage }
