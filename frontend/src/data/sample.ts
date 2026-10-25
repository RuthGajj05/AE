// Sample market data for the Seattle area, used by the mock API until the scraper is live.
// Every business here is fictional.
import type { Category, NeighborhoodId, Profile, Theme } from '../types'

export interface SampleBusiness {
  id: string
  name: string
  category: Category
  neighborhood: NeighborhoodId
  rating: number
  reviewCount: number
  itemPrice: number | null
  waitMin: number | null
  priceChange90d: number
  complaints: Partial<Record<Theme, number>>
}

type Row = [
  name: string,
  neighborhood: NeighborhoodId,
  rating: number,
  reviewCount: number,
  itemPrice: number | null,
  waitMin: number | null,
  priceChange90d: number,
  complaints: Partial<Record<Theme, number>>,
]

const ROWS: Record<Category, Row[]> = {
  bakery: [
    ['Golden Crumb Bakehouse', 'capitol-hill', 4.6, 812, 5.25, 9, 4, { wait: 31, price: 12, seating: 9 }],
    ['Ballard Hearth & Loaf', 'ballard', 4.4, 540, 4.75, 6, 0, { hours: 22, consistency: 8 }],
    ['Little Oven Patisserie', 'fremont', 4.7, 1290, 5.75, 14, 6, { wait: 44, price: 27, portions: 10 }],
    ['Sunrise Sweet Shop', 'beacon-hill', 4.2, 210, 3.95, 4, 0, { consistency: 14, online: 11, service: 6 }],
    ['Northside Bread Co.', 'u-district', 4.3, 388, 4.5, 7, 3, { hours: 17, online: 15 }],
    ['Rainy Day Pastry', 'queen-anne', 4.5, 674, 5.0, 8, 2, { price: 15, seating: 12, wait: 9 }],
    ['Columbia Crust', 'columbia-city', 4.1, 156, 4.25, null, -2, { service: 13, hours: 10 }],
    ['Pike Morning Bakery', 'downtown', 4.3, 1020, 5.5, 10, 5, { wait: 26, price: 18, seating: 15 }],
  ],
  coffee: [
    ['Steam & Grind', 'capitol-hill', 4.5, 1430, 5.75, 6, 3, { seating: 28, wait: 16 }],
    ['Puddle Jumper Coffee', 'ballard', 4.6, 920, 5.5, 5, 0, { hours: 19, price: 8 }],
    ['Fremont Daily Roast', 'fremont', 4.3, 610, 5.95, 7, 5, { service: 21, price: 17 }],
    ['Two Hills Espresso', 'beacon-hill', 4.4, 302, 4.95, 4, 0, { online: 12, seating: 9 }],
    ['Ave Bean Bar', 'u-district', 4.2, 845, 5.25, 9, 2, { wait: 33, consistency: 14, seating: 20 }],
    ['Kerry View Café', 'queen-anne', 4.7, 1105, 6.25, 6, 4, { price: 24, hours: 7 }],
    ['Third & Pine Coffee', 'downtown', 4.0, 1680, 5.65, 8, 1, { service: 30, consistency: 19, wait: 18 }],
    ['Hillman Coffee Cart', 'columbia-city', 4.6, 188, null, 3, 0, { hours: 14, seating: 18 }],
  ],
  tacos: [
    ['Taquería La Lluvia', 'capitol-hill', 4.6, 980, 4.25, 12, 6, { wait: 38, hours: 6 }],
    ['El Muelle Tacos', 'ballard', 4.4, 455, 4.5, 9, 3, { price: 19, portions: 16 }],
    ['Troll Bridge Tacos', 'fremont', 4.2, 320, 3.95, 8, 0, { consistency: 15, online: 12 }],
    ['Cocina Beacon', 'beacon-hill', 4.7, 610, 3.5, 10, 0, { seating: 14, online: 20, hours: 11 }],
    ['Husky Taco Truck', 'u-district', 4.3, 702, 3.25, 6, -3, { portions: 11, consistency: 13, hours: 16 }],
    ['Rainier Ave Taquería', 'columbia-city', 4.5, 388, 3.75, 7, 2, { service: 10, online: 15 }],
    ['Second Ave Tortillería', 'downtown', 4.1, 840, 4.75, 11, 4, { price: 21, wait: 17, service: 9 }],
  ],
  pho: [
    ['Pho Lantern', 'capitol-hill', 4.4, 760, 16.95, 13, 5, { wait: 22, price: 14 }],
    ['Bowl & Broth', 'ballard', 4.3, 410, 17.5, 11, 6, { price: 26, portions: 12 }],
    ['Saigon Corner Kitchen', 'beacon-hill', 4.7, 890, 14.5, 9, 0, { seating: 16, hours: 9, online: 14 }],
    ['Pho on the Ave', 'u-district', 4.1, 1120, 13.95, 8, 2, { service: 24, consistency: 18 }],
    ['Jackson St Noodle House', 'downtown', 4.5, 1340, 15.75, 12, 3, { wait: 27, seating: 13 }],
    ['Columbia Pho & Grill', 'columbia-city', 4.6, 520, 15.25, 10, 4, { online: 17, hours: 12 }],
    ['Queen Anne Pho Bar', 'queen-anne', 4.2, 365, 16.5, 10, 3, { price: 16, portions: 9 }],
  ],
}

export const SAMPLE_BUSINESSES: SampleBusiness[] = Object.entries(ROWS).flatMap(([category, rows]) =>
  rows.map(([name, neighborhood, rating, reviewCount, itemPrice, waitMin, priceChange90d, complaints], i) => ({
    id: `${category}-${i}`,
    name,
    category: category as Category,
    neighborhood,
    rating,
    reviewCount,
    itemPrice,
    waitMin,
    priceChange90d,
    complaints,
  })),
)

/** Search and demand signals per category. */
export const TRENDS: Record<Category, string[]> = {
  bakery: [
    'Searches for “matcha croissant” in Seattle are up 41% over the last 90 days.',
    'Weekend pre-orders for pastry boxes grew 22% year over year across the city.',
  ],
  coffee: [
    'Searches for “oat milk latte near me” are up 18% over the last 90 days.',
    'Laptop-friendly cafés get 2× more weekday-afternoon map views than average.',
  ],
  tacos: [
    'Late-night (after 9pm) taco searches in Seattle are up 27% over the last 90 days.',
    'Birria listings get 35% more photo views than other taco listings.',
  ],
  pho: [
    'Pho searches spike 60% on rainy days — Seattle averages 150 of them a year.',
    'Searches for “pho delivery” are up 15% over the last 90 days.',
  ],
}

export const DEMO_PROFILE: Profile = {
  name: 'Rise & Knead Bakery',
  category: 'bakery',
  neighborhood: 'beacon-hill',
  reviewUrl: 'https://g.page/r/your-business/review',
  rating: 4.5,
  reviewCount: 142,
  itemPrice: 4.25,
  waitMin: 6,
}
