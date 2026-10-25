import { CATEGORIES, distanceMi, THEMES } from '../data/reference'
import { TRENDS } from '../data/sample'
import type { Competitor, Impact, Profile, Recommendation, Theme } from '../types'

export interface NearbyCompetitor extends Competitor {
  distance: number
}

export interface ThemeSummary {
  theme: Theme
  mentions: number
  businesses: number
}

export interface Analysis {
  nearby: NearbyCompetitor[]
  medianPrice: number
  medianWait: number
  medianRating: number
  medianReviews: number
  /** Your price relative to the nearby median, as a fraction (0.1 = 10% above). */
  priceGap: number
  waitGap: number
  themes: ThemeSummary[]
  priceRaisers: number
  recommendations: Recommendation[]
}

export function median(values: number[]): number {
  if (values.length === 0) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

export const money = (n: number) => `$${n.toFixed(2)}`
export const pct = (n: number) => `${n > 0 ? '+' : ''}${Math.round(n * 100)}%`

export function findNearby(profile: Profile, all: Competitor[], radiusMi: number): NearbyCompetitor[] {
  return all
    .filter((c) => c.category === profile.category)
    .map((c) => ({ ...c, distance: distanceMi(profile.neighborhood, c.neighborhood) }))
    .filter((c) => c.distance <= radiusMi)
    .sort((a, b) => a.distance - b.distance)
}

function summarizeThemes(nearby: Competitor[]): ThemeSummary[] {
  const totals = new Map<Theme, ThemeSummary>()
  for (const c of nearby) {
    for (const [theme, count] of Object.entries(c.complaints) as [Theme, number][]) {
      const t = totals.get(theme) ?? { theme, mentions: 0, businesses: 0 }
      t.mentions += count
      t.businesses += 1
      totals.set(theme, t)
    }
  }
  return [...totals.values()].sort((a, b) => b.mentions - a.mentions)
}

const IMPACT_ORDER: Record<Impact, number> = { high: 0, medium: 1, low: 2 }

export function analyze(profile: Profile, all: Competitor[], radiusMi: number): Analysis {
  const nearby = findNearby(profile, all, radiusMi)
  const { item, plural } = CATEGORIES[profile.category]

  const medianPrice = median(nearby.map((c) => c.itemPrice))
  const medianWait = median(nearby.map((c) => c.waitMin))
  const medianRating = median(nearby.map((c) => c.rating))
  const medianReviews = median(nearby.map((c) => c.reviewCount))
  const priceGap = medianPrice ? (profile.itemPrice - medianPrice) / medianPrice : 0
  const waitGap = profile.waitMin - medianWait
  const themes = summarizeThemes(nearby)
  const priceRaisers = nearby.filter((c) => c.priceChange90d > 0).length

  const recs: Recommendation[] = []
  if (nearby.length === 0) {
    return { nearby, medianPrice, medianWait, medianRating, medianReviews, priceGap, waitGap, themes, priceRaisers, recommendations: recs }
  }

  const n = nearby.length
  const pricedBy = `${n} nearby ${plural}`

  if (priceGap <= -0.08) {
    const target = Math.min(medianPrice - 0.05, profile.itemPrice * 1.08)
    recs.push({
      id: 'price-low',
      title: `You have room to raise your ${item} price`,
      evidence: `Yours is ${money(profile.itemPrice)}; the median across ${pricedBy} is ${money(medianPrice)} (${pct(priceGap)}). ${priceRaisers} of ${n} raised prices in the last 90 days.`,
      action: `Try ${money(Math.round(target * 20) / 20)} for two weeks and watch your daily count. You would still be below the area median.`,
      impact: 'high',
      effort: 'low',
    })
  } else if (priceGap >= 0.08) {
    const backed = profile.rating >= medianRating
    recs.push({
      id: 'price-high',
      title: backed ? 'Your premium price is backed by your rating — say why' : 'You are priced above the area without the rating to back it',
      evidence: `Yours is ${money(profile.itemPrice)} vs a ${money(medianPrice)} median (${pct(priceGap)}). Your rating is ${profile.rating.toFixed(1)} vs ${medianRating.toFixed(1)} nearby.`,
      action: backed
        ? 'Name what makes it worth it (ingredients, size, made in-house) on your menu board and listing.'
        : 'Hold the price but add a small extra, or test a lower price on your slowest day before changing it everywhere.',
      impact: backed ? 'medium' : 'high',
      effort: 'low',
    })
  }

  const waitIsAComplaint = themes.slice(0, 3).some((t) => t.theme === 'wait')
  if (waitGap >= 2) {
    recs.push({
      id: 'wait-long',
      title: `Your wait runs ${Math.round(waitGap)} min longer than nearby`,
      evidence: `About ${profile.waitMin} min for you vs a ${medianWait} min median across ${pricedBy}.`,
      action: 'Prep your top two sellers ahead of the morning and lunch rush, and offer order-ahead pickup.',
      impact: 'high',
      effort: 'medium',
    })
  } else if (waitGap <= -2 && waitIsAComplaint) {
    const wait = themes.find((t) => t.theme === 'wait')!
    recs.push({
      id: 'wait-fast',
      title: 'Speed is your edge — advertise it',
      evidence: `${wait.mentions} reviews of ${wait.businesses} nearby ${plural} complain about waits. You are ${Math.abs(Math.round(waitGap))} min faster than the median.`,
      action: `Add “ready in about ${profile.waitMin} minutes” to your Google profile and storefront sign.`,
      impact: 'medium',
      effort: 'low',
    })
  }

  if (profile.reviewCount < medianReviews * 0.6) {
    recs.push({
      id: 'reviews',
      title: 'Customers can’t find enough reviews of you yet',
      evidence: `You have ${profile.reviewCount} reviews; the typical nearby competitor has ${Math.round(medianReviews)}. Listings with more reviews rank higher in map search.`,
      action: profile.reviewUrl
        ? 'Print a QR code to your review link for the register and receipts, and ask happy regulars directly.'
        : 'Add your Google review link to your profile, then put a QR code to it at the register.',
      impact: 'high',
      effort: 'low',
    })
  }

  const handled = new Set<Theme>(['price', 'wait'])
  for (const t of themes.filter((t) => !handled.has(t.theme)).slice(0, 2)) {
    recs.push({
      id: `theme-${t.theme}`,
      title: `Nearby ${plural} get dinged for “${THEMES[t.theme].label.toLowerCase()}”`,
      evidence: `${t.mentions} reviews across ${t.businesses} of ${n} competitors mention it.`,
      action: THEMES[t.theme].opportunity,
      impact: t.mentions >= 25 ? 'medium' : 'low',
      effort: 'medium',
    })
  }

  recs.push({
    id: 'trend',
    title: 'A demand trend worth testing',
    evidence: TRENDS[profile.category][0],
    action: 'Run it as a limited weekend special and post it on your listing; keep it only if it sells out.',
    impact: 'low',
    effort: 'medium',
  })

  recs.sort((a, b) => IMPACT_ORDER[a.impact] - IMPACT_ORDER[b.impact] || IMPACT_ORDER[a.effort] - IMPACT_ORDER[b.effort])

  return { nearby, medianPrice, medianWait, medianRating, medianReviews, priceGap, waitGap, themes, priceRaisers, recommendations: recs }
}
