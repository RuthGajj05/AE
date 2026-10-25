// Everything the crumbs app loads or saves goes through this file: Google Places, the sample places and food
// types, pick events, the business report, and (later) review scores from the backend. See API.md → "crumbs map".
import { buildBusinessReport } from './businessReport.js'
import businessData from './data/business.json'
import cuisineData from './data/cuisines.json'
import mock from './data/mock-places.json'
import { AMBIANCE } from './metrics.js'

// Browser key from .env.local (git-ignored). Missing → the app uses the sample places on a free fallback map.
export const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''

// Backend base URL. Empty → relative /api, which the Vite dev server proxies to the backend on the machine running
// it, so anyone opening the page through a tunnel reaches that backend too.
export const API_BASE = import.meta.env.VITE_API_URL || '/api'

/** GET a backend endpoint as JSON, or null when the backend is down, slow or errors (callers fall back to samples). */
async function apiGet(path) {
  try {
    const res = await fetch(`${API_BASE}${path}`, { signal: AbortSignal.timeout(4000) })
    return res.ok ? await res.json() : null
  } catch {
    return null
  }
}

export const CAPITOL_HILL = { lat: 47.619, lng: -122.321 }

const PRICE = { FREE: 'Free', INEXPENSIVE: '$', MODERATE: '$$', EXPENSIVE: '$$$', VERY_EXPENSIVE: '$$$$' }

/** "$$" for Google's price enum, or null when unknown. */
export const formatPrice = (level) => PRICE[level] ?? null

// "1525 10th Ave, Seattle, WA 98122, USA" → "1525 10th Ave, Seattle"
const shortAddress = (address) => (address ? address.split(', ').slice(0, 2).join(', ') : '')

let nearby = null

/**
 * Restaurants and cafes around Capitol Hill from Places API (New) Nearby Search.
 * `placesLib` is google.maps.places (from useMapsLibrary('places')). Cached so re-renders don't re-bill.
 */
export function searchNearbyPlaces(placesLib) {
  nearby ??= placesLib.Place.searchNearby({
    fields: ['id', 'displayName', 'primaryTypeDisplayName', 'priceLevel', 'rating', 'userRatingCount', 'formattedAddress', 'location'],
    locationRestriction: { center: CAPITOL_HILL, radius: 800 },
    includedTypes: ['restaurant', 'cafe'],
    maxResultCount: 20,
  })
    .then(({ places }) =>
      places
        .filter((p) => p.location)
        .map((p) => ({
          id: p.id,
          name: p.displayName || 'Unnamed spot',
          cuisine: p.primaryTypeDisplayName || 'Restaurant',
          priceLevel: p.priceLevel ?? null,
          rating: p.rating ?? null,
          ratingCount: p.userRatingCount ?? null,
          address: shortAddress(p.formattedAddress),
          lat: p.location.lat(),
          lng: p.location.lng(),
        })),
    )
    .catch((err) => {
      nearby = null
      throw err
    })
  return nearby
}

/** The 10 sample Capitol Hill spots, same shape as searchNearbyPlaces. */
export const getMockPlaces = () => mock.places

/** The food types for the chips: [{ id, label }]. */
export const CUISINES = cuisineData.cuisines.map(({ id, label }) => ({ id, label }))

// Demo "you are here": the middle of Capitol Hill. Walks and distances are measured from it.
export const USER_LOCATION = CAPITOL_HILL

/** Walking estimate along the street grid (Capitol Hill is a N–S grid): { miles, minutes } at 3 mph. */
export function walkFromUser(spot) {
  const milesPerDegLat = 69
  const milesPerDegLng = 69 * Math.cos((USER_LOCATION.lat * Math.PI) / 180)
  const miles = Math.abs(spot.lat - USER_LOCATION.lat) * milesPerDegLat + Math.abs(spot.lng - USER_LOCATION.lng) * milesPerDegLng
  return { miles: Math.max(0.1, Math.round(miles * 10) / 10), minutes: Math.max(1, Math.round(miles * 20)) }
}

/** Walking path drawn on the map: along the user's street, then up or down the spot's avenue. [{ lat, lng }] */
export const walkPath = (spot) => [USER_LOCATION, { lat: USER_LOCATION.lat, lng: spot.lng }, { lat: spot.lat, lng: spot.lng }]

const average = (values) => Math.round(values.reduce((sum, v) => sum + v, 0) / values.length)

/**
 * One food type's compare data: attributes (plus Ambiance on every food type), 4 spots, and the crumbs pick. Sample
 * data for now; later the backend returns the same shape from Claude's review analysis (contract in API.md). Spots
 * get letters A–D in order, an `overall` average of the 0–100 scores, and a walk from the user.
 */
export async function getCuisine(id) {
  const cuisine = (await apiGet(`/cuisines/${encodeURIComponent(id)}`)) ?? cuisineData.cuisines.find((c) => c.id === id)
  if (!cuisine) throw new Error(`No sample data for "${id}".`)
  const spots = cuisine.spots.map((s, i) => {
    const walk = walkFromUser(s)
    return { ...s, letter: 'ABCD'[i], overall: average(Object.values(s.scores)), walk, distanceMi: walk.miles }
  })
  return {
    ...cuisine,
    attributes: [...cuisine.attributes, AMBIANCE],
    spots,
    reviewsRead: spots.reduce((sum, s) => sum + s.reviewCount, 0),
  }
}

/** Google Maps walking directions to a spot. */
export const directionsUrl = (spot) =>
  `https://www.google.com/maps/dir/?api=1&destination=${spot.lat},${spot.lng}&travelmode=walking`

// Pick events and saved spots live in this browser only (localStorage) until the backend has POST /api/picks.
// Storage can be missing (private mode), so every read and write is wrapped.
const PICKS_KEY = 'crumbs.picks'
const SAVED_KEY = 'crumbs.saved'

function readList(key) {
  try {
    const list = JSON.parse(localStorage.getItem(key) ?? '[]')
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

function writeList(key, list) {
  try {
    localStorage.setItem(key, JSON.stringify(list))
  } catch {
    // Storage full or blocked: the demo keeps working, the event just isn't kept.
  }
}

/** Anonymous pick: which spot a user chose after comparing. No user info is stored. */
export function recordPick({ cuisine, chosenSpotId, comparedSpotIds }) {
  writeList(PICKS_KEY, [...readList(PICKS_KEY), { cuisine, chosenSpotId, comparedSpotIds, timestamp: new Date().toISOString() }])
}

export const readPicks = () => readList(PICKS_KEY)

export const isSaved = (spotId) => readList(SAVED_KEY).includes(spotId)

/** Toggles a saved spot; returns whether it's saved now. */
export function toggleSaved(spotId) {
  const saved = readList(SAVED_KEY)
  const next = saved.includes(spotId) ? saved.filter((id) => id !== spotId) : [...saved, spotId]
  writeList(SAVED_KEY, next)
  return next.includes(spotId)
}

/**
 * The business side (You tab): picks won and lost, why rivals won, and the breakdown vs the area. Built from
 * sample data plus this browser's pick events for now; later one backend call (contract in API.md).
 */
export async function getBusinessReport() {
  return buildBusinessReport(businessData, await getCuisine(businessData.you.cuisine), readPicks())
}

/**
 * Freshness / Value / Service from Claude's review analysis (contract in API.md). Until the backend answers, every
 * score is null and the card shows "—".
 */
export async function getPlaceScores(placeId) {
  const scores = placeId ? await apiGet(`/places/${encodeURIComponent(placeId)}/scores`) : null
  return { freshness: scores?.freshness ?? null, value: scores?.value ?? null, service: scores?.service ?? null }
}
