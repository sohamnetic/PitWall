// Mirrors backend/f1p/api/schemas.py

export type Stage = 'pre' | 'post'

export interface DriverRef {
  id: string
  code: string | null
  name: string
  number?: number | null
  team_id: string | null
  team_name: string | null
}

export interface RaceSummary {
  id: string
  season: number
  round: number
  name: string
  circuit_id: string
  circuit_name: string
  locality: string | null
  country: string | null
  race_date: string
  race_start_utc: string | null
  quali_start_utc: string | null
  weekend_format: string
  status: 'upcoming' | 'completed'
  result_source: 'official' | 'none'
  qualifying_source: 'official' | 'provisional' | 'none'
  latest_predictions: Record<Stage, number | null>
  winner: DriverRef | null
  favourite: { driver: DriverRef; p_win: number; stage: Stage; live: boolean } | null
}

export interface Metrics {
  spearman: number
  pos_mae: number
  winner_hit: number
  top3_hit: number
  top10_hit: number
  win_logloss: number
  win_brier: number
  podium_logloss: number
  podium_brier: number
  points_logloss: number
  points_brier: number
}

export interface Score {
  scored_at: string
  n_drivers: number
  model: Metrics
  baseline_name: string
  baseline: Metrics
}

export interface PredictionRow {
  driver: DriverRef
  pred_rank: number
  expected_pos: number
  p_win: number
  p_podium: number
  p_points: number
  position_probs: number[]
  actual_position: number | null
}

export interface SnapshotMeta {
  id: number
  race_id: string
  stage: Stage
  created_at: string
  cutoff_utc: string
  made_before_cutoff: boolean
  model_trained_through: string
  temperature: number
  model_version: string
  scored: boolean
}

export interface Snapshot extends SnapshotMeta {
  rows: PredictionRow[]
  score: Score | null
}

export interface ResultRow {
  driver: DriverRef
  grid: number | null
  position: number | null
  position_text: string
  position_order: number
  points: number
  laps: number | null
  status: string
  source: string | null
}

export interface QualifyingRow {
  driver: DriverRef
  position: number
  q1_s: number | null
  q2_s: number | null
  q3_s: number | null
  source: string | null
}

export interface RaceDetail {
  race: RaceSummary
  snapshots: SnapshotMeta[]
  results: ResultRow[]
  sprint: ResultRow[]
  qualifying: QualifyingRow[]
}

export interface BacktestModelSummary {
  model: string
  races: number
  metrics: Metrics
}

export interface SeasonPoint {
  model: string
  season: number
  spearman: number
  win_logloss: number
}

export interface CalibrationBin {
  predicted: number
  observed: number
  n: number
}

export interface StageBacktest {
  summary: BacktestModelSummary[]
  by_season: SeasonPoint[]
  calibration: Record<string, CalibrationBin[]>
}

export interface TrackRecordEntry {
  snapshot_id: number
  race_id: string
  race_name: string
  stage: Stage
  created_at: string
  live: boolean
  spearman: number | null
  winner_hit: number | null
  win_logloss: number | null
  baseline_name: string | null
  baseline_spearman: number | null
  baseline_win_logloss: number | null
}

export interface Performance {
  backtest: Partial<Record<Stage, StageBacktest>>
  track_record: TrackRecordEntry[]
}

export interface DriverResult {
  race_id: string
  race_name: string
  team_id: string
  grid: number | null
  quali_position: number | null
  position: number | null
  position_text: string
  points: number
}

export interface DriverPrediction {
  snapshot_id: number
  race_id: string
  stage: Stage
  pred_rank: number
  p_win: number
  p_podium: number
  actual_position: number | null
}

export interface DriverDetail {
  driver: DriverRef
  nationality: string | null
  season: number
  season_points: number
  recent_results: DriverResult[]
  predictions: DriverPrediction[]
}

// ------------------------------------------------------------ ask the model / what-if

export type QuestionKind =
  | 'top_k'
  | 'position'
  | 'ahead'
  | 'team_top_k'
  | 'team_wins'
  | 'podium_exact'
  | 'dnf'

export interface Question {
  kind: QuestionKind
  driver?: string | null
  other?: string | null
  team?: string | null
  k?: number | null
  drivers?: string[]
}

export interface Scenario {
  grid?: string[] | null
  pit_lane?: string[]
  out?: string[]
  retire?: string[]
  chaos?: number
}

export interface SimulateRequest {
  stage?: Stage | null
  scenario?: Scenario | null
  questions: Question[]
}

export interface Answer {
  question: Question
  probability: number | null
  happened: boolean | null
  error: string | null
}

export interface SimulateResponse {
  race_id: string
  source: 'snapshot' | 'scenario'
  snapshot_id: number | null
  stage: Stage
  n_sims: number
  temperature: number
  grid: string[] | null
  rows: PredictionRow[]
  answers: Answer[]
}

export interface RaceField {
  race_id: string
  completed: boolean
  grid_source: 'qualifying' | 'predicted'
  drivers: DriverRef[]
  teams: { id: string; name: string }[]
}

// ------------------------------------------------------------------- beat the model

export interface PlayerCreated {
  id: number
  nickname: string
  token: string
}

export interface PickOut {
  race_id: string
  podium: DriverRef[]
  updated_at: string
  locked: boolean
  points: number | null
}

export interface PickHistoryEntry extends PickOut {
  race_name: string
  actual_podium: DriverRef[] | null
}

export interface PicksSummary {
  race_id: string
  locked: boolean
  lock_at_utc: string | null
  n_players: number
  winner_picks: { driver: DriverRef; count: number }[]
  crowd_podium: DriverRef[]
  model_podium: DriverRef[] | null
  actual_podium: DriverRef[] | null
  crowd_avg_points: number | null
  model_points: number | null
}

export interface LeaderboardEntry {
  rank: number
  name: string
  is_model: boolean
  points: number
  races: number
  exact: number
}
