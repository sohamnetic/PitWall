import { Suspense, lazy, type ReactNode } from 'react'
import { NavLink, Route, Routes, useLocation } from 'react-router'
import Backdrop from './components/Backdrop'
import ErrorBoundary from './components/ErrorBoundary'
import { AskIcon, ChartIcon, FlagIcon, ListIcon, PeopleIcon, TrophyIcon } from './components/icons'
import { Loading } from './components/ui'
import Drivers from './pages/Drivers'
import NextRace from './pages/NextRace'
import RaceArchive from './pages/RaceArchive'
import RacePage from './pages/RacePage'

// Heavier pages load on demand to keep the first screen fast.
const ModelPerformance = lazy(() => import('./pages/ModelPerformance'))
const Driver = lazy(() => import('./pages/Driver'))
const Ask = lazy(() => import('./pages/Ask'))
const Play = lazy(() => import('./pages/Play'))

interface NavItem {
  to: string
  label: string
  short: string
  icon: ReactNode
  end: boolean
  mobile: boolean
}

const NAV: NavItem[] = [
  { to: '/', label: 'Next race', short: 'Race', icon: <FlagIcon />, end: true, mobile: true },
  { to: '/ask', label: 'Ask the model', short: 'Ask', icon: <AskIcon />, end: false, mobile: true },
  { to: '/play', label: 'Beat the model', short: 'Play', icon: <TrophyIcon />, end: false, mobile: true },
  { to: '/archive', label: 'Races', short: 'Races', icon: <ListIcon />, end: false, mobile: true },
  { to: '/performance', label: 'Track record', short: 'Record', icon: <ChartIcon />, end: true, mobile: true },
  { to: '/drivers', label: 'Drivers', short: 'Drivers', icon: <PeopleIcon />, end: false, mobile: false },
]

export default function App() {
  const location = useLocation()
  return (
    <div className="relative min-h-screen pb-20 lg:pb-0">
      <Backdrop />
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-card focus:px-3 focus:py-2">
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-page/80 backdrop-blur-xl">
        <div className="h-0.5 bg-gradient-to-r from-brand via-brand-hot to-transparent" aria-hidden />
        <nav aria-label="Main" className="mx-auto flex max-w-6xl items-center gap-x-6 px-4">
          <NavLink to="/" className="mr-2 flex shrink-0 items-center gap-2 py-3" aria-label="PitWall, home">
            <Logo />
            <span className="display text-lg uppercase leading-none tracking-wide">
              Pit<span className="text-brand-hot">Wall</span>
            </span>
          </NavLink>
          <div className="hidden items-stretch gap-x-5 self-stretch lg:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `relative flex items-center text-sm font-medium transition-colors ${
                    isActive
                      ? 'text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:rounded-full after:bg-brand-hot'
                      : 'text-ink-2 hover:text-ink'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
          <NavLink to="/drivers" className="ml-auto text-sm font-medium text-ink-2 hover:text-ink lg:hidden">
            Drivers
          </NavLink>
        </nav>
      </header>

      <main id="main" className="mx-auto max-w-6xl px-4 py-6 sm:py-10">
        <ErrorBoundary resetKey={location.pathname}>
          <Suspense fallback={<Loading what="page" />}>
            <Routes>
              <Route path="/" element={<NextRace />} />
              <Route path="/ask" element={<Ask />} />
              <Route path="/play" element={<Play />} />
              <Route path="/archive" element={<RaceArchive />} />
              <Route path="/races/:raceId" element={<RacePage />} />
              <Route path="/performance" element={<ModelPerformance />} />
              <Route path="/drivers" element={<Drivers />} />
              <Route path="/drivers/:driverId" element={<Driver />} />
              <Route path="*" element={<p className="text-ink-2">Page not found.</p>} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>

      <div className="kerb mx-auto max-w-6xl opacity-60" aria-hidden />
      <footer className="mx-auto max-w-6xl px-4 py-6 text-xs text-muted">
        <span className="display text-sm uppercase text-ink-2">Pit<span className="text-brand-hot">Wall</span></span>{' '}
        · Probabilities come from 10,000 simulated races per prediction. Data: Jolpica &amp; FastF1.
        Independent fan project, not affiliated with Formula 1, the FIA or any team.
      </footer>

      {/* Phone navigation: a bottom tab bar within thumb reach. */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-page/90 backdrop-blur-xl lg:hidden"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <ul className="grid grid-cols-5">
          {NAV.filter((i) => i.mobile).map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `relative flex flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${
                    isActive
                      ? 'text-ink before:absolute before:inset-x-6 before:top-0 before:h-0.5 before:rounded-full before:bg-brand-hot'
                      : 'text-muted'
                  }`
                }
              >
                {item.icon}
                {item.short}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </div>
  )
}

function Logo() {
  // A slanted red tile with three rising bars: a forecast.
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
      <path d="M7 2h23l-5 28H2z" fill="var(--brand)" />
      <rect x="9" y="19" width="3.2" height="6" rx="1" fill="#fff" transform="skewX(-10)" />
      <rect x="14.5" y="14" width="3.2" height="11" rx="1" fill="#fff" transform="skewX(-10)" />
      <rect x="20" y="8" width="3.2" height="17" rx="1" fill="#fff" transform="skewX(-10)" />
    </svg>
  )
}
