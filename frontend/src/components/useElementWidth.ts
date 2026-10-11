import { useLayoutEffect, useRef, useState } from 'react'

/** Track an element's content width, for SVG charts that lay out in real pixels. */
export function useElementWidth<T extends HTMLElement>(initial = 320) {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(initial)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    // Measure synchronously before paint; the observer alone can miss the first layout
    // (e.g. in a background tab where resize callbacks are deferred).
    setWidth(Math.floor(el.getBoundingClientRect().width))
    const ro = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}
