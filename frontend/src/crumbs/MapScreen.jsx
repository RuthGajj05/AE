import { useCallback, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { FallbackMap } from './FallbackMap.jsx'
import { FoodChips } from './FoodChips.jsx'
import { FoodSheet } from './FoodSheet.jsx'
import { GooglePlacesMap } from './GooglePlacesMap.jsx'
import { IconLocate, IconPin } from './icons.jsx'
import { GOOGLE_MAPS_API_KEY, getCuisine, getMockPlaces } from './places.js'
import { SearchSheet } from './SearchSheet.jsx'
import { snapHeight } from './useSnapSheet.js'

const hasKey = Boolean(GOOGLE_MAPS_API_KEY)

/**
 * Keeps `--sheet-h` on the screen in sync with whichever sheet is showing, so the recenter button and map credits
 * ride just above it, and `inset.current` so the map can keep a tapped pin out from under it.
 */
function useSheetHeight(screen, inset) {
  const observer = useRef(null)
  return useCallback(
    (el) => {
      observer.current?.disconnect()
      if (!el) return
      observer.current = new ResizeObserver(() => {
        inset.current = el.offsetHeight
        screen.current?.style.setProperty('--sheet-h', `${el.offsetHeight}px`)
      })
      observer.current.observe(el)
    },
    [screen, inset],
  )
}

/**
 * The Map tab: full-screen map, floating top bar with food chips, recenter button and the bottom sheet.
 * `controlRef` gets { openSpot(cuisine, spotId) } so other tabs can open a food type, and a spot's Go here sheet.
 */
export function MapScreen({ active, controlRef }) {
  const [places, setPlaces] = useState(() => (hasKey ? [] : getMockPlaces()))
  // 'loading' → waiting on Google Places, 'live' → real places, 'sample' → the 10 mock spots
  const [status, setStatus] = useState(hasKey ? 'loading' : 'sample')
  const [selectedId, setSelectedId] = useState(null)
  const [query, setQuery] = useState('')

  // Food type mode
  const [cuisineId, setCuisineId] = useState(null)
  const [cuisine, setCuisine] = useState(null)
  const [view, setView] = useState('compare') // 'compare' | 'list'
  const [sort, setSort] = useState('overall')
  const [spotId, setSpotId] = useState(null)
  const [snap, setSnap] = useState('half')
  const requested = useRef(null)

  // Filled in by whichever map is showing: { recenter() }
  const mapApi = useRef(null)
  const screen = useRef(null)
  const sheetInset = useRef(0)
  const sheetRef = useSheetHeight(screen, sheetInset)

  const foodMode = cuisine !== null && cuisine.id === cuisineId
  const selected = places.find((p) => p.id === selectedId) ?? null
  const openSpot = foodMode ? (cuisine.spots.find((s) => s.id === spotId) ?? null) : null

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return places
    return places.filter((p) => p.name.toLowerCase().includes(q) || p.cuisine.toLowerCase().includes(q))
  }, [places, query])

  const onLoaded = useCallback((list) => {
    setPlaces(list)
    setStatus('live')
  }, [])
  const onFailed = useCallback((err) => {
    console.warn('[crumbs] Places Nearby Search failed, showing sample places instead.', err)
    setPlaces(getMockPlaces())
    setStatus('sample')
  }, [])

  // `spotId` opens that spot's Go here sheet as soon as the food type is showing.
  const chooseCuisine = useCallback((id, spotId = null) => {
    setSelectedId(null)
    setSpotId(spotId)
    setView('compare')
    setSort('overall')
    setSnap('half')
    setCuisineId(id)
    requested.current = id
    if (!id) return setCuisine(null)
    getCuisine(id)
      .then((c) => requested.current === id && setCuisine(c))
      .catch((err) => {
        console.warn('[crumbs] Could not load food type.', err)
        if (requested.current === id) setCuisineId(null)
      })
  }, [])

  useImperativeHandle(controlRef, () => ({ openSpot: chooseCuisine }), [chooseCuisine])

  // A map tap (id null) also closes an open food spot.
  const selectPlace = useCallback((id) => {
    setSelectedId(id)
    if (id === null) setSpotId(null)
  }, [])
  const collapse = useCallback(() => setSelectedId(null), [])
  const showSpot = useCallback((id) => {
    setSpotId(id)
    setSnap((s) => (s === 'peek' ? 'half' : s))
  }, [])
  const closeSpot = useCallback(() => setSpotId(null), [])
  const changeView = useCallback((v) => {
    setView(v)
    setSnap(v === 'list' ? 'full' : 'half')
  }, [])

  const mapProps = {
    places: visible,
    selectedId,
    onSelect: selectPlace,
    spots: foodMode ? cuisine.spots : null,
    selectedSpotId: spotId,
    onSelectSpot: showSpot,
    routeTo: openSpot,
    fitBottom: snapHeight('half'),
    insetRef: sheetInset,
    apiRef: mapApi,
  }

  return (
    <div className="map-screen" ref={screen}>
      {hasKey ? (
        <GooglePlacesMap apiKey={GOOGLE_MAPS_API_KEY} {...mapProps} onLoaded={onLoaded} onFailed={onFailed} />
      ) : (
        <FallbackMap {...mapProps} active={active} />
      )}

      <header className="map-top">
        <div className="map-top-row">
          <span className="logo-pill">crumbs</span>
          <span className="area-chip">
            <IconPin />
            Capitol Hill
          </span>
          {status === 'loading' && <span className="status-chip">Finding spots…</span>}
        </div>
        <FoodChips selected={cuisineId} onSelect={chooseCuisine} />
        {openSpot && (
          <span className="walk-pill">
            {openSpot.walk.minutes} min walk · {openSpot.walk.miles} mi
          </span>
        )}
      </header>

      {!(foodMode && snap === 'full') && (
        <button className="recenter" onClick={() => mapApi.current?.recenter()} aria-label="Back to Capitol Hill">
          <IconLocate />
        </button>
      )}

      {foodMode ? (
        <FoodSheet
          cuisine={cuisine}
          view={view}
          onView={changeView}
          sort={sort}
          onSort={setSort}
          spotId={spotId}
          onOpenSpot={showSpot}
          onCloseSpot={closeSpot}
          snap={snap}
          onSnap={setSnap}
          sheetRef={sheetRef}
        />
      ) : (
        <SearchSheet place={selected} query={query} onQuery={setQuery} onCollapse={collapse} onCuisine={chooseCuisine} sheetRef={sheetRef} />
      )}
    </div>
  )
}
