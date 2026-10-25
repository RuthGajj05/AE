import { APIProvider, Map, Marker, Polyline, useMap, useMapsLibrary } from '@vis.gl/react-google-maps'
import { useEffect, useRef } from 'react'
import { MAP_STYLE } from './mapStyle.js'
import { letterPin, PIN, PIN_SELECTED } from './pins.js'
import { CAPITOL_HILL, searchNearbyPlaces, USER_LOCATION, walkPath } from './places.js'

const TOP_ROOM = 120
const svgUrl = (svg) => `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`

// Classic markers with SVG icons: Advanced Markers need a cloud map ID, which would ignore MAP_STYLE.
const icons = {}
function pinIcon(selected) {
  const pin = selected ? PIN_SELECTED : PIN
  icons[pin.width] ??= {
    url: svgUrl(pin.svg),
    scaledSize: new window.google.maps.Size(pin.width, pin.height),
    anchor: new window.google.maps.Point(pin.width / 2, pin.height - 1),
  }
  return icons[pin.width]
}

function letterIcon(spot, selected) {
  const { size, svg } = letterPin(spot.letter, { pick: spot.pick, selected })
  return {
    url: svgUrl(svg),
    scaledSize: new window.google.maps.Size(size, size),
    anchor: new window.google.maps.Point(size / 2, size / 2),
  }
}

const YOU_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"><circle cx="9" cy="9" r="9" fill="#fff"/><circle cx="9" cy="9" r="6" fill="#111"/></svg>'

// Dotted line: invisible stroke with a repeating round dot.
const dottedIcons = () => [
  {
    icon: { path: window.google.maps.SymbolPath.CIRCLE, fillColor: '#111', fillOpacity: 1, strokeOpacity: 0, scale: 2.5 },
    offset: '0',
    repeat: '12px',
  },
]

/**
 * Full-screen styled Google map. Loads nearby spots once and reports them (or the failure) to the parent.
 * With `spots` (a food type is chosen) it shows lettered pins instead of the nearby places; `routeTo` draws a
 * dotted walk from the user to that spot.
 */
export function GooglePlacesMap({ apiKey, places, selectedId, onSelect, spots, selectedSpotId, onSelectSpot, routeTo, fitBottom, onLoaded, onFailed, apiRef }) {
  return (
    <APIProvider apiKey={apiKey}>
      <Map
        className="crumbs-map"
        defaultCenter={CAPITOL_HILL}
        defaultZoom={15}
        styles={MAP_STYLE}
        disableDefaultUI
        clickableIcons={false}
        gestureHandling="greedy"
        onClick={() => onSelect(null)}
      >
        {spots
          ? spots.map((spot) => (
              <Marker
                key={spot.id}
                position={{ lat: spot.lat, lng: spot.lng }}
                icon={letterIcon(spot, spot.id === selectedSpotId)}
                zIndex={spot.id === selectedSpotId ? 1000 : spot.pick ? 500 : undefined}
                title={`${spot.letter}: ${spot.name}`}
                onClick={() => onSelectSpot(spot.id)}
              />
            ))
          : places.map((place) => (
              <Marker
                key={place.id}
                position={{ lat: place.lat, lng: place.lng }}
                icon={pinIcon(place.id === selectedId)}
                zIndex={place.id === selectedId ? 1000 : undefined}
                title={place.name}
                onClick={() => onSelect(place.id)}
              />
            ))}
        {routeTo && (
          <>
            <Polyline path={walkPath(routeTo)} strokeOpacity={0} icons={dottedIcons()} clickable={false} />
            <Marker
              position={USER_LOCATION}
              clickable={false}
              icon={{ url: svgUrl(YOU_SVG), anchor: new window.google.maps.Point(9, 9) }}
              title="You"
            />
          </>
        )}
        <MapControls
          routeTo={routeTo}
          focus={spots?.find((s) => s.id === selectedSpotId) ?? places.find((p) => p.id === selectedId)}
          spots={spots}
          fitBottom={fitBottom}
          apiRef={apiRef}
        />
      </Map>
      <PlacesLoader onLoaded={onLoaded} onFailed={onFailed} />
    </APIProvider>
  )
}

function PlacesLoader({ onLoaded, onFailed }) {
  const placesLib = useMapsLibrary('places')
  const report = useRef({ onLoaded, onFailed })

  useEffect(() => {
    report.current = { onLoaded, onFailed }
  })

  useEffect(() => {
    if (!placesLib) return
    let live = true
    searchNearbyPlaces(placesLib)
      .then((list) => {
        if (!live) return
        if (list.length) report.current.onLoaded(list)
        else report.current.onFailed(new Error('Nearby Search found no restaurants or cafes.'))
      })
      .catch((err) => live && report.current.onFailed(err))
    return () => {
      live = false
    }
  }, [placesLib])

  return null
}

/** Pans to the selected pin, fits a food type's spots or a walk, and gives the parent a recenter() for the button. */
function MapControls({ focus, spots, routeTo, fitBottom, apiRef }) {
  const map = useMap()
  const fit = useRef(fitBottom)

  useEffect(() => {
    fit.current = fitBottom
  })

  useEffect(() => {
    if (!map) return
    apiRef.current = {
      recenter: () => {
        map.panTo(CAPITOL_HILL)
        map.setZoom(15)
      },
    }
    return () => {
      apiRef.current = null
    }
  }, [map, apiRef])

  useEffect(() => {
    if (!map || !spots) return
    const bounds = new window.google.maps.LatLngBounds()
    for (const s of spots) bounds.extend({ lat: s.lat, lng: s.lng })
    map.fitBounds(bounds, { top: TOP_ROOM, bottom: fit.current + 24, left: 40, right: 40 })
  }, [map, spots])

  useEffect(() => {
    if (map && focus) map.panTo({ lat: focus.lat, lng: focus.lng })
  }, [map, focus])

  useEffect(() => {
    if (!map || !routeTo) return
    const bounds = new window.google.maps.LatLngBounds()
    for (const p of walkPath(routeTo)) bounds.extend(p)
    map.fitBounds(bounds, { top: TOP_ROOM + 44, bottom: fit.current + 32, left: 56, right: 56 })
  }, [map, routeTo])

  return null
}
