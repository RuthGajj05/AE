// Shapes shared with the backend. API.md documents the same contract in plain JSON;
// change both together.

export type Category = 'bakery' | 'coffee' | 'tacos' | 'pho'

export type NeighborhoodId =
  | 'capitol-hill'
  | 'ballard'
  | 'fremont'
  | 'u-district'
  | 'queen-anne'
  | 'downtown'
  | 'beacon-hill'
  | 'columbia-city'

/** What customers complain about in reviews. The backend tags reviews with these exact keys. */
export type Theme =
  | 'wait'
  | 'price'
  | 'portions'
  | 'service'
  | 'hours'
  | 'online'
  | 'consistency'
  | 'seating'

/** The owner's own business, entered in the form. Never leaves the browser except in API requests. */
export interface Profile {
  name: string
  category: Category
  neighborhood: NeighborhoodId
  reviewUrl: string
  rating: number
  reviewCount: number
  /** Price of the category's benchmark item, e.g. a croissant for bakeries. */
  itemPrice: number
  /** Typical minutes from ordering to food in hand. */
  waitMin: number
}

/**
 * A nearby business found by the scraper. Anything the scraper can't find is null —
 * the UI shows "—" and leaves it out of medians and charts.
 */
export interface Competitor {
  id: string
  name: string
  /** Display name of the area, e.g. "Capitol Hill". */
  neighborhood: string
  distanceMi: number | null
  rating: number | null
  reviewCount: number | null
  /** Price of the same benchmark item the owner entered. */
  itemPrice: number | null
  waitMin: number | null
  /** Percent change in itemPrice over the last 90 days, e.g. 4 for +4%. */
  priceChange90d: number | null
  /** Number of reviews mentioning each complaint theme. */
  complaints: Partial<Record<Theme, number>>
  /** Link to the business's listing or site. */
  url?: string
}

export type Impact = 'high' | 'medium' | 'low'

export interface Recommendation {
  id: string
  title: string
  evidence: string
  action: string
  impact: Impact
  effort: Impact
}

export type DataSource = 'live' | 'sample'

/** GET /api/competitors */
export interface CompetitorsResponse {
  competitors: Competitor[]
  /** Short, plain-English market signals for this category and area. */
  trends: string[]
  source: DataSource
  /** ISO 8601 time the data was scraped. */
  scrapedAt: string
}

/** POST /api/recommendations */
export interface RecommendationsRequest {
  profile: Profile
  competitors: Competitor[]
}

export interface RecommendationsResponse {
  recommendations: Recommendation[]
}
