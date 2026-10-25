const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.9, strokeLinecap: 'round', strokeLinejoin: 'round' }

const Svg = ({ size = 24, strokeWidth, children }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" {...base} strokeWidth={strokeWidth ?? base.strokeWidth} aria-hidden="true">
    {children}
  </svg>
)

export const IconHome = (p) => (
  <Svg {...p}>
    <path d="M4 10.5 12 4l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5.5h-5V20H5a1 1 0 0 1-1-1z" />
  </Svg>
)

export const IconBell = (p) => (
  <Svg {...p}>
    <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15zM10 20.5a2 2 0 0 0 4 0" />
  </Svg>
)

// Alert kinds (thin outline, one color)
const ALERT_ART = {
  // leaf: fresh in
  fresh_stock: <path d="M5 19c0-8 5-13 14-14-.5 9-5.5 14-14 14zM5 19l7-7" />,
  // trophy: top rated
  top_rated: <path d="M8 4h8v4a4 4 0 0 1-8 0zM8 6H5a3 3 0 0 0 3 3M16 6h3a3 3 0 0 1-3 3M12 12v4M9 20h6M10 16h4v4h-4z" />,
  // price tag
  price_change: <path d="M4 12.5V5a1 1 0 0 1 1-1h7.5L20 11.5 12.5 19zM8.5 8.5h.01" />,
  // storefront: new spot
  new_spot: <path d="M4 9.5 5.5 4h13L20 9.5M4 9.5a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0 2.7 2.7 0 0 0 5.3 0M5 11.5V20h14v-8.5M10 20v-5h4v5" />,
  // clock: closed
  closed: <path d="M12 3.5a8.5 8.5 0 1 0 0 17 8.5 8.5 0 0 0 0-17zM12 7.5V12l3 2" />,
  // trend: a rival changed something
  owner_change: <path d="M4 17l5-5 4 4 7-8M15 8h5v5" />,
  // box: low stock
  low_stock: <path d="M4 8l8-4 8 4v8l-8 4-8-4zM4 8l8 4 8-4M12 12v8" />,
}

// The backend's owner kinds reuse the closest picture.
const ALERT_ALIAS = { new_competitor: 'new_spot', hours_change: 'closed', rating_change: 'top_rated', review_trend: 'owner_change' }

export const AlertIcon = ({ kind, size = 20 }) => (
  <Svg size={size}>{ALERT_ART[kind] ?? ALERT_ART[ALERT_ALIAS[kind]] ?? ALERT_ART.new_spot}</Svg>
)

export const IconLock = (p) => (
  <Svg size={22} {...p}>
    <rect x="5" y="10.5" width="14" height="10" rx="2.5" />
    <path d="M8 10.5V8a4 4 0 0 1 8 0v2.5" />
  </Svg>
)

export const IconX = (p) => (
  <Svg size={16} strokeWidth={2.2} {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Svg>
)

export const IconMap = (p) => (
  <Svg {...p}>
    <path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6zM9 4v14M15 6v14" />
  </Svg>
)

export const IconSaved = (p) => (
  <Svg {...p}>
    <path d="M6.5 4h11v16L12 16l-5.5 4z" />
  </Svg>
)

export const IconYou = (p) => (
  <Svg {...p}>
    <circle cx="12" cy="8.5" r="3.5" />
    <path d="M5 20c1.2-3.6 4-5.5 7-5.5s5.8 1.9 7 5.5" />
  </Svg>
)

export const IconPin = (p) => (
  <Svg size={16} {...p}>
    <path d="M12 21s-6.5-5.7-6.5-11a6.5 6.5 0 0 1 13 0c0 5.3-6.5 11-6.5 11z" />
    <circle cx="12" cy="10" r="2.3" />
  </Svg>
)

export const IconSearch = (p) => (
  <Svg size={18} strokeWidth={2.1} {...p}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4 4" />
  </Svg>
)

export const IconChevron = (p) => (
  <Svg size={18} strokeWidth={2} {...p}>
    <path d="m9 6 6 6-6 6" />
  </Svg>
)

export const IconBack = (p) => (
  <Svg size={22} strokeWidth={2.1} {...p}>
    <path d="m15 5-7 7 7 7" />
  </Svg>
)

export const IconList = (p) => (
  <Svg size={16} strokeWidth={2} {...p}>
    <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />
  </Svg>
)

export const IconChart = (p) => (
  <Svg size={16} strokeWidth={2} {...p}>
    <rect x="4" y="4" width="6.5" height="6.5" rx="1.5" />
    <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" />
    <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" />
    <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" />
  </Svg>
)

export const IconPhone = (p) => (
  <Svg size={20} {...p}>
    <path d="M6.6 3.5h2.6l1.4 4-2 1.3a11 11 0 0 0 6.6 6.6l1.3-2 4 1.4v2.6a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 4.6 5.7a2 2 0 0 1 2-2.2z" />
  </Svg>
)

export const IconShare = (p) => (
  <Svg size={20} {...p}>
    <path d="M12 15V4M8 8l4-4 4 4M6 12v6.5a1.5 1.5 0 0 0 1.5 1.5h9a1.5 1.5 0 0 0 1.5-1.5V12" />
  </Svg>
)

export const IconLocate = ({ size = 22 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="M20.3 3.7a1 1 0 0 0-1.1-.2L3.6 10.1a1 1 0 0 0 .1 1.9l6.6 1.7 1.7 6.6a1 1 0 0 0 1.9.1l6.6-15.6a1 1 0 0 0-.2-1.1z" />
  </svg>
)

export const IconStar = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d="m12 3 2.7 5.6 6.1.8-4.5 4.2 1.1 6.1L12 16.8l-5.4 2.9 1.1-6.1-4.5-4.2 6.1-.8z" />
  </svg>
)
