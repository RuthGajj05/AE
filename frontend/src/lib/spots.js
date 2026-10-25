// Adds map coordinates to competitors. Coordinates in the report itself win; otherwise they come from
// data/spots.geo.json, made once by `npm run geocode`, so the demo never geocodes live.
import geo from '../../data/spots.geo.json'

const norm = (s = '') => s.toUpperCase().replace(/[^A-Z0-9]/g, '')
const byAddress = new Map(geo.spots.map((s) => [norm(s.address), s]))
const byName = new Map(geo.spots.map((s) => [norm(s.name), s]))

export function withLocations(competitors) {
  return competitors.map((c) => {
    if (c.lat !== null && c.lng !== null) return c
    const hit = (c.address && byAddress.get(norm(c.address))) || byName.get(norm(c.name))
    return hit ? { ...c, lat: hit.lat, lng: hit.lng } : c
  })
}
