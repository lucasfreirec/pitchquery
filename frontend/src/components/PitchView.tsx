import type { ArrowMark, DotMark, Mark, ShotMark } from '../pitch'
import { MARGIN, VIEW_BOX } from '../pitch'

/** Pitch markings, drawn in StatsBomb coordinates (120 x 80) inside the margin. */
function Markings() {
  return (
    <g className="markings" transform={`translate(${String(MARGIN)} ${String(MARGIN)})`}>
      <rect x={0} y={0} width={120} height={80} />
      <line x1={60} y1={0} x2={60} y2={80} />
      <circle cx={60} cy={40} r={10} />
      <circle cx={60} cy={40} r={0.4} className="spot" />
      {/* Own half: penalty area, six-yard box, penalty spot, arc, goal */}
      <rect x={0} y={18} width={18} height={44} />
      <rect x={0} y={30} width={6} height={20} />
      <circle cx={12} cy={40} r={0.4} className="spot" />
      <path d="M 18 32 A 10 10 0 0 1 18 48" />
      <rect x={-2} y={36} width={2} height={8} className="goal" />
      {/* Attacking half */}
      <rect x={102} y={18} width={18} height={44} />
      <rect x={114} y={30} width={6} height={20} />
      <circle cx={108} cy={40} r={0.4} className="spot" />
      <path d="M 102 32 A 10 10 0 0 0 102 48" />
      <rect x={120} y={36} width={2} height={8} className="goal" />
    </g>
  )
}

function Arrow({ mark }: { mark: ArrowMark }) {
  const variant = mark.kind === 'carry' ? 'carry' : mark.complete ? 'complete' : 'incomplete'
  return (
    <line
      className={`arrow ${variant}`}
      x1={mark.from.x}
      y1={mark.from.y}
      x2={mark.to.x}
      y2={mark.to.y}
      markerEnd={`url(#head-${variant})`}
    >
      <title>{mark.label}</title>
    </line>
  )
}

function Shot({ mark }: { mark: ShotMark }) {
  return (
    <circle
      className={mark.goal ? 'shot goal' : 'shot'}
      cx={mark.at.x}
      cy={mark.at.y}
      r={mark.radius}
    >
      <title>{mark.label}</title>
    </circle>
  )
}

function Dot({ mark }: { mark: DotMark }) {
  return (
    <circle className="dot" cx={mark.at.x} cy={mark.at.y} r={0.6}>
      <title>{mark.label}</title>
    </circle>
  )
}

function ArrowHead({ id }: { id: string }) {
  return (
    <marker
      id={`head-${id}`}
      className={`head ${id}`}
      viewBox="0 0 10 10"
      refX={8}
      refY={5}
      markerWidth={5}
      markerHeight={5}
      orient="auto-start-reverse"
    >
      <path d="M 0 0 L 10 5 L 0 10 z" />
    </marker>
  )
}

export function PitchView({ marks }: { marks: Mark[] }) {
  const arrows = marks.filter((m): m is ArrowMark => m.kind === 'pass' || m.kind === 'carry')
  const dots = marks.filter((m): m is DotMark => m.kind === 'event')
  // Biggest chances first, so small circles are drawn on top and stay hoverable.
  const shots = marks
    .filter((m): m is ShotMark => m.kind === 'shot')
    .sort((a, b) => b.radius - a.radius)

  return (
    <figure className="pitch">
      <svg viewBox={VIEW_BOX} role="img" aria-label={`Pitch with ${String(marks.length)} events`}>
        <defs>
          <ArrowHead id="complete" />
          <ArrowHead id="incomplete" />
          <ArrowHead id="carry" />
        </defs>
        <rect className="grass" x={0} y={0} width="100%" height="100%" />
        <Markings />
        {arrows.map((m, i) => (
          <Arrow key={`a${String(i)}`} mark={m} />
        ))}
        {dots.map((m, i) => (
          <Dot key={`d${String(i)}`} mark={m} />
        ))}
        {shots.map((m, i) => (
          <Shot key={`s${String(i)}`} mark={m} />
        ))}
      </svg>
      <figcaption className="legend">
        <span>
          <i className="swatch goal" /> Goal
        </span>
        <span>
          <i className="swatch shot" /> Shot (size = xG)
        </span>
        <span>
          <i className="swatch line complete" /> Completed pass
        </span>
        <span>
          <i className="swatch line incomplete" /> Failed pass
        </span>
        <span>
          <i className="swatch line carry" /> Carry
        </span>
        <span className="direction">Attacking →</span>
      </figcaption>
    </figure>
  )
}
