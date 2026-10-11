import { Link } from 'react-router'
import { useDrivers } from '../api/hooks'
import type { DriverRef } from '../api/types'
import { ErrorState, Loading, PageHeader } from '../components/ui'
import { teamColor, teamName } from '../teams'
import { usePageTitle } from '../usePageTitle'

export default function Drivers() {
  usePageTitle('Drivers')
  const drivers = useDrivers()
  if (drivers.isPending) return <Loading what="drivers" />
  if (drivers.error) return <ErrorState error={drivers.error} />

  const teams = new Map<string, DriverRef[]>()
  for (const d of drivers.data) {
    const key = d.team_id ?? 'unknown'
    teams.set(key, [...(teams.get(key) ?? []), d])
  }
  return (
    <div className="space-y-8">
      <PageHeader eyebrow="The grid" title="Drivers" subtitle="This season's line-up. Pick a driver for their form and prediction history." />
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[...teams.entries()].map(([teamId, list], i) => (
          <section key={teamId} className="panel rise overflow-hidden" style={{ animationDelay: `${i * 40}ms` }}>
            <div className="h-1" style={{ background: teamColor(teamId) }} aria-hidden />
            <div className="p-4">
              <div className="eyebrow">{teamName(list[0].team_name)}</div>
              <ul className="mt-3 grid grid-cols-2 gap-3">
                {list.map((d) => (
                  <li key={d.id}>
                    <Link
                      to={`/drivers/${d.id}`}
                      className="group relative block overflow-hidden rounded-xl border border-line bg-black/20 p-3 transition-colors hover:border-line-strong hover:bg-hover"
                    >
                      <span
                        className="display pointer-events-none absolute -right-1 -top-3 text-6xl opacity-25"
                        style={{ color: teamColor(teamId) }}
                        aria-hidden
                      >
                        {d.number ?? ''}
                      </span>
                      <div className="display relative text-2xl">{d.code}</div>
                      <div className="relative truncate text-sm text-ink-2 group-hover:text-ink">{d.name}</div>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
