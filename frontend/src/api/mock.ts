// Stand-in backend. Returns the same shapes as the real endpoints (see API.md),
// with a short delay so loading states show up during development.
import { CATEGORIES, distanceMi, NEIGHBORHOODS, THEMES } from '../data/reference'
import { SAMPLE_BUSINESSES, TRENDS } from '../data/sample'
import { marketStats, money, pct } from '../lib/stats'
import type {
  Competitor,
  CompetitorsResponse,
  Impact,
  Profile,
  Recommendation,
  RecommendationsResponse,
  Theme,
} from '../types'

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason)
    })
  })
}

export async function getCompetitors(profile: Profile, radiusMi: number, signal?: AbortSignal): Promise<CompetitorsResponse> {
  await wait(900, signal)
  const competitors: Competitor[] = SAMPLE_BUSINESSES.filter((b) => b.category === profile.category)
    .map((b) => ({
      id: b.id,
      name: b.name,
      neighborhood: NEIGHBORHOODS[b.neighborhood].label,
      distanceMi: Math.round(distanceMi(profile.neighborhood, b.neighborhood) * 10) / 10,
      rating: b.rating,
      reviewCount: b.reviewCount,
      itemPrice: b.itemPrice,
      waitMin: b.waitMin,
      priceChange90d: b.priceChange90d,
      complaints: b.complaints,
    }))
    .filter((c) => c.distanceMi <= radiusMi)
    .sort((a, b) => a.distanceMi - b.distanceMi)
  return { competitors, trends: TRENDS[profile.category], source: 'sample', scrapedAt: new Date().toISOString() }
}

const IMPACT_ORDER: Record<Impact, number> = { high: 0, medium: 1, low: 2 }

/** Rule-based stand-in for the Claude call on the backend. */
export async function getRecommendations(
  profile: Profile,
  competitors: Competitor[],
  signal?: AbortSignal,
): Promise<RecommendationsResponse> {
  await wait(1200, signal)
  const s = marketStats(profile, competitors)
  const { item, plural } = CATEGORIES[profile.category]
  const n = competitors.length
  const recs: Recommendation[] = []
  if (n === 0) return { recommendations: recs }

  if (s.medianPrice !== null && s.priceGap !== null && s.priceGap <= -0.08) {
    const target = Math.min(s.medianPrice - 0.05, profile.itemPrice * 1.08)
    recs.push({
      id: 'price-low',
      title: `You have room to raise your ${item} price`,
      evidence: `Yours is ${money(profile.itemPrice)}; the median nearby is ${money(s.medianPrice)} (${pct(s.priceGap)}). ${s.priceRaisers} of ${s.priceTracked} competitors raised prices in the last 90 days.`,
      action: `Try ${money(Math.round(target * 20) / 20)} for two weeks and watch your daily count. You would still be below the area median.`,
      impact: 'high',
      effort: 'low',
    })
  } else if (s.medianPrice !== null && s.priceGap !== null && s.priceGap >= 0.08) {
    const backed = s.medianRating === null || profile.rating >= s.medianRating
    recs.push({
      id: 'price-high',
      title: backed ? 'Your premium price is backed by your rating — say why' : 'You are priced above the area without the rating to back it',
      evidence: `Yours is ${money(profile.itemPrice)} vs a ${money(s.medianPrice)} median (${pct(s.priceGap)}).${s.medianRating !== null ? ` Your rating is ${profile.rating.toFixed(1)} vs ${s.medianRating.toFixed(1)} nearby.` : ''}`,
      action: backed
        ? 'Name what makes it worth it (ingredients, size, made in-house) on your menu board and listing.'
        : 'Hold the price but add a small extra, or test a lower price on your slowest day before changing it everywhere.',
      impact: backed ? 'medium' : 'high',
      effort: 'low',
    })
  }

  const waitTheme = s.themes.slice(0, 3).find((t) => t.theme === 'wait')
  if (s.waitGap !== null && s.waitGap >= 2) {
    recs.push({
      id: 'wait-long',
      title: `Your wait runs ${Math.round(s.waitGap)} min longer than nearby`,
      evidence: `About ${profile.waitMin} min for you vs a ${s.medianWait} min median nearby.`,
      action: 'Prep your top two sellers ahead of the morning and lunch rush, and offer order-ahead pickup.',
      impact: 'high',
      effort: 'medium',
    })
  } else if (s.waitGap !== null && s.waitGap <= -2 && waitTheme) {
    recs.push({
      id: 'wait-fast',
      title: 'Speed is your edge — advertise it',
      evidence: `${waitTheme.mentions} reviews of ${waitTheme.businesses} nearby ${plural} complain about waits. You are ${Math.abs(Math.round(s.waitGap))} min faster than the median.`,
      action: `Add “ready in about ${profile.waitMin} minutes” to your Google profile and storefront sign.`,
      impact: 'medium',
      effort: 'low',
    })
  }

  if (s.medianReviews !== null && profile.reviewCount < s.medianReviews * 0.6) {
    recs.push({
      id: 'reviews',
      title: 'Customers can’t find enough reviews of you yet',
      evidence: `You have ${profile.reviewCount} reviews; the typical nearby competitor has ${Math.round(s.medianReviews)}. Listings with more reviews rank higher in map search.`,
      action: profile.reviewUrl
        ? 'Print a QR code to your review link for the register and receipts, and ask happy regulars directly.'
        : 'Add your Google review link to your profile, then put a QR code to it at the register.',
      impact: 'high',
      effort: 'low',
    })
  }

  const handled = new Set<Theme>(['price', 'wait'])
  for (const t of s.themes.filter((t) => !handled.has(t.theme)).slice(0, 2)) {
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
  return { recommendations: recs }
}
