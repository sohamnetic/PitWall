import { Link } from 'react-router'
import { isNotFound, useNextRace } from '../api/hooks'
import RaceView from '../components/RaceView'
import { Card, ErrorState, Loading } from '../components/ui'

export default function NextRace() {
  const next = useNextRace()
  if (next.isPending) return <Loading what="the next race" />
  if (isNotFound(next.error))
    return (
      <Card title="No upcoming race">
        <p className="text-ink-2">
          The season is over. Browse past predictions in the <Link to="/archive" className="underline">race archive</Link>.
        </p>
      </Card>
    )
  if (next.error) return <ErrorState error={next.error} />
  return <RaceView raceId={next.data.id} />
}
