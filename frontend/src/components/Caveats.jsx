export function Caveats({ caveats }) {
  return (
    <details className="glass caveats">
      <summary>
        <span>What we couldn't verify</span>
        <span className="muted">{caveats.length} note{caveats.length === 1 ? '' : 's'} from the research</span>
      </summary>
      <ul>
        {caveats.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
    </details>
  )
}
