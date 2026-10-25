import type { Category, NeighborhoodId, Theme } from '../types'

export const CATEGORIES: Record<Category, { label: string; plural: string; item: string }> = {
  bakery: { label: 'Bakery', plural: 'bakeries', item: 'butter croissant' },
  coffee: { label: 'Coffee shop', plural: 'coffee shops', item: '12 oz latte' },
  tacos: { label: 'Taquería', plural: 'taquerías', item: 'al pastor taco' },
  pho: { label: 'Pho / Vietnamese', plural: 'pho spots', item: 'large beef pho' },
}

export const NEIGHBORHOODS: Record<NeighborhoodId, { label: string; lat: number; lng: number }> = {
  'capitol-hill': { label: 'Capitol Hill', lat: 47.6253, lng: -122.3222 },
  ballard: { label: 'Ballard', lat: 47.6687, lng: -122.3847 },
  fremont: { label: 'Fremont', lat: 47.651, lng: -122.3505 },
  'u-district': { label: 'U District', lat: 47.6615, lng: -122.3138 },
  'queen-anne': { label: 'Queen Anne', lat: 47.637, lng: -122.357 },
  downtown: { label: 'Downtown', lat: 47.6062, lng: -122.3321 },
  'beacon-hill': { label: 'Beacon Hill', lat: 47.579, lng: -122.3115 },
  'columbia-city': { label: 'Columbia City', lat: 47.5596, lng: -122.2866 },
}

export const THEMES: Record<Theme, { label: string; opportunity: string }> = {
  wait: {
    label: 'Long waits',
    opportunity: 'Post your typical wait on your Google profile and at the door — speed is a reason to pick you.',
  },
  price: {
    label: 'Too expensive',
    opportunity: 'Lead with value: a combo or a “regulars” punch card answers the price complaint without a discount war.',
  },
  portions: {
    label: 'Small portions',
    opportunity: 'Photograph your portions for your listing — people choosing between spots compare plates.',
  },
  service: {
    label: 'Unfriendly service',
    opportunity: 'Reply to every review this month. Visible, friendly replies are cheap proof you are the welcoming option.',
  },
  hours: {
    label: 'Closes too early',
    opportunity: 'If you can staff it, an extra hour in the evening catches customers your neighbors turn away.',
  },
  online: {
    label: 'No online ordering',
    opportunity: 'Turn on pickup ordering through your Google listing so call-ahead customers find you first.',
  },
  consistency: {
    label: 'Inconsistent quality',
    opportunity: 'Write down your recipes and prep steps so every shift makes it the same — reliability earns repeat visits.',
  },
  seating: {
    label: 'Nowhere to sit',
    opportunity: 'If you have seats or outlets, say so in your listing photos — it is a deciding factor for this crowd.',
  },
}

const EARTH_RADIUS_MI = 3958.8

export function distanceMi(a: NeighborhoodId, b: NeighborhoodId): number {
  const p = NEIGHBORHOODS[a]
  const q = NEIGHBORHOODS[b]
  const rad = (d: number) => (d * Math.PI) / 180
  const dLat = rad(q.lat - p.lat)
  const dLng = rad(q.lng - p.lng)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(p.lat)) * Math.cos(rad(q.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.sqrt(h))
}
