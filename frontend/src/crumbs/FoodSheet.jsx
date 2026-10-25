import { useEffect, useRef } from 'react'
import { CompareChart, PickRow } from './CompareChart.jsx'
import { GoHere } from './GoHere.jsx'
import { IconBack, IconChart, IconList, IconStar } from './icons.jsx'
import { SpotList } from './SpotList.jsx'
import { useSnapSheet } from './useSnapSheet.js'

/**
 * Draggable sheet for one food type (peek / half / full). Shows the compare chart, the ranked list, or the
 * "go here" view for one spot.
 */
export function FoodSheet({ cuisine, view, onView, sort, onSort, spotId, onOpenSpot, onCloseSpot, snap, onSnap, sheetRef }) {
  const { height, dragging, dragProps } = useSnapSheet(snap, onSnap)
  const spot = cuisine.spots.find((s) => s.id === spotId) ?? null
  const body = useRef(null)

  useEffect(() => {
    body.current?.scrollTo(0, 0)
  }, [view, spotId, cuisine.id])

  useEffect(() => {
    if (!spot) return
    const onKey = (e) => e.key === 'Escape' && onCloseSpot()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [spot, onCloseSpot])

  return (
    <section
      ref={sheetRef}
      className={`sheet food-sheet${dragging ? ' is-dragging' : ''}`}
      style={{ height }}
      aria-label={`${cuisine.label} spots`}
    >
      <div className="food-head" {...dragProps}>
        <button
          className="sheet-handle"
          onClick={() => onSnap(snap === 'half' ? 'full' : 'half')}
          aria-label={snap === 'full' ? 'Shrink sheet' : 'Expand sheet'}
        >
          <span />
        </button>
        {spot ? (
          <div className="food-title-row">
            <button className="back-btn" onClick={onCloseSpot} aria-label="Back">
              <IconBack />
            </button>
            {spot.pick && (
              <span className="pick-tag">
                <IconStar size={12} />
                crumbs pick · {cuisine.label}
              </span>
            )}
          </div>
        ) : (
          <div className="food-title-row">
            <div className="food-title-copy">
              <h2 className="food-title">{cuisine.label}</h2>
              <p className="food-sub">
                {cuisine.spots.length} spots · {cuisine.reviewsRead.toLocaleString()} reviews read
              </p>
            </div>
            <button className="pill-btn" onClick={() => onView(view === 'list' ? 'compare' : 'list')}>
              {view === 'list' ? <IconChart /> : <IconList />}
              {view === 'list' ? 'Chart' : 'List'}
            </button>
          </div>
        )}
      </div>

      <div className="food-body" ref={body}>
        {spot ? (
          <GoHere key={spot.id} spot={spot} cuisine={cuisine} />
        ) : view === 'list' ? (
          <SpotList cuisine={cuisine} sort={sort} onSort={onSort} onOpenSpot={onOpenSpot} />
        ) : (
          <>
            <PickRow cuisine={cuisine} onOpenSpot={onOpenSpot} />
            <CompareChart cuisine={cuisine} onOpenSpot={onOpenSpot} />
          </>
        )}
      </div>
    </section>
  )
}
