// Teardrop pins shared by the Leaflet and Google maps. The tip is the bottom-center point.
export const PIN = {
  width: 30,
  height: 40,
  svg: '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="40" viewBox="0 0 30 40"><path d="M15 1.5C7.5 1.5 1.5 7.4 1.5 14.8c0 9.6 11.2 21.5 12.6 23 .5.5 1.3.5 1.8 0 1.4-1.5 12.6-13.4 12.6-23C28.5 7.4 22.5 1.5 15 1.5z" fill="#F7DC8F" stroke="#111" stroke-width="2"/><circle cx="15" cy="14.5" r="4.5" fill="#111"/></svg>',
}

export const PIN_SELECTED = {
  width: 40,
  height: 52,
  svg: '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="52" viewBox="0 0 40 52"><path d="M20 2C10.1 2 2 9.9 2 19.6c0 12.8 15 28.6 16.8 30.5.7.7 1.7.7 2.4 0C23 48.2 38 32.4 38 19.6 38 9.9 29.9 2 20 2z" fill="#111" stroke="#fff" stroke-width="3"/><circle cx="20" cy="19.5" r="6" fill="#F7DC8F"/></svg>',
}

// Lettered circle pins for a food type's spots (Google map; the Leaflet map draws the same thing with CSS).
// The crumbs pick is bigger and black with a white ring. Selected pins grow a little.
export function letterPin(letter, { pick = false, selected = false } = {}) {
  const size = (pick ? 42 : 32) + (selected ? 8 : 0)
  const r = size / 2
  const circle = pick
    ? `<circle cx="${r}" cy="${r}" r="${r}" fill="#fff"/><circle cx="${r}" cy="${r}" r="${r - 3}" fill="#111"/>`
    : `<circle cx="${r}" cy="${r}" r="${r - 1}" fill="#F7DC8F" stroke="#111" stroke-width="2"/>`
  const text = `<text x="${r}" y="${r}" dy=".36em" text-anchor="middle" font-family="Arial, sans-serif" font-weight="700" font-size="${Math.round(size * 0.44)}" fill="${pick ? '#F7DC8F' : '#111'}">${letter}</text>`
  return { size, svg: `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}">${circle}${text}</svg>` }
}
