import { useEffect, useRef, useState } from 'react'

// Snap points as a share of the screen height.
export const SNAPS = { peek: 0.25, half: 0.55, full: 0.9 }

// Room left for the nav bar below the map area.
const NAV_ROOM = 72

function useViewportHeight() {
  const [height, setHeight] = useState(() => window.innerHeight)
  useEffect(() => {
    const onResize = () => setHeight(window.innerHeight)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])
  return height
}

/** Pixel height of a snap point right now. */
export const snapHeight = (snap) => Math.min(Math.round(window.innerHeight * SNAPS[snap]), window.innerHeight - NAV_ROOM)

/**
 * Drag-to-snap for a bottom sheet. Spread `dragProps` on the drag area (handle + header). A drag that ends fast
 * carries on toward the next snap point; a tap is left alone so buttons in the header still work.
 */
export function useSnapSheet(snap, setSnap) {
  const vh = useViewportHeight()
  const heights = {}
  for (const [name, share] of Object.entries(SNAPS)) heights[name] = Math.min(Math.round(vh * share), vh - NAV_ROOM)

  const [dragHeight, setDragHeight] = useState(null)
  const drag = useRef(null)
  const dragged = useRef(false)

  function onPointerDown(e) {
    // One finger drives the sheet: a second finger isn't the primary pointer, so it can't take over the drag.
    if (e.button !== 0 || !e.isPrimary) return
    // A new primary pointer means the last drag never got its pointerup; drop its listeners.
    drag.current?.stop()
    dragged.current = false

    const onMove = (ev) => {
      const d = drag.current
      if (!d || ev.pointerId !== d.pointerId) return
      const dy = d.startY - ev.clientY
      if (Math.abs(dy) > 5) dragged.current = true
      if (!dragged.current) return
      d.velocity = (d.lastY - ev.clientY) / Math.max(ev.timeStamp - d.lastT, 1)
      d.lastY = ev.clientY
      d.lastT = ev.timeStamp
      setDragHeight(Math.max(heights.peek * 0.7, Math.min(d.startH + dy, heights.full + 24)))
    }
    const onUp = (ev) => {
      const d = drag.current
      if (d && ev.pointerId !== d.pointerId) return
      stop()
      drag.current = null
      setDragHeight(null)
      if (!d || !dragged.current) return
      // Project ~180ms ahead so a flick goes to the next snap point.
      const target = d.startH + (d.startY - ev.clientY) + d.velocity * 180
      const nearest = Object.keys(heights).reduce((a, b) => (Math.abs(heights[b] - target) < Math.abs(heights[a] - target) ? b : a))
      setSnap(nearest)
    }
    const stop = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
      window.removeEventListener('pointercancel', onUp)
    }

    drag.current = { pointerId: e.pointerId, startY: e.clientY, startH: heights[snap], lastY: e.clientY, lastT: e.timeStamp, velocity: 0, stop }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
    window.addEventListener('pointercancel', onUp)
  }

  // Swallow the click that ends a drag, so dragging over the List button doesn't press it.
  function onClickCapture(e) {
    if (!dragged.current) return
    dragged.current = false
    e.stopPropagation()
    e.preventDefault()
  }

  return {
    height: dragHeight ?? heights[snap],
    dragging: dragHeight !== null,
    dragProps: { onPointerDown, onClickCapture },
  }
}
