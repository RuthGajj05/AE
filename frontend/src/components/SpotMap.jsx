import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'

const CAPITOL_HILL = [47.6223, -122.3165]

function pinLabel(spot) {
  if (spot.minPrice !== null) return `$${spot.minPrice % 1 ? spot.minPrice.toFixed(2) : spot.minPrice}`
  if (spot.rating !== null) return `★ ${spot.rating.toFixed(1)}`
  return '•'
}

/** Leaflet map with one price pin per spot. Clicking a pin calls onSelect; activeId/hoverId restyle pins. */
export function SpotMap({ spots, activeId, hoverId, onSelect }) {
  const container = useRef(null)
  const map = useRef(null)
  const markers = useRef(new Map())
  const select = useRef(onSelect)

  useEffect(() => {
    select.current = onSelect
  })

  useEffect(() => {
    const m = L.map(container.current, { zoomControl: false, scrollWheelZoom: true }).setView(CAPITOL_HILL, 15)
    L.control.zoom({ position: 'bottomright' }).addTo(m)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m)
    map.current = m
    return () => {
      m.remove()
      map.current = null
    }
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m) return
    for (const marker of markers.current.values()) marker.remove()
    markers.current.clear()

    const placed = spots.filter((s) => s.lat !== null && s.lng !== null)
    for (const spot of placed) {
      const pin = document.createElement('span')
      pin.className = 'pin-label'
      pin.textContent = pinLabel(spot)
      const marker = L.marker([spot.lat, spot.lng], {
        icon: L.divIcon({ className: 'pin', html: pin, iconSize: null }),
        title: spot.name,
        keyboard: true,
        riseOnHover: true,
      })
        .on('click', () => select.current(spot.id, 'map'))
        .addTo(m)
      markers.current.set(spot.id, marker)
    }
    if (placed.length) m.fitBounds(L.latLngBounds(placed.map((s) => [s.lat, s.lng])), { padding: [48, 48], maxZoom: 16 })
  }, [spots])

  useEffect(() => {
    for (const [id, marker] of markers.current) {
      const el = marker.getElement()
      el?.classList.toggle('is-active', id === activeId)
      el?.classList.toggle('is-hover', id === hoverId && id !== activeId)
      marker.setZIndexOffset(id === activeId ? 1000 : id === hoverId ? 500 : 0)
    }
  }, [activeId, hoverId, spots])

  // Bring the selected pin into view when it's chosen from the list.
  useEffect(() => {
    const marker = activeId && markers.current.get(activeId)
    if (marker && map.current && !map.current.getBounds().pad(-0.15).contains(marker.getLatLng())) {
      map.current.panTo(marker.getLatLng())
    }
  }, [activeId])

  return <div ref={container} className="spot-map" aria-label="Map of nearby competitors" />
}
