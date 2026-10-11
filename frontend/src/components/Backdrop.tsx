import { useAccentColor } from '../accent'

// A stylised circuit (not a real track): main straight, hairpin, chicane and a fast sweep.
// Drawn on a 1600x900 canvas; pathLength normalises it so the "cars" lap at a fixed pace.
const TRACK =
  'M 260 690 L 1010 690 C 1110 690 1150 650 1160 590 L 1180 470 C 1190 410 1250 380 1310 390 ' +
  'L 1410 410 C 1480 425 1500 350 1450 310 C 1390 260 1280 280 1210 250 L 930 170 ' +
  'C 870 150 810 170 790 220 L 730 370 C 710 420 650 430 610 400 C 570 370 530 380 510 420 ' +
  'L 450 530 C 420 580 360 570 330 530 L 280 460 C 240 410 170 430 160 490 L 160 610 ' +
  'C 160 660 200 690 260 690 Z'

// A generic night skyline, generated once from a fixed seed so it never changes between visits.
function seeded(seed: number) {
  let s = seed
  return () => {
    s = (s * 1664525 + 1013904223) % 4294967296
    return s / 4294967296
  }
}

interface Building {
  x: number
  w: number
  h: number
  far: boolean
  windows: { x: number; y: number; on: number }[]
}

const SKYLINE: Building[] = (() => {
  const rnd = seeded(17)
  const out: Building[] = []
  for (const far of [true, false]) {
    let x = -20
    while (x < 1620) {
      const w = 34 + rnd() * (far ? 60 : 80)
      const h = (far ? 90 : 50) + rnd() * (far ? 150 : 120)
      const windows = []
      for (let wy = 300 - h + 10; wy < 292; wy += 11) {
        for (let wx = x + 6; wx < x + w - 6; wx += 9) {
          const r = rnd()
          if (r < (far ? 0.18 : 0.26)) windows.push({ x: wx, y: wy, on: 0.25 + rnd() * 0.6 })
        }
      }
      out.push({ x, w, h, far, windows })
      x += w + (far ? 2 : 6) + rnd() * 10
    }
  }
  return out
})()

/** Fixed, decorative night-race scene behind every page: floodlights and light beams, a
 *  circuit with two cars lapping it, a city skyline, light streaks, grain and a vignette.
 *  Purely visual (aria-hidden); all motion stops for prefers-reduced-motion. */
export default function Backdrop() {
  const accent = useAccentColor()
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden" aria-hidden>
      {/* Floodlights. Radial gradients rather than blur filters: cheap to animate. */}
      <div
        className="drift-a absolute -left-[22vmax] -top-[28vmax] h-[85vmax] w-[85vmax] rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(225,6,0,0.42), rgba(225,6,0,0.08) 45%, transparent 65%)' }}
      />
      <div
        className="drift-b absolute -right-[26vmax] top-[0vh] h-[80vmax] w-[80vmax] rounded-full transition-[background] duration-1000"
        style={{ background: `radial-gradient(circle, ${accent}66, ${accent}14 45%, transparent 63%)` }}
      />
      <div
        className="drift-b absolute left-1/2 top-[-30vmax] h-[60vmax] w-[60vmax] -translate-x-1/2 rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(255,190,110,0.16), transparent 60%)', animationDelay: '-8s' }}
      />
      <div
        className="drift-a absolute -bottom-[38vmax] left-[10vw] h-[75vmax] w-[75vmax] rounded-full"
        style={{ background: 'radial-gradient(circle, rgba(57,135,229,0.28), transparent 60%)', animationDelay: '-12s' }}
      />

      {/* Floodlight beams from the lighting towers at the top corners. */}
      <div
        className="beam absolute -left-[10vw] -top-[10vh] h-[130vh] w-[45vw] origin-top-left"
        style={{ background: 'linear-gradient(180deg, rgba(255,240,220,0.13), transparent 75%)', clipPath: 'polygon(0 0, 18% 0, 100% 100%, 55% 100%)' }}
      />
      <div
        className="beam absolute -right-[10vw] -top-[10vh] h-[130vh] w-[45vw] origin-top-right"
        style={{
          background: 'linear-gradient(180deg, rgba(220,235,255,0.11), transparent 75%)',
          clipPath: 'polygon(82% 0, 100% 0, 45% 100%, 0 100%)',
          animationDelay: '-7s',
        }}
      />

      {/* Timing-screen dot grid, fading towards the edges. */}
      <div
        className="absolute inset-0 opacity-70"
        style={{
          backgroundImage: 'radial-gradient(rgba(255,255,255,0.09) 1px, transparent 1.3px)',
          backgroundSize: '26px 26px',
          maskImage: 'radial-gradient(ellipse 75% 60% at 50% 30%, black, transparent)',
          WebkitMaskImage: 'radial-gradient(ellipse 75% 60% at 50% 30%, black, transparent)',
        }}
      />

      {/* The circuit, with two cars lapping it. Scaled up so it reaches into the margins. */}
      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">
        <defs>
          <linearGradient id="track-fade" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#fff" stopOpacity="0.22" />
            <stop offset="1" stopColor="#fff" stopOpacity="0.08" />
          </linearGradient>
        </defs>
        <g transform="translate(800 450) scale(1.22) rotate(-6) translate(-800 -440)">
          <path d={TRACK} fill="none" stroke="url(#track-fade)" strokeWidth="36" strokeLinejoin="round" />
          <path d={TRACK} fill="none" stroke="#0a0a10" strokeOpacity="0.94" strokeWidth="29" strokeLinejoin="round" />
          <path d={TRACK} fill="none" stroke="#fff" strokeOpacity="0.10" strokeWidth="2" strokeDasharray="3 16" />
          <Car color="#ff2a1f" duration="16s" delay="0s" />
          <Car color={accent} duration="17.5s" delay="-5s" />
        </g>
      </svg>

      {/* Night skyline along the bottom, with lit windows and an observation wheel. */}
      <svg
        className="absolute inset-x-0 bottom-0 h-[34vh] w-full"
        viewBox="0 0 1600 300"
        preserveAspectRatio="xMidYMax slice"
      >
        <defs>
          <linearGradient id="haze" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#e10600" stopOpacity="0" />
            <stop offset="1" stopColor="#e10600" stopOpacity="0.12" />
          </linearGradient>
        </defs>
        <rect width="1600" height="300" fill="url(#haze)" />
        <g transform="translate(1290 120)" opacity="0.55">
          <circle r="96" fill="none" stroke="#1d2340" strokeWidth="3" />
          {Array.from({ length: 16 }, (_, i) => {
            const a = (i / 16) * Math.PI * 2
            return (
              <g key={i}>
                <line x1="0" y1="0" x2={Math.cos(a) * 96} y2={Math.sin(a) * 96} stroke="#1d2340" strokeWidth="1.2" />
                <circle cx={Math.cos(a) * 96} cy={Math.sin(a) * 96} r="3" fill="#ffd9a0" opacity="0.55" />
              </g>
            )
          })}
          <path d="M -40 180 L 0 0 L 40 180" fill="none" stroke="#1d2340" strokeWidth="5" />
        </g>
        {SKYLINE.map((b, i) => (
          <g key={i} opacity={b.far ? 0.75 : 1}>
            <rect x={b.x} y={300 - b.h} width={b.w} height={b.h} fill={b.far ? '#0f1428' : '#090b16'} />
            {b.windows.map((w, j) => (
              <rect
                key={j}
                x={w.x}
                y={w.y}
                width="4"
                height="5"
                fill={j % 7 === 0 ? '#9cc3ff' : '#ffd08a'}
                opacity={w.on * (b.far ? 0.35 : 0.5)}
              />
            ))}
          </g>
        ))}
      </svg>

      {/* Light streaks, like long-exposure car lights. */}
      {[
        { top: '18%', delay: '0s', width: '28vw' },
        { top: '57%', delay: '-3.5s', width: '20vw' },
        { top: '83%', delay: '-6.5s', width: '34vw' },
      ].map((s) => (
        <div
          key={s.top}
          className="streak absolute left-0 h-px"
          style={{
            top: s.top,
            width: s.width,
            animationDelay: s.delay,
            background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.45), rgba(255,42,31,0.75), transparent)',
          }}
        />
      ))}

      {/* Film grain, so dark areas have texture rather than flat black. */}
      <div
        className="absolute inset-0 opacity-[0.08] mix-blend-overlay"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")",
        }}
      />

      {/* Vignette: darkens the corners so content stays the focus. */}
      <div
        className="absolute inset-0"
        style={{ background: 'radial-gradient(ellipse 120% 95% at 50% 40%, transparent 60%, rgba(0,0,0,0.5))' }}
      />
    </div>
  )
}

/** A car's light trail lapping the circuit: a faint wide halo under a bright core. Strokes
 *  instead of a blur filter, so the animation stays cheap. */
function Car({ color, duration, delay }: { color: string; duration: string; delay: string }) {
  const lap = { animationDuration: duration, animationDelay: delay }
  return (
    <>
      <path d={TRACK} pathLength={1000} fill="none" stroke={color} strokeOpacity="0.18" strokeWidth="22"
        strokeLinecap="round" strokeDasharray="40 960" className="lap" style={lap} />
      <path d={TRACK} pathLength={1000} fill="none" stroke={color} strokeOpacity="0.35" strokeWidth="11"
        strokeLinecap="round" strokeDasharray="38 962" className="lap" style={lap} />
      <path d={TRACK} pathLength={1000} fill="none" stroke={color} strokeWidth="5"
        strokeLinecap="round" strokeDasharray="34 966" className="lap" style={lap} />
    </>
  )
}
