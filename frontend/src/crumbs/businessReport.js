import { gapScore, gapText, metricValue } from './metrics.js'

const average = (values) => values.reduce((sum, v) => sum + v, 0) / values.length

/**
 * Turns the sample business data into what the You tab shows. Stands in for the backend's report: once that
 * exists, getBusinessReport returns its JSON and this file goes away.
 */
export function buildBusinessReport(data, cuisine, picks) {
  const { you } = data

  // This browser's Go-here taps for the same food type in the report's window count as picks lost: in the demo,
  // "you" was in every comparison but the user chose someone else. Malformed stored entries are skipped.
  const since = Date.now() - (data.periodDays ?? 7) * 24 * 60 * 60 * 1000
  const localPicks = picks.filter(
    (p) =>
      p !== null &&
      typeof p === 'object' &&
      p.cuisine === you.cuisine &&
      typeof p.chosenSpotId === 'string' &&
      Date.parse(p.timestamp) >= since,
  )
  const lostTo = { ...data.picksLostTo }
  for (const p of localPicks) lostTo[p.chosenSpotId] = (lostTo[p.chosenSpotId] ?? 0) + 1
  const picksLost = Object.values(lostTo).reduce((sum, n) => sum + n, 0)

  // "Likely because of" = the attribute where the rival beats you by the most (minutes and points on one scale).
  const rivals = cuisine.spots
    .filter((spot) => lostTo[spot.id] > 0)
    .map((spot) => {
      let reason = null
      for (const attr of cuisine.attributes) {
        const mine = metricValue(you, attr)
        const theirs = metricValue(spot, attr)
        const gap = gapScore(attr, mine, theirs)
        if (gap > 0 && (!reason || gap > reason.gap)) reason = { attr, gap, you: mine, rival: theirs, text: gapText(attr, mine, theirs) }
      }
      return { spot, picksWon: lostTo[spot.id], reason }
    })
    .sort((a, b) => b.picksWon - a.picksWon)

  const biggest = rivals.reduce((best, r) => (r.reason && (!best || r.reason.gap > best.reason.gap) ? r : best), null)

  // Attributes where you beat every spot nearby.
  const wins = cuisine.attributes.filter((attr) =>
    cuisine.spots.every((s) => gapScore(attr, metricValue(you, attr), metricValue(s, attr)) < 0),
  )

  const breakdown = cuisine.attributes.map((attr) => ({
    attr,
    you: metricValue(you, attr),
    area: Math.round(average(cuisine.spots.map((s) => metricValue(s, attr)))),
  }))
  const drag = breakdown.reduce((worst, row) => {
    const gap = gapScore(row.attr, row.you, row.area)
    return gap > 0 && (!worst || gap > worst.gap) ? { ...row, gap } : worst
  }, null)

  return {
    you,
    cuisine,
    area: data.area,
    period: data.period,
    picksWon: data.picksWon,
    picksLost,
    localPicks: localPicks.length,
    rivals,
    biggestGapId: biggest?.spot.id ?? null,
    wins,
    breakdown,
    drag,
  }
}
