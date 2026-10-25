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

/** What customers complain about in reviews. */
export type Theme =
  | 'wait'
  | 'price'
  | 'portions'
  | 'service'
  | 'hours'
  | 'online'
  | 'consistency'
  | 'seating'

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

export interface Competitor {
  id: string
  name: string
  category: Category
  neighborhood: NeighborhoodId
  rating: number
  reviewCount: number
  itemPrice: number
  waitMin: number
  /** Percent change in the benchmark item's price over the last 90 days. */
  priceChange90d: number
  /** Number of reviews mentioning each complaint theme. */
  complaints: Partial<Record<Theme, number>>
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
