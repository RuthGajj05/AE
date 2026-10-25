import { TABS } from './tabs.js'

/** Flat white tab bar. Map is the raised black circle in the middle. */
export function BottomNav({ current }) {
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
        return (
          <a key={id} href={`#/${id}`} className={`nav-tab${isCurrent ? ' is-active' : ''}`} aria-current={isCurrent ? 'page' : undefined}>
            <Icon size={22} />
            <span>{label}</span>
          </a>
        )
      })}
    </nav>
  )
}
