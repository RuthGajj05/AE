import { TABS } from './tabs.js'

/** Flat white tab bar. Map is the raised black circle in the middle. `badges` = { tabId: unread count }. */
export function BottomNav({ current, badges = {} }) {
  return (
    <nav className="nav" aria-label="Main">
      {TABS.map(({ id, label, Icon }) => {
        const isCurrent = id === current
        if (id === 'map') {
          return (
            <a key={id} href="#/map" className="nav-map" aria-label={label} aria-current={isCurrent ? 'page' : undefined}>
              <Icon size={28} strokeWidth={2.1} />
            </a>
          )
        }
        const count = badges[id] ?? 0
        return (
          <a
            key={id}
            href={`#/${id}`}
            className={`nav-tab${isCurrent ? ' is-active' : ''}`}
            aria-current={isCurrent ? 'page' : undefined}
            aria-label={count ? `${label}, ${count} unread` : undefined}
          >
            <span className="nav-icon">
              <Icon size={22} />
              {count > 0 && <span className="nav-badge">{count > 9 ? '9+' : count}</span>}
            </span>
            <span>{label}</span>
          </a>
        )
      })}
    </nav>
  )
}
