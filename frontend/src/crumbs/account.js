import { createContext, useContext } from 'react'

// The demo account lives in this browser (localStorage): consumer or business, the profile, favorite foods, alert
// settings and, for business accounts, their spot. Later this comes from sign-in.

export const AREAS = ['Capitol Hill', 'First Hill', 'Central District', 'Montlake']

// Every alert kind the feed knows. Business accounts also get the owner kinds.
export const ALERT_KINDS = [
  { id: 'fresh_stock', label: 'Fresh in', audience: 'consumer' },
  { id: 'top_rated', label: 'Top rated', audience: 'consumer' },
  { id: 'price_change', label: 'Price changes', audience: 'consumer' },
  { id: 'new_spot', label: 'New spots', audience: 'consumer' },
  { id: 'closed', label: 'Closures', audience: 'consumer' },
  { id: 'owner_change', label: 'Rival changes', audience: 'business' },
  { id: 'low_stock', label: 'Low stock', audience: 'business' },
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
export const SAMPLE_BUSINESS = { name: 'Tamago Sushi', address: '1520 E Olive Way, Seattle', cuisine: 'sushi' }

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

/** Alert kinds are on unless the user switched them off. */
export const alertKindOn = (account, kind) => account.alertPrefs[kind] !== false

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
