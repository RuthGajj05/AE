import { average } from './data/adapter.js'
import { money, minutes, stars } from './format.js'

export const METRICS = [
  {
    key: 'avgPrice',
    label: 'Avg price',
    format: money,
    lowerIsBetter: true,
    // Prices compare as a percentage; small gaps count as "about the same".
    describe: (you, avg) => {
      const p = Math.round(((you - avg) / avg) * 100)
      return Math.abs(p) < 2 ? null : `${Math.abs(p)}% ${p < 0 ? 'cheaper' : 'pricier'}`
    },
  },
  {
    key: 'waitMin',
    label: 'Wait time',
    format: minutes,
    lowerIsBetter: true,
    describe: (you, avg) => {
      const d = you - avg
      return Math.abs(d) < 1 ? null : `${Math.round(Math.abs(d))} min ${d < 0 ? 'faster' : 'slower'}`
    },
  },
  {
    key: 'rating',
    label: 'Rating',
    format: stars,
    lowerIsBetter: false,
    describe: (you, avg) => {
      const d = Math.round((you - avg) * 10) / 10
      return d === 0 ? null : `${Math.abs(d).toFixed(1)} ${d > 0 ? 'higher' : 'lower'}`
    },
  },
]

/** Metrics where both the business and at least one competitor have a value. */
export function comparableMetrics(business, competitors) {
  return METRICS.filter((m) => business[m.key] !== null && average(competitors, m.key) !== null)
}
