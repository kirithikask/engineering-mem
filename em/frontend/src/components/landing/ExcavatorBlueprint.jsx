import React from 'react';

/**
 * Original side-elevation schematic of a hydraulic excavator, drawn as SVG
 * linework so the landing experience is self-contained and fully offline.
 *
 * Callouts name the same components the diagnosis engine resolves to, so the
 * schematic and the 3D twin describe the same machine.
 */
const CALLOUTS = [
  { id: 'pump', label: 'Hydraulic pump', sub: 'Line pressure / internal leakage', x: 300, y: 250, tx: 604, ty: 128, side: 'right' },
  { id: 'valve', label: 'Main control valve', sub: 'Spool response / bypass', x: 352, y: 268, tx: 604, ty: 176, side: 'right' },
  { id: 'boom', label: 'Boom cylinder', sub: 'Drift / pressure decay', x: 452, y: 196, tx: 604, ty: 224, side: 'right' },
  { id: 'cooler', label: 'Hydraulic cooler', sub: 'Restriction at temperature', x: 214, y: 282, tx: 78, ty: 118, side: 'left' },
  { id: 'tank', label: 'Hydraulic tank', sub: 'Oil condition / suction', x: 246, y: 292, tx: 78, ty: 306, side: 'left' },
];

export default function ExcavatorBlueprint({ className = '' }) {
  return (
    <svg
      viewBox="0 0 760 360"
      role="img"
      aria-label="Technical schematic of a hydraulic excavator showing the hydraulic pump, main control valve, boom cylinder, hydraulic cooler and hydraulic tank"
      className={className}
    >
      {/* Datum / ground line */}
      <g stroke="#C7C6C0" strokeWidth="1">
        <line x1="20" y1="300" x2="740" y2="300" strokeDasharray="6 5" />
        <line x1="20" y1="330" x2="740" y2="330" strokeDasharray="6 5" opacity="0.6" />
      </g>

      {/* ---- Undercarriage: tracks, idlers, drive sprocket ---- */}
      <g fill="none" stroke="#2C3237" strokeWidth="2.1" strokeLinecap="round" strokeLinejoin="round">
        <path className="draw-line" style={{ '--len': 900 }} d="M120 300 L120 262 Q120 250 132 250 L318 250 Q330 250 330 262 L330 300 Q330 312 318 312 L132 312 Q120 312 120 300 Z" />
        <path className="draw-line" style={{ '--len': 900, animationDelay: '0.15s' }} d="M144 300 L144 268 Q144 260 152 260 L298 260 Q306 260 306 268 L306 300 Q306 308 298 308 L152 308 Q144 308 144 300 Z" />
        <circle cx="142" cy="284" r="15" />
        <circle cx="308" cy="284" r="15" />
        <circle cx="170" cy="292" r="9" />
        <circle cx="200" cy="292" r="9" />
        <circle cx="230" cy="292" r="9" />
        <circle cx="260" cy="292" r="9" />
        <circle cx="290" cy="292" r="9" />
      </g>

      {/* ---- Car body / swing platform ---- */}
      <g fill="none" stroke="#1B1E21" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path className="draw-line" style={{ '--len': 700, animationDelay: '0.3s' }} d="M176 250 L176 208 L452 208 L452 250" />
        {/* Counterweight (rear) */}
        <path className="draw-line" style={{ '--len': 400, animationDelay: '0.4s' }} d="M176 208 L146 208 Q136 208 136 218 L136 240 Q136 250 146 250 L176 250" />
        {/* Operator cab */}
        <path className="draw-line" style={{ '--len': 500, animationDelay: '0.45s' }} d="M186 208 L186 158 L262 158 L262 208" />
        <line x1="196" y1="168" x2="252" y2="168" strokeWidth="1.4" />
        <line x1="252" y1="168" x2="252" y2="200" strokeWidth="1.4" />
        {/* Walkway rail */}
        <line x1="282" y1="196" x2="440" y2="196" strokeWidth="1.3" />
        <line x1="300" y1="196" x2="300" y2="208" strokeWidth="1.3" />
        <line x1="360" y1="196" x2="360" y2="208" strokeWidth="1.3" />
        <line x1="420" y1="196" x2="420" y2="208" strokeWidth="1.3" />
        {/* Swing circle */}
        <line x1="248" y1="250" x2="248" y2="262" strokeWidth="1.3" />
        <line x1="330" y1="250" x2="330" y2="262" strokeWidth="1.3" />
      </g>

      {/* ---- Boom, arm, bucket ---- */}
      <g fill="none" stroke="#1B1E21" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
        <path className="draw-line" style={{ '--len': 900, animationDelay: '0.55s' }} d="M406 232 L470 132 L500 140 L448 236 Z" />
        <path className="draw-line" style={{ '--len': 900, animationDelay: '0.65s' }} d="M486 140 L588 218 L572 236 L472 158 Z" />
        <path className="draw-line" style={{ '--len': 500, animationDelay: '0.75s' }} d="M574 222 Q604 226 606 250 Q608 274 580 278 L556 268 Q548 250 560 238 Z" />
        {/* Bucket teeth */}
        <path d="M556 268 L548 276 L560 280 M572 272 L566 281 L578 283 M590 268 L586 278 L598 278" strokeWidth="1.6" />
      </g>

      {/* ---- Hydraulic cylinders ---- */}
      <g fill="none" stroke="#8D621E" strokeWidth="2.4" strokeLinecap="round">
        <path className="draw-line" style={{ '--len': 420, animationDelay: '0.85s' }} d="M352 240 L448 190" />
        <rect x="342" y="232" width="34" height="16" transform="rotate(-27 359 240)" strokeWidth="2" />
        <path className="draw-line" style={{ '--len': 420, animationDelay: '0.95s' }} d="M470 168 L556 214" />
        <rect x="462" y="160" width="30" height="15" transform="rotate(31 477 168)" strokeWidth="2" />
        <path className="draw-line" style={{ '--len': 300, animationDelay: '1.05s' }} d="M536 202 L566 226" />
      </g>

      {/* ---- Machine internals (pump, valve, cooler, tank) ---- */}
      <g fill="none" stroke="#596168" strokeWidth="1.8">
        <rect x="286" y="236" width="30" height="22" rx="2" />
        <rect x="336" y="250" width="34" height="18" rx="2" />
        <rect x="198" y="266" width="34" height="22" rx="2" />
        <rect x="232" y="272" width="30" height="22" rx="2" />
        {/* Hydraulic line run */}
        <path d="M316 246 Q330 240 336 252" strokeWidth="1.4" strokeDasharray="4 3" />
        <path d="M232 280 Q262 288 286 250" strokeWidth="1.4" strokeDasharray="4 3" />
      </g>

      {/* ---- Base plate of the house for grounding ---- */}
      <line x1="176" y1="250" x2="452" y2="250" stroke="#2C3237" strokeWidth="2.4" />

      {/* ---- Leader lines + callouts ---- */}
      {CALLOUTS.map((c, i) => (
        <g key={c.id} className="reveal is-visible" style={{ animationDelay: `${1.1 + i * 0.12}s` }}>
          <line
            x1={c.x}
            y1={c.y}
            x2={c.tx}
            y2={c.ty}
            stroke="#C58B2A"
            strokeWidth="1.1"
            strokeDasharray="3 3"
          />
          <circle cx={c.x} cy={c.y} r="3.2" fill="#C58B2A" />
          {c.side === 'right' ? (
            <>
              <line x1={c.tx} y1={c.ty} x2={c.tx + 10} y2={c.ty} stroke="#C58B2A" strokeWidth="1.1" />
              <text x={c.tx + 15} y={c.ty - 2} fill="#1B1E21" fontSize="12" fontFamily="ui-monospace, monospace">
                {c.label}
              </text>
              <text x={c.tx + 15} y={c.ty + 12} fill="#858C91" fontSize="10" fontFamily="ui-monospace, monospace">
                {c.sub}
              </text>
            </>
          ) : (
            <>
              <line x1={c.tx} y1={c.ty} x2={c.tx + 10} y2={c.ty} stroke="#C58B2A" strokeWidth="1.1" />
              <text x={c.tx + 15} y={c.ty - 2} fill="#1B1E21" fontSize="12" fontFamily="ui-monospace, monospace">
                {c.label}
              </text>
              <text x={c.tx + 15} y={c.ty + 12} fill="#858C91" fontSize="10" fontFamily="ui-monospace, monospace">
                {c.sub}
              </text>
            </>
          )}
        </g>
      ))}

      {/* Drawing frame annotation */}
      <g fill="#858C91" fontFamily="ui-monospace, monospace" fontSize="9" letterSpacing="0.1em">
        <text x="20" y="22">FIG. 1 — HYDRAULIC EXCAVATOR, SIDE ELEVATION</text>
        <text x="20" y="348">DIAGNOSTIC COMPONENT MAP</text>
      </g>
    </svg>
  );
}
