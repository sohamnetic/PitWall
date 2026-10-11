import { useEffect } from 'react'

export function usePageTitle(title: string | undefined) {
  useEffect(() => {
    document.title = title ? `${title} · PitWall` : 'PitWall · race predictions'
  }, [title])
}
