import { useParams } from 'react-router'
import RaceView from '../components/RaceView'

export default function RacePage() {
  const { raceId } = useParams()
  return <RaceView key={raceId} raceId={raceId!} />
}
