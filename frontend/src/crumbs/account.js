import { createContext, useContext } from 'react'

// The demo account lives in this browser (localStorage): consumer or business, the profile, favorite foods, alert
// settings and, for business accounts, their spot. Later this comes from sign-in.

export const AREAS = ['Capitol Hill', 'First Hill', 'Central District', 'Montlake']

// Alert settings, each covering one or more alert kinds (the backend's owner kinds roll up into "Rival changes").
// Business accounts also get the owner groups.
export const ALERT_KINDS = [
  { id: 'fresh_stock', label: 'Fresh in', audience: 'consumer', kinds: ['fresh_stock'] },
  { id: 'top_rated', label: 'Top rated', audience: 'consumer', kinds: ['top_rated'] },
  { id: 'price_change', label: 'Price changes', audience: 'consumer', kinds: ['price_change'] },
  { id: 'new_spot', label: 'New spots', audience: 'consumer', kinds: ['new_spot'] },
  { id: 'closed', label: 'Closures', audience: 'consumer', kinds: ['closed'] },
  {
    id: 'owner_change',
    label: 'Rival changes',
    audience: 'business',
    kinds: ['owner_change', 'new_competitor', 'hours_change', 'rating_change', 'review_trend'],
  },
  { id: 'low_stock', label: 'Low stock', audience: 'business', kinds: ['low_stock'] },
]

export const DEFAULT_ACCOUNT = {
  type: 'consumer',
  name: 'Guest',
  homeArea: 'Capitol Hill',
  favorites: [],
  alertPrefs: {},
  business: null,
}

/** Pre-filled in onboarding; it matches the sample Insights and Rivals data. */
export const SAMPLE_BUSINESS = { name: 'Tamago Sushi', address: '1520 E Olive Way, Seattle', type: 'Sushi', cuisine: 'sushi' }

const KEY = 'crumbs.account'

export function loadAccount() {
  try {
    const saved = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    return saved && typeof saved === 'object' ? { ...DEFAULT_ACCOUNT, ...saved } : DEFAULT_ACCOUNT
  } catch {
    return DEFAULT_ACCOUNT
  }
}

export function saveAccount(account) {
  try {
    localStorage.setItem(KEY, JSON.stringify(account))
  } catch {
    // Storage blocked: the account just resets on reload.
  }
}

export const isBusiness = (account) => account.type === 'business' && account.business !== null

/** An alert kind is on unless the user switched its setting off. Unknown kinds are always on. */
export function alertKindOn(account, kind) {
  const setting = ALERT_KINDS.find((k) => k.id === kind || k.kinds.includes(kind))
  return !setting || account.alertPrefs[setting.id] !== false
}

/** "Jagger Baldevia" → "JB", "Guest" → "G" */
export const initials = (name) =>
  name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('') || '?'

export const AccountContext = createContext(null)

/** { account, update(patch), onboarding, startOnboarding(), closeOnboarding() } */
export const useAccount = () => useContext(AccountContext)
