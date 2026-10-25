// Thin one-color outline icons for the food types. Stroke only, so they pick up currentColor.
const base = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.8, strokeLinecap: 'round', strokeLinejoin: 'round' }

const ART = {
  // roll seen from above: rice, filling, center
  sushi: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5.5" />
      <circle cx="12" cy="12" r="2" />
    </>
  ),
  // bowl, chopsticks, steam
  ramen: (
    <>
      <path d="M4 11.5h16a8 8 0 0 1-16 0z" />
      <path d="M9 21h6" />
      <path d="m12.5 11.5 6.5-8M15 11.5l6-6.5" />
      <path d="M7.5 8.5c-1-1 1-2 0-3.5M10.5 8.5c-1-1 1-2 0-3.5" />
    </>
  ),
  // T-bone: lopsided steak with the bone running down one side
  steak: (
    <>
      <path d="M3.5 12.5c0-5 4.2-8.5 9.5-8.5 4.6 0 7.5 2.7 7.5 6.3 0 2.4-1.4 3.9-1.4 6.2 0 2.3-2 3.5-5.1 3.5-6 0-10.5-2.8-10.5-7.5z" />
      <path d="M6.8 13c0-3.6 2.9-6.2 6.2-6.2" />
      <circle cx="14.2" cy="13.2" r="2.2" />
    </>
  ),
  // slice with crust and 2 pepperoni
  pizza: (
    <>
      <path d="M3.5 6.5c5.5-3 11.5-3 17 0L12 21.5z" />
      <path d="M5 9.2c4.6-2.4 9.4-2.4 14 0" />
      <circle cx="10.2" cy="12" r="1.4" />
      <circle cx="13.6" cy="15.2" r="1.3" />
    </>
  ),
  // half-circle shell with wavy lettuce
  tacos: (
    <>
      <path d="M2.5 18a9.5 9.5 0 0 1 19 0z" />
      <path d="M6 14c1-1.2 2-1.2 3 0s2 1.2 3 0 2-1.2 3 0 2 1.2 3 0" />
    </>
  ),
}

export function FoodIcon({ id, size = 20 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" {...base} aria-hidden="true">
      {ART[id]}
    </svg>
  )
}
