// How each compare row reads a value, shades it and prints it. Most rows are 0–100 review scores; Wait time is
// average minutes (shorter is better) and Ambiance is % of vibe mentions that are positive.

export const AMBIANCE = { id: 'ambiance', label: 'Ambiance', unit: '%' }

export const isWait = (attr) => attr.id === 'wait'

/** Plain 0–100 review scores (what "overall" averages). */
export const isScore = (attr) => !attr.unit

export function metricValue(item, attr) {
  if (isWait(attr)) return item.waitMinutes
  if (attr.id === AMBIANCE.id) return item.ambiancePct
  return item.scores[attr.id]
}

/** 'top' (darkest) / 'mid' / 'low' (palest). Wait: ≤8 min darkest, 9–15 honey, >15 pale. */
export function metricTone(attr, value) {
  if (isWait(attr)) return value <= 8 ? 'top' : value <= 15 ? 'mid' : 'low'
  return value >= 85 ? 'top' : value >= 70 ? 'mid' : 'low'
}

export function formatMetric(attr, value) {
  if (isWait(attr)) return `${value} min`
  if (attr.id === AMBIANCE.id) return `${value}%`
  return String(value)
}

/** Sort comparator, best first. */
export const bestFirst = (attr, value) => (a, b) => (isWait(attr) ? value(a) - value(b) : value(b) - value(a))

/** 0.25 → "in 1 of 4 reviews" */
export const mentionText = (rate) => `in 1 of ${Math.max(1, Math.round(1 / rate))} reviews`

/** Bar scale: 0–30 min for wait, 0–100 for everything else. */
export const scaleMax = (attr) => (isWait(attr) ? 30 : 100)

/**
 * How much `other` beats `you` on this attribute, as a share of the bar scale (0–100), so minutes and points can be
 * compared. Negative when you're better.
 */
export function gapScore(attr, you, other) {
  const diff = isWait(attr) ? you - other : other - you
  return (diff / scaleMax(attr)) * 100
}

/** "+12 min" or "−36 pts": how far behind you are. */
export function gapText(attr, you, other) {
  return isWait(attr) ? `+${Math.round(you - other)} min` : `−${Math.round(other - you)} pts`
}
