import { useEffect, useId, useState } from 'react'
import { verifyBusiness } from '../lib/verifyBusiness.ts'

const ACRONYMS = new Set(['LLC', 'PLLC', 'LLP', 'LP', 'INC', 'JV', 'II', 'III', 'USA'])
/** "CINN CITY LLC" → "Cinn City LLC" */
const titleCase = (s) =>
  s
    .split(/\s+/)
    .map((w) => (ACRONYMS.has(w.toUpperCase()) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()))
    .join(' ')

export function LicenseBadge({ name, address }) {
  const [result, setResult] = useState(null)
  const [tipOpen, setTipOpen] = useState(false)
  const tipId = useId()

  useEffect(() => {
    let live = true
    verifyBusiness(name, address ?? '').then((r) => {
      if (live) setResult(r)
    })
    return () => {
      live = false
    }
  }, [name, address])

  // Tapping the badge toggles its details (phones have no hover); it shouldn't also select the card.
  const toggleTip = (e) => {
    e.stopPropagation()
    setTipOpen((o) => !o)
  }

  if (!result) return <span className="license is-checking">Checking license records…</span>
  if (result.status === 'not_found') return <span className="license is-none">Not found in Seattle license records</span>
  if (result.status === 'error') return <span className="license is-none">{result.note}</span>

  const { match } = result
  const verified = result.status === 'verified'
  return (
    <span className="license-row">
      <span className={`license-wrap${tipOpen ? ' is-open' : ''}`} onMouseLeave={() => setTipOpen(false)}>
        <button
          type="button"
          className={`license ${verified ? 'is-verified' : 'is-unverified'}`}
          aria-describedby={tipId}
          aria-expanded={tipOpen}
          onClick={toggleTip}
          onBlur={() => setTipOpen(false)}
        >
          {verified ? '✓ Licensed in Seattle' : 'Unverified'}
        </button>
        <span className="license-tip" role="tooltip" id={tipId}>
          {verified ? (
            <>
              <strong>{titleCase(match.legalName)}</strong>
              {match.tradeName && match.tradeName !== match.legalName && <span>Doing business as {titleCase(match.tradeName)}</span>}
              <span>{match.ownershipType}</span>
              {match.openSince && <span>Open since {match.openSince}</span>}
              {result.note && <span className="license-tip-note">{result.note}</span>}
            </>
          ) : (
            <>
              <strong>Couldn't confirm this match</strong>
              <span>{result.note}</span>
            </>
          )}
          <span className="license-tip-source">Seattle business license records</span>
        </span>
      </span>
      {result.smallBusiness && <span className="tag-small">Small business</span>}
    </span>
  )
}
