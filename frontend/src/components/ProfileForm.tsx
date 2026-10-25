import { useState, type FormEvent } from 'react'
import { CATEGORIES, NEIGHBORHOODS } from '../data/reference'
import { DEMO_PROFILE } from '../data/sample'
import type { Category, NeighborhoodId, Profile } from '../types'

interface Props {
  initial: Profile | null
  onSave: (p: Profile) => void
  onCancel?: () => void
}

type Draft = Record<keyof Profile, string>

const toDraft = (p: Profile): Draft => ({
  name: p.name,
  category: p.category,
  neighborhood: p.neighborhood,
  reviewUrl: p.reviewUrl,
  rating: String(p.rating),
  reviewCount: String(p.reviewCount),
  itemPrice: String(p.itemPrice),
  waitMin: String(p.waitMin),
})

const EMPTY: Draft = {
  name: '',
  category: 'bakery',
  neighborhood: 'capitol-hill',
  reviewUrl: '',
  rating: '',
  reviewCount: '',
  itemPrice: '',
  waitMin: '',
}

function validate(d: Draft): string | null {
  if (!d.name.trim()) return 'Add your business name.'
  const rating = Number(d.rating)
  if (!d.rating || rating < 1 || rating > 5) return 'Rating should be between 1 and 5.'
  if (d.reviewCount === '' || Number(d.reviewCount) < 0) return 'Add how many reviews you have (0 is fine).'
  if (!d.itemPrice || Number(d.itemPrice) <= 0) return 'Add the price of your benchmark item.'
  if (!d.waitMin || Number(d.waitMin) <= 0) return 'Add your typical wait in minutes.'
  return null
}

export function ProfileForm({ initial, onSave, onCancel }: Props) {
  const [draft, setDraft] = useState<Draft>(initial ? toDraft(initial) : EMPTY)
  const [error, setError] = useState<string | null>(null)
  const set = (key: keyof Profile) => (e: { target: { value: string } }) =>
    setDraft((d) => ({ ...d, [key]: e.target.value }))
  const item = CATEGORIES[draft.category as Category].item

  function submit(e: FormEvent) {
    e.preventDefault()
    const problem = validate(draft)
    setError(problem)
    if (problem) return
    onSave({
      name: draft.name.trim(),
      category: draft.category as Category,
      neighborhood: draft.neighborhood as NeighborhoodId,
      reviewUrl: draft.reviewUrl.trim(),
      rating: Number(draft.rating),
      reviewCount: Math.round(Number(draft.reviewCount)),
      itemPrice: Number(draft.itemPrice),
      waitMin: Number(draft.waitMin),
    })
  }

  return (
    <form className="card form" onSubmit={submit} noValidate>
      <header className="card-head">
        <div>
          <h2>{initial ? 'Edit your business' : 'Tell us about your business'}</h2>
          <p className="muted">
            Takes about a minute. We compare you to similar spots nearby — no account needed.
          </p>
        </div>
        {!initial && (
          <button type="button" className="text-btn" onClick={() => setDraft(toDraft(DEMO_PROFILE))}>
            Fill with a demo bakery
          </button>
        )}
      </header>

      <div className="form-grid">
        <label className="span-2">
          Business name
          <input value={draft.name} onChange={set('name')} placeholder="e.g. Rise & Knead Bakery" />
        </label>
        <label>
          What you sell
          <select value={draft.category} onChange={set('category')}>
            {Object.entries(CATEGORIES).map(([id, c]) => (
              <option key={id} value={id}>{c.label}</option>
            ))}
          </select>
        </label>
        <label>
          Neighborhood
          <select value={draft.neighborhood} onChange={set('neighborhood')}>
            {Object.entries(NEIGHBORHOODS).map(([id, n]) => (
              <option key={id} value={id}>{n.label}</option>
            ))}
          </select>
        </label>
        <label>
          Price of a {item} ($)
          <input type="number" inputMode="decimal" min="0" step="0.05" value={draft.itemPrice} onChange={set('itemPrice')} />
        </label>
        <label>
          Typical wait (minutes)
          <input type="number" inputMode="numeric" min="1" value={draft.waitMin} onChange={set('waitMin')} />
        </label>
        <label>
          Google rating
          <input type="number" inputMode="decimal" min="1" max="5" step="0.1" value={draft.rating} onChange={set('rating')} />
        </label>
        <label>
          Number of reviews
          <input type="number" inputMode="numeric" min="0" value={draft.reviewCount} onChange={set('reviewCount')} />
        </label>
        <label className="span-2">
          Google review link <span className="muted">(optional)</span>
          <input type="url" value={draft.reviewUrl} onChange={set('reviewUrl')} placeholder="https://g.page/r/…/review" />
        </label>
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}

      <div className="form-actions">
        {onCancel && (
          <button type="button" className="btn ghost" onClick={onCancel}>Cancel</button>
        )}
        <button type="submit" className="btn primary">{initial ? 'Save changes' : 'See my market'}</button>
      </div>
    </form>
  )
}
