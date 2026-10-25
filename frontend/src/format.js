export const DASH = '—'

export const money = (n) => (n === null ? DASH : `$${n.toFixed(2)}`)
export const minutes = (n) => {
  if (n === null) return DASH
  const tenths = Math.round(n * 10) / 10
  return `${Number.isInteger(tenths) ? tenths : tenths.toFixed(1)} min`
}
export const stars = (n) => (n === null ? DASH : n.toFixed(1))
export const miles = (n) => (n === null ? DASH : n < 0.1 ? 'Next door' : `${n.toFixed(1)} mi`)
export const count = (n) => (n === null ? DASH : Math.round(n).toLocaleString())
