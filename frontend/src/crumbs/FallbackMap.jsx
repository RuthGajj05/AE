import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
// Plugin attaches itself to the global L, so it has to come after the leaflet import.
import 'leaflet.markercluster'
import 'leaflet.markercluster/dist/MarkerCluster.css'
import { useEffect, useRef } from 'react'
import { PIN, PIN_SELECTED } from './pins.js'
import { CAPITOL_HILL, walkPath } from './places.js'

// Stadia "Alidade Smooth": clean, Waze-like, no key on localhost. CARTO Voyager now watermarks tiles without a key.
// For a deployed URL, add the domain to a free Stadia account (still no key in the code).
const TILES = {
  url: 'https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png',
  attribution:
    '&copy; <a href="https://stadiamaps.com/">Stadia Maps</a> &copy; <a href="https://openmaptiles.org/">OpenMapTiles</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
}

const CENTER = [CAPITOL_HILL.lat, CAPITOL_HILL.lng]
// Keeps fitted pins clear of the top bar (logo row + food chips).
const TOP_ROOM = 120

function pinIcon(selected) {
  const pin = selected ? PIN_SELECTED : PIN
  return L.divIcon({
    className: selected ? 'crumb-pin is-selected' : 'crumb-pin',
    html: `<div class="crumb-pin-art">${pin.svg}</div>`,
    iconSize: [pin.width, pin.height],
    iconAnchor: [pin.width / 2, pin.height - 1],
  })
}

function letterIcon(spot, selected) {
  const size = (spot.pick ? 42 : 32) + (selected ? 8 : 0)
  return L.divIcon({
    className: `letter-pin${spot.pick ? ' is-pick' : ''}${selected ? ' is-selected' : ''}`,
    html: `<span class="letter-pin-art">${spot.letter}</span>`,
    iconSize: [size, size],
  })
}

const youIcon = () => L.divIcon({ className: 'you-dot', iconSize: [18, 18] })

const clusterIcon = (cluster) =>
  L.divIcon({ className: 'crumb-cluster', html: `<span>${cluster.getChildCount()}</span>`, iconSize: [40, 40] })

/**
 * Stand-in for the Google map when there's no API key: same pins on free tiles, warmed up with CSS.
 * With `spots` (a food type is chosen) it hides the regular pins and shows lettered ones instead; `routeTo` draws
 * a dotted walk from the user to that spot.
 */
export function FallbackMap({ places, selectedId, onSelect, spots, selectedSpotId, onSelectSpot, routeTo, fitBottom, insetRef, active, apiRef }) {
  const container = useRef(null)
  const map = useRef(null)
  const cluster = useRef(null)
  const spotLayer = useRef(null)
  const routeLayer = useRef(null)
  const markers = useRef(new Map())
  const spotMarkers = useRef(new Map())
  const shownSelected = useRef(null)
  const shownSpot = useRef(null)
  const select = useRef(onSelect)
  const selectSpot = useRef(onSelectSpot)
  const fit = useRef(fitBottom)

  useEffect(() => {
    select.current = onSelect
    selectSpot.current = onSelectSpot
    fit.current = fitBottom
  })

  useEffect(() => {
    const m = L.map(container.current, { zoomControl: false, attributionControl: false }).setView(CENTER, 15)
    L.control.attribution({ position: 'bottomleft', prefix: false }).addTo(m)
    L.tileLayer(TILES.url, { maxZoom: 20, attribution: TILES.attribution }).addTo(m)
    // Pins only group when zoomed out past the starting view.
    cluster.current = L.markerClusterGroup({
      iconCreateFunction: clusterIcon,
      showCoverageOnHover: false,
      maxClusterRadius: 50,
      disableClusteringAtZoom: 15,
    }).addTo(m)
    spotLayer.current = L.layerGroup().addTo(m)
    routeLayer.current = L.layerGroup().addTo(m)
    m.on('click', () => select.current(null))
    map.current = m
    apiRef.current = { recenter: () => m.flyTo(CENTER, 15, { duration: 0.6 }) }
    return () => {
      m.remove()
      map.current = null
      apiRef.current = null
    }
  }, [apiRef])

  useEffect(() => {
    cluster.current.clearLayers()
    markers.current.clear()
    for (const place of places) {
      const marker = L.marker([place.lat, place.lng], { icon: pinIcon(false), title: place.name, keyboard: true }).on(
        'click',
        () => select.current(place.id),
      )
      markers.current.set(place.id, marker)
    }
    cluster.current.addLayers([...markers.current.values()])
    shownSelected.current = null
  }, [places])

  // Only swap the two icons that changed, so just the new pin plays its pop animation.
  useEffect(() => {
    const prev = markers.current.get(shownSelected.current)
    prev?.setIcon(pinIcon(false)).setZIndexOffset(0)
    const marker = markers.current.get(selectedId)
    marker?.setIcon(pinIcon(true)).setZIndexOffset(1000)
    shownSelected.current = marker ? selectedId : null
    if (marker) map.current.panTo(marker.getLatLng())
  }, [selectedId, places])

  // Food type chosen: swap the regular pins for lettered ones and fit them above the half-open sheet.
  useEffect(() => {
    const m = map.current
    spotLayer.current.clearLayers()
    spotMarkers.current.clear()
    shownSpot.current = null
    if (!spots) {
      if (!m.hasLayer(cluster.current)) m.addLayer(cluster.current)
      return
    }
    m.removeLayer(cluster.current)
    for (const spot of spots) {
      const marker = L.marker([spot.lat, spot.lng], {
        icon: letterIcon(spot, false),
        title: `${spot.letter}: ${spot.name}`,
        keyboard: true,
        zIndexOffset: spot.pick ? 500 : 0,
      }).on('click', () => selectSpot.current(spot.id))
      spotMarkers.current.set(spot.id, marker.addTo(spotLayer.current))
    }
    m.flyToBounds(L.latLngBounds(spots.map((s) => [s.lat, s.lng])), {
      paddingTopLeft: [40, TOP_ROOM],
      paddingBottomRight: [40, fit.current + 24],
      maxZoom: 16,
      duration: 0.6,
    })
  }, [spots])

  useEffect(() => {
    const prev = spotMarkers.current.get(shownSpot.current)
    const prevSpot = spots?.find((s) => s.id === shownSpot.current)
    if (prev && prevSpot) prev.setIcon(letterIcon(prevSpot, false)).setZIndexOffset(prevSpot.pick ? 500 : 0)
    const marker = spotMarkers.current.get(selectedSpotId)
    const spot = spots?.find((s) => s.id === selectedSpotId)
    shownSpot.current = marker ? selectedSpotId : null
    if (!marker) return
    marker.setIcon(letterIcon(spot, true)).setZIndexOffset(1000)
    map.current.panInside(marker.getLatLng(), { paddingTopLeft: [40, TOP_ROOM], paddingBottomRight: [40, insetRef.current + 24] })
  }, [selectedSpotId, spots, insetRef])

  // Open spot: dotted walk from "you" to it, fitted between the top bar and the sheet.
  useEffect(() => {
    routeLayer.current.clearLayers()
    if (!routeTo) return
    const path = walkPath(routeTo).map((p) => [p.lat, p.lng])
    L.polyline(path, { color: '#111', weight: 4, dashArray: '1 9', lineCap: 'round', interactive: false }).addTo(routeLayer.current)
    L.marker(path[0], { icon: youIcon(), interactive: false, keyboard: false }).addTo(routeLayer.current)
    map.current.flyToBounds(L.latLngBounds(path), {
      paddingTopLeft: [56, TOP_ROOM + 44],
      paddingBottomRight: [56, fit.current + 32],
      maxZoom: 17,
      duration: 0.6,
    })
  }, [routeTo])

  // Leaflet measures its box once; re-measure after the Map tab was hidden.
  useEffect(() => {
    if (active) map.current?.invalidateSize()
  }, [active])

  return <div ref={container} className="crumbs-map crumbs-fallback" aria-label="Map of food spots on Capitol Hill" />
}
