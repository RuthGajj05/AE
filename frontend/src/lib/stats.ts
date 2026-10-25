// Display math over whatever the competitors endpoint returns. Null values
// (things the scraper couldn't find) are left out of every median.
import { THEMES } from '../data/reference'
import type { Competitor, Profile, Theme } from '../types'

export interface ThemeSummary {
  theme: Theme
  mentions: number
  businesses: number
}

export interface MarketStats {
  medianPrice: number | null
  medianWait: number | null
  medianRating: number | null
  medianReviews: number | null
  /** Your price relative to the nearby median, as a fraction (0.1 = 10% above). */
  priceGap: number | null
  waitGap: number | null
  themes: ThemeSummary[]
  /** Competitors with a known 90-day price change, and how many of them raised prices. */
  priceTracked: number
  priceRaisers: number
  avgRaise: number
}

const known = (values: (number | null)[]) => values.filter((v): v is number => v !== null)

export function median(values: (number | null)[]): number | null {
  const sorted = known(values).sort((a, b) => a - b)
  if (sorted.length === 0) return null
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}

export const money = (n: number) => `$${n.toFixed(2)}`
export const pct = (n: number) => `${n > 0 ? '+' : ''}${Math.round(n * 100)}%`

function summarizeThemes(competitors: Competitor[]): ThemeSummary[] {
  const totals = new Map<Theme, ThemeSummary>()
  for (const c of competitors) {
    for (const [theme, count] of Object.entries(c.complaints) as [Theme, number][]) {
      if (!(theme in THEMES) || !count) continue
      const t = totals.get(theme) ?? { theme, mentions: 0, businesses: 0 }
      t.mentions += count
      t.businesses += 1
      totals.set(theme, t)
    }
  }
  return [...totals.values()].sort((a, b) => b.mentions - a.mentions)
}

export function marketStats(profile: Profile, competitors: Competitor[]): MarketStats {
  const medianPrice = median(competitors.map((c) => c.itemPrice))
  const medianWait = median(competitors.map((c) => c.waitMin))
  const changes = known(competitors.map((c) => c.priceChange90d))
  const raises = changes.filter((c) => c > 0)
  return {
    medianPrice,
    medianWait,
    medianRating: median(competitors.map((c) => c.rating)),
    medianReviews: median(competitors.map((c) => c.reviewCount)),
    priceGap: medianPrice ? (profile.itemPrice - medianPrice) / medianPrice : null,
    waitGap: medianWait === null ? null : profile.waitMin - medianWait,
    themes: summarizeThemes(competitors),
    priceTracked: changes.length,
    priceRaisers: raises.length,
    avgRaise: raises.length ? raises.reduce((s, c) => s + c, 0) / raises.length : 0,
  }
}
