import { FoodIcon } from './foodIcons.jsx'
import { CUISINES } from './places.js'

/** Scrolling row of food-type chips in the top bar. Tapping the selected chip clears it. */
export function FoodChips({ selected, onSelect }) {
  return (
    <div className="food-chips" role="group" aria-label="Food types">
      {CUISINES.map(({ id, label }) => {
        const isOn = id === selected
        return (
          <button
            key={id}
            className={`food-chip${isOn ? ' is-on' : ''}`}
            aria-pressed={isOn}
            aria-label={isOn ? `${label}, tap to clear` : label}
            onClick={() => onSelect(isOn ? null : id)}
          >
            <FoodIcon id={id} />
            {label}
            {isOn && (
              <span className="food-chip-x" aria-hidden="true">
                ✕
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/** "Popular near you" row in the search sheet: 56px round buttons with a label underneath. */
export function FoodButtons({ selected, onSelect }) {
  return (
    <div className="food-buttons">
      {CUISINES.map(({ id, label }) => (
        <button key={id} className={`food-button${id === selected ? ' is-on' : ''}`} aria-pressed={id === selected} onClick={() => onSelect(id)}>
          <span className="food-button-circle">
            <FoodIcon id={id} size={26} />
          </span>
          {label}
        </button>
      ))}
    </div>
  )
}
