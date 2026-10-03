import React from 'react'

/**
 * In-game style artwork for lobby tiles: each scene shows what the game looks
 * like while it is being played (our own drawings, no third-party images).
 * Drawn on a 300x400 portrait canvas; the top ~110px stays calm for the title.
 */

const W = 300
const H = 400
const RED_SUITS = new Set(['♥', '♦'])

// ------------------------------------------------------------------ shared pieces
const Card: React.FC<{ x: number; y: number; rank: string; suit: string; w?: number; rot?: number; back?: boolean }> = ({ x, y, rank, suit, w = 54, rot = 0, back = false }) => {
  const h = w * 1.4
  const color = RED_SUITS.has(suit) ? '#dc2626' : '#111827'
  return (
    <g transform={`rotate(${rot} ${x + w / 2} ${y + h / 2})`}>
      <rect x={x + 2} y={y + 4} width={w} height={h} rx={6} fill="#000" opacity={0.35} />
      {back ? (
        <>
          <rect x={x} y={y} width={w} height={h} rx={6} fill="#1e3a8a" stroke="#fff" strokeWidth={2} />
          <rect x={x + 5} y={y + 5} width={w - 10} height={h - 10} rx={4} fill="none" stroke="#93c5fd" strokeWidth={1.5} strokeDasharray="3 3" />
        </>
      ) : (
        <>
          <rect x={x} y={y} width={w} height={h} rx={6} fill="#fff" stroke="#e5e7eb" />
          <text x={x + 6} y={y + w * 0.36} fontSize={w * 0.3} fontWeight={800} fill={color} fontFamily="Arial, sans-serif">{rank}</text>
          <text x={x + 6} y={y + w * 0.62} fontSize={w * 0.24} fill={color}>{suit}</text>
          <text x={x + w / 2} y={y + h * 0.72} fontSize={w * 0.62} textAnchor="middle" fill={color}>{suit}</text>
        </>
      )}
    </g>
  )
}

const Chip: React.FC<{ x: number; y: number; r?: number; color: string; label?: string }> = ({ x, y, r = 16, color, label }) => (
  <g>
    <circle cx={x} cy={y + 2} r={r} fill="#000" opacity={0.35} />
    <circle cx={x} cy={y} r={r} fill={color} />
    <circle cx={x} cy={y} r={r * 0.78} fill="none" stroke="#fff" strokeWidth={r * 0.18} strokeDasharray={`${r * 0.35} ${r * 0.35}`} />
    <circle cx={x} cy={y} r={r * 0.5} fill={color} stroke="#fff" strokeOpacity={0.6} />
    {label && <text x={x} y={y + r * 0.2} fontSize={r * 0.55} fontWeight={800} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">{label}</text>}
  </g>
)

const Pill: React.FC<{ x: number; y: number; text: string; fill?: string; color?: string; size?: number }> = ({ x, y, text, fill = 'rgba(0,0,0,0.55)', color = '#fff', size = 16 }) => {
  const w = text.length * size * 0.62 + 20
  return (
    <g>
      <rect x={x - w / 2} y={y - size} width={w} height={size * 1.5} rx={size * 0.75} fill={fill} />
      <text x={x} y={y + size * 0.15} fontSize={size} fontWeight={800} textAnchor="middle" fill={color} fontFamily="Arial, sans-serif">{text}</text>
    </g>
  )
}

const Bg: React.FC<{ id: string; from: string; to: string; glow?: string }> = ({ id, from, to, glow = 'rgba(255,255,255,0.18)' }) => (
  <>
    <defs>
      <linearGradient id={`${id}-bg`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={from} /><stop offset="1" stopColor={to} /></linearGradient>
      <radialGradient id={`${id}-glow`} cx="50%" cy="65%" r="60%"><stop offset="0" stopColor={glow} /><stop offset="1" stopColor="rgba(255,255,255,0)" /></radialGradient>
    </defs>
    <rect width={W} height={H} fill={`url(#${id}-bg)`} />
    <rect width={W} height={H} fill={`url(#${id}-glow)`} />
  </>
)

const Rays: React.FC<{ cx: number; cy: number; color: string; n?: number; opacity?: number }> = ({ cx, cy, color, n = 18, opacity = 0.12 }) => (
  <g opacity={opacity}>
    {Array.from({ length: n }, (_, i) => {
      const a1 = (i / n) * Math.PI * 2, a2 = ((i + 0.5) / n) * Math.PI * 2, R = 520
      return <path key={i} d={`M${cx},${cy} L${cx + R * Math.cos(a1)},${cy + R * Math.sin(a1)} L${cx + R * Math.cos(a2)},${cy + R * Math.sin(a2)} Z`} fill={color} />
    })}
  </g>
)

const Emoji: React.FC<{ x: number; y: number; size: number; children: string; rot?: number }> = ({ x, y, size, children, rot = 0 }) => (
  <text x={x} y={y} fontSize={size} textAnchor="middle" dominantBaseline="central" transform={rot ? `rotate(${rot} ${x} ${y})` : undefined}>{children}</text>
)

// ------------------------------------------------------------------ live games
const AviatorScene: React.FC = () => (
  <>
    <rect width={W} height={H} fill="#0b0b0d" />
    <Rays cx={20} cy={385} color="#ffffff" n={22} opacity={0.06} />
    <defs>
      <linearGradient id="av-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#e50539" stopOpacity={0.75} /><stop offset="1" stopColor="#e50539" stopOpacity={0.15} /></linearGradient>
    </defs>
    {/* grid */}
    <g stroke="#ffffff" strokeOpacity={0.07}>{[150, 200, 250, 300, 350].map((y) => <line key={y} x1={20} x2={W} y1={y} y2={y} />)}</g>
    <path d="M20,385 Q170,380 232,215 L232,385 Z" fill="url(#av-fill)" />
    <path d="M20,385 Q170,380 232,215" fill="none" stroke="#e50539" strokeWidth={5} strokeLinecap="round" />
    <image href="/games/aviator/plane.png" x={196} y={160} width={98} height={43} preserveAspectRatio="xMidYMid meet" />
    <text x={130} y={300} fontSize={50} fontWeight={900} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">2.47x</text>
    <g>{['1.21x', '3.86x', '1.04x', '12.4x'].map((m, i) => <Pill key={m} x={46 + i * 70} y={392} text={m} size={11} fill={i === 3 ? '#7c3aed' : i === 1 ? '#2563eb' : '#334155'} />)}</g>
  </>
)

const TeenPattiScene: React.FC = () => (
  <>
    <rect width={W} height={H} fill="#0f2a1b" />
    <ellipse cx={150} cy={270} rx={160} ry={140} fill="#5b3412" />
    <ellipse cx={150} cy={270} rx={148} ry={128} fill="#0f7a3e" />
    <ellipse cx={150} cy={270} rx={148} ry={128} fill="url(#tp-felt)" />
    <defs><radialGradient id="tp-felt" cx="50%" cy="45%" r="60%"><stop offset="0" stopColor="#22c55e" stopOpacity={0.45} /><stop offset="1" stopColor="#052e16" stopOpacity={0.6} /></radialGradient></defs>
    <text x={75} y={180} fontSize={13} fontWeight={800} textAnchor="middle" fill="#fde68a" fontFamily="Arial, sans-serif">PLAYER A</text>
    <text x={225} y={180} fontSize={13} fontWeight={800} textAnchor="middle" fill="#fde68a" fontFamily="Arial, sans-serif">PLAYER B</text>
    <Card x={22} y={196} rank="A" suit="♠" w={44} rot={-12} />
    <Card x={52} y={192} rank="K" suit="♠" w={44} />
    <Card x={82} y={196} rank="Q" suit="♠" w={44} rot={12} />
    <Card x={172} y={196} rank="7" suit="♥" w={44} rot={-12} />
    <Card x={202} y={192} rank="7" suit="♦" w={44} />
    <Card x={232} y={196} rank="7" suit="♣" w={44} rot={12} />
    <circle cx={150} cy={232} r={17} fill="#111" stroke="#fde68a" strokeWidth={2} />
    <text x={150} y={237} fontSize={13} fontWeight={900} textAnchor="middle" fill="#fde68a" fontFamily="Arial, sans-serif">VS</text>
    <Chip x={110} y={330} color="#dc2626" label="100" />
    <Chip x={150} y={342} color="#2563eb" label="500" r={18} />
    <Chip x={190} y={330} color="#16a34a" label="50" />
    <Pill x={150} y={385} text="Bets close in 12s" size={12} fill="rgba(0,0,0,0.6)" color="#fde68a" />
  </>
)

const WINGO_BALL: Record<number, [string, string]> = {
  0: ['#ef4444', '#8b5cf6'], 5: ['#22c55e', '#8b5cf6'],
  1: ['#22c55e', '#22c55e'], 3: ['#22c55e', '#22c55e'], 7: ['#22c55e', '#22c55e'], 9: ['#22c55e', '#22c55e'],
  2: ['#ef4444', '#ef4444'], 4: ['#ef4444', '#ef4444'], 6: ['#ef4444', '#ef4444'], 8: ['#ef4444', '#ef4444'],
}

const ColorScene: React.FC = () => (
  <>
    <Bg id="wg" from="#6d28d9" to="#3b0764" />
    {/* scaled down and lowered so the two-line title stays clear */}
    <g transform="translate(27.5 148) scale(0.9) translate(-14 -118)">
    <rect x={14} y={118} width={272} height={270} rx={18} fill="#fff" />
    <text x={30} y={146} fontSize={12} fontWeight={700} fill="#6b7280" fontFamily="Arial, sans-serif">WinGo 1 Min</text>
    <g>{['0', '0', ':', '2', '7'].map((c, i) => (
      <g key={i}>{c === ':' ? <text x={198 + i * 17} y={147} fontSize={16} fontWeight={900} fill="#111827">:</text> : <><rect x={190 + i * 17} y={130} width={15} height={22} rx={3} fill="#111827" /><text x={197.5 + i * 17} y={147} fontSize={15} fontWeight={800} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">{c}</text></>}</g>
    ))}</g>
    <g>
      {[['Green', '#22c55e'], ['Violet', '#8b5cf6'], ['Red', '#ef4444']].map(([label, fill], i) => (
        <g key={label}><rect x={28 + i * 84} y={166} width={76} height={34} rx={10} fill={fill} /><text x={66 + i * 84} y={188} fontSize={14} fontWeight={800} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">{label}</text></g>
      ))}
    </g>
    <defs>{Object.entries(WINGO_BALL).map(([n, [a, b]]) => (
      <linearGradient key={n} id={`wb${n}`} x1="0" y1="0" x2="1" y2="1"><stop offset="0.5" stopColor={a} /><stop offset="0.5" stopColor={b} /></linearGradient>
    ))}</defs>
    {Array.from({ length: 10 }, (_, n) => {
      const cx = 48 + (n % 5) * 51, cy = 236 + Math.floor(n / 5) * 54
      return (
        <g key={n}>
          <circle cx={cx} cy={cy} r={22} fill={`url(#wb${n})`} />
          <circle cx={cx} cy={cy} r={15} fill="#fff" />
          <text x={cx} y={cy + 6} fontSize={17} fontWeight={900} textAnchor="middle" fill={WINGO_BALL[n][0]} fontFamily="Arial, sans-serif">{n}</text>
        </g>
      )
    })}
    <rect x={28} y={334} width={120} height={36} rx={18} fill="#f59e0b" /><text x={88} y={357} fontSize={15} fontWeight={800} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">Big</text>
    <rect x={152} y={334} width={120} height={36} rx={18} fill="#3b82f6" /><text x={212} y={357} fontSize={15} fontWeight={800} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">Small</text>
    </g>
  </>
)

const Gem: React.FC<{ x: number; y: number; s: number }> = ({ x, y, s }) => (
  <g>
    <polygon points={`${x},${y - s} ${x + s},${y - s * 0.2} ${x},${y + s} ${x - s},${y - s * 0.2}`} fill="#22c55e" />
    <polygon points={`${x},${y - s} ${x + s},${y - s * 0.2} ${x},${y - s * 0.05}`} fill="#86efac" />
    <polygon points={`${x - s},${y - s * 0.2} ${x},${y - s * 0.05} ${x},${y + s}`} fill="#15803d" />
  </g>
)

const Bomb: React.FC<{ x: number; y: number; s: number }> = ({ x, y, s }) => (
  <g>
    <circle cx={x} cy={y + s * 0.15} r={s * 0.75} fill="#1f1235" />
    <circle cx={x - s * 0.25} cy={y - s * 0.1} r={s * 0.2} fill="#7c3aed" opacity={0.7} />
    <path d={`M${x + s * 0.45},${y - s * 0.45} q${s * 0.35},${-s * 0.3} ${s * 0.55},${-s * 0.05}`} stroke="#d4a373" strokeWidth={2} fill="none" />
    <circle cx={x + s * 1.02} cy={y - s * 0.52} r={s * 0.22} fill="#f97316" />
  </g>
)

const MinesScene: React.FC = () => {
  const gems = new Set([1, 6, 8, 12, 17, 22]), bomb = 13
  return (
    <>
      <Bg id="mn" from="#0b1d4d" to="#020617" glow="rgba(59,130,246,0.25)" />
      <Pill x={150} y={136} text="3 mines · next 3.28x" size={13} fill="rgba(37,99,235,0.85)" />
      {Array.from({ length: 25 }, (_, i) => {
        const x = 24 + (i % 5) * 52, y = 160 + Math.floor(i / 5) * 46
        const open = gems.has(i) || i === bomb
        return (
          <g key={i}>
            <rect x={x} y={y + 3} width={46} height={40} rx={8} fill="#000" opacity={0.35} />
            <rect x={x} y={y} width={46} height={40} rx={8} fill={i === bomb ? '#7f1d1d' : open ? '#0f2f6b' : '#2b4a8f'} stroke={open ? '#60a5fa' : '#3b5ea8'} />
            {gems.has(i) && <Gem x={x + 23} y={y + 20} s={13} />}
            {i === bomb && <Bomb x={x + 21} y={y + 20} s={14} />}
          </g>
        )
      })}
    </>
  )
}

// ------------------------------------------------------------------ coming-soon templates
const CrashScene: React.FC<{ id: string; from: string; to: string; line: string; icon: string; mult: string }> = ({ id, from, to, line, icon, mult }) => (
  <>
    <Bg id={id} from={from} to={to} />
    <Rays cx={20} cy={385} color="#fff" n={20} opacity={0.06} />
    <path d="M20,380 Q170,375 235,205 L235,380 Z" fill={line} opacity={0.3} />
    <path d="M20,380 Q170,375 235,205" fill="none" stroke={line} strokeWidth={5} strokeLinecap="round" />
    <Emoji x={248} y={190} size={44} rot={-30}>{icon}</Emoji>
    <text x={125} y={300} fontSize={46} fontWeight={900} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">{mult}</text>
  </>
)

const CardTableScene: React.FC<{ id: string; felt: string; labels: [string, string]; left: [string, string][]; right: [string, string][]; center?: [string, string] }> = ({ id, felt, labels, left, right, center }) => (
  <>
    <Bg id={id} from={felt} to="#020617" glow="rgba(255,255,255,0.12)" />
    <rect x={14} y={150} width={128} height={168} rx={14} fill="rgba(0,0,0,0.25)" stroke="rgba(255,255,255,0.35)" />
    <rect x={158} y={150} width={128} height={168} rx={14} fill="rgba(0,0,0,0.25)" stroke="rgba(255,255,255,0.35)" />
    <text x={78} y={174} fontSize={14} fontWeight={900} textAnchor="middle" fill="#fde68a" fontFamily="Arial, sans-serif">{labels[0]}</text>
    <text x={222} y={174} fontSize={14} fontWeight={900} textAnchor="middle" fill="#fde68a" fontFamily="Arial, sans-serif">{labels[1]}</text>
    {left.map(([r, s], i) => <Card key={`l${i}`} x={30 + i * 26} y={196 + i * 4} rank={r} suit={s} w={48} rot={-8 + i * 8} />)}
    {right.map(([r, s], i) => <Card key={`r${i}`} x={174 + i * 26} y={196 + i * 4} rank={r} suit={s} w={48} rot={-8 + i * 8} />)}
    {center && <Card x={124} y={330} rank={center[0]} suit={center[1]} w={52} />}
    {!center && <><Chip x={120} y={355} color="#dc2626" label="100" /><Chip x={180} y={355} color="#2563eb" label="500" /></>}
  </>
)

const SlotsScene: React.FC<{ id: string; from: string; to: string; symbols: string[] }> = ({ id, from, to, symbols }) => (
  <>
    <Bg id={id} from={from} to={to} />
    <rect x={22} y={140} width={256} height={210} rx={20} fill="#3b0764" stroke="#fbbf24" strokeWidth={6} />
    {Array.from({ length: 9 }, (_, i) => {
      const x = 36 + (i % 3) * 78, y = 154 + Math.floor(i / 3) * 62
      return (
        <g key={i}>
          <rect x={x} y={y} width={72} height={56} rx={8} fill="#fff" />
          <Emoji x={x + 36} y={y + 30} size={34}>{symbols[i % symbols.length]}</Emoji>
        </g>
      )
    })}
    <line x1={30} x2={270} y1={247} y2={247} stroke="#ef4444" strokeWidth={3} opacity={0.8} />
    <Pill x={150} y={380} text="WIN 25x" size={15} fill="#f59e0b" />
  </>
)

const FieldScene: React.FC<{ id: string; grass: string; kind: 'cricket' | 'football' | 'kabaddi' | 'tennis'; icon: string; score: string }> = ({ id, grass, kind, icon, score }) => (
  <>
    <Bg id={id} from={grass} to="#052e16" glow="rgba(255,255,255,0.15)" />
    {kind === 'cricket' && <><ellipse cx={150} cy={265} rx={135} ry={120} fill="none" stroke="#fff" strokeOpacity={0.5} strokeWidth={2} /><rect x={135} y={200} width={30} height={130} fill="#d6b97b" /><line x1={135} x2={165} y1={215} y2={215} stroke="#fff" strokeWidth={2} /><line x1={135} x2={165} y1={315} y2={315} stroke="#fff" strokeWidth={2} /></>}
    {kind === 'football' && <><rect x={20} y={150} width={260} height={230} fill="none" stroke="#fff" strokeOpacity={0.6} strokeWidth={2} /><line x1={20} x2={280} y1={265} y2={265} stroke="#fff" strokeOpacity={0.6} strokeWidth={2} /><circle cx={150} cy={265} r={36} fill="none" stroke="#fff" strokeOpacity={0.6} strokeWidth={2} /><rect x={95} y={150} width={110} height={40} fill="none" stroke="#fff" strokeOpacity={0.6} strokeWidth={2} /></>}
    {kind === 'kabaddi' && <><rect x={20} y={150} width={260} height={230} fill="#d97706" opacity={0.6} /><line x1={150} x2={150} y1={150} y2={380} stroke="#fff" strokeWidth={3} /><line x1={80} x2={80} y1={150} y2={380} stroke="#fff" strokeOpacity={0.6} strokeWidth={2} strokeDasharray="6 5" /><line x1={220} x2={220} y1={150} y2={380} stroke="#fff" strokeOpacity={0.6} strokeWidth={2} strokeDasharray="6 5" /></>}
    {kind === 'tennis' && <><rect x={40} y={150} width={220} height={230} fill="#1d4ed8" opacity={0.75} /><rect x={40} y={150} width={220} height={230} fill="none" stroke="#fff" strokeWidth={2} /><line x1={40} x2={260} y1={265} y2={265} stroke="#fff" strokeWidth={3} /><line x1={150} x2={150} y1={205} y2={325} stroke="#fff" strokeWidth={2} /><line x1={70} x2={230} y1={205} y2={205} stroke="#fff" strokeWidth={2} /><line x1={70} x2={230} y1={325} y2={325} stroke="#fff" strokeWidth={2} /></>}
    <Emoji x={210} y={300} size={58}>{icon}</Emoji>
    <Pill x={150} y={140} text={score} size={13} fill="rgba(0,0,0,0.65)" color="#fde68a" />
  </>
)

const WheelScene: React.FC<{ id: string; from: string; to: string; colors: string[]; labels?: string[] }> = ({ id, from, to, colors, labels }) => {
  const n = colors.length, cx = 150, cy = 265, r = 112
  return (
    <>
      <Bg id={id} from={from} to={to} />
      <circle cx={cx} cy={cy + 4} r={r + 10} fill="#000" opacity={0.35} />
      <circle cx={cx} cy={cy} r={r + 10} fill="#78350f" stroke="#fbbf24" strokeWidth={4} />
      {colors.map((c, i) => {
        const a1 = (i / n) * Math.PI * 2 - Math.PI / 2, a2 = ((i + 1) / n) * Math.PI * 2 - Math.PI / 2, am = (a1 + a2) / 2
        return (
          <g key={i}>
            <path d={`M${cx},${cy} L${cx + r * Math.cos(a1)},${cy + r * Math.sin(a1)} A${r},${r} 0 0 1 ${cx + r * Math.cos(a2)},${cy + r * Math.sin(a2)} Z`} fill={c} stroke="#fde68a" strokeWidth={1} />
            {labels && <text x={cx + r * 0.78 * Math.cos(am)} y={cy + r * 0.78 * Math.sin(am) + 4} fontSize={11} fontWeight={800} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">{labels[i]}</text>}
          </g>
        )
      })}
      <circle cx={cx} cy={cy} r={24} fill="#fbbf24" stroke="#78350f" strokeWidth={4} />
      <polygon points={`${cx - 12},${cy - r - 22} ${cx + 12},${cy - r - 22} ${cx},${cy - r + 4}`} fill="#fff" stroke="#111" />
    </>
  )
}

const DiceFace: React.FC<{ x: number; y: number; s: number; v: number; rot?: number }> = ({ x, y, s, v, rot = 0 }) => {
  const P: Record<number, [number, number][]> = { 1: [[.5, .5]], 2: [[.25, .25], [.75, .75]], 3: [[.25, .25], [.5, .5], [.75, .75]], 4: [[.25, .25], [.75, .25], [.25, .75], [.75, .75]], 5: [[.25, .25], [.75, .25], [.5, .5], [.25, .75], [.75, .75]], 6: [[.25, .22], [.75, .22], [.25, .5], [.75, .5], [.25, .78], [.75, .78]] }
  return (
    <g transform={`rotate(${rot} ${x + s / 2} ${y + s / 2})`}>
      <rect x={x + 3} y={y + 5} width={s} height={s} rx={s * 0.18} fill="#000" opacity={0.35} />
      <rect x={x} y={y} width={s} height={s} rx={s * 0.18} fill="#fff" />
      {P[v].map(([px, py], i) => <circle key={i} cx={x + px * s} cy={y + py * s} r={s * 0.08} fill={v === 1 ? '#dc2626' : '#111827'} />)}
    </g>
  )
}

// ------------------------------------------------------------------ catalogue
const SCENES: Record<string, () => React.ReactElement> = {
  aviator: () => <AviatorScene />,
  teen_patti: () => <TeenPattiScene />,
  color: () => <ColorScene />,
  mines: () => <MinesScene />,

  rocket: () => <CrashScene id="rk" from="#312e81" to="#0f0a2e" line="#a78bfa" icon="🚀" mult="5.82x" />,
  limbo: () => <CrashScene id="lb" from="#365314" to="#0b1a05" line="#a3e635" icon="🎯" mult="10.00x" />,
  chicken: () => (
    <>
      <Bg id="ck" from="#1e293b" to="#020617" />
      {[0, 1, 2, 3].map((i) => <rect key={i} x={i * 75} y={150} width={73} height={230} fill={i % 2 ? '#334155' : '#1e293b'} />)}
      {[0, 1, 2, 3].map((i) => <line key={`d${i}`} x1={i * 75 + 74} x2={i * 75 + 74} y1={150} y2={380} stroke="#facc15" strokeWidth={2} strokeDasharray="10 8" />)}
      {['1.2x', '1.5x', '2.1x', '3.4x'].map((m, i) => <g key={m}><circle cx={37 + i * 75} cy={270} r={26} fill="#0f172a" stroke="#64748b" strokeWidth={3} /><text x={37 + i * 75} y={275} fontSize={13} fontWeight={800} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">{m}</text></g>)}
      <Emoji x={112} y={215} size={42}>🐔</Emoji>
      <Emoji x={190} y={345} size={40}>🚗</Emoji>
    </>
  ),
  coinflip: () => (
    <>
      <Bg id="cf" from="#b45309" to="#451a03" glow="rgba(253,224,71,0.35)" />
      <ellipse cx={150} cy={360} rx={80} ry={12} fill="#000" opacity={0.3} />
      <circle cx={150} cy={258} r={86} fill="#ca8a04" />
      <circle cx={150} cy={252} r={86} fill="#facc15" />
      <circle cx={150} cy={252} r={68} fill="none" stroke="#a16207" strokeWidth={5} />
      <text x={150} y={276} fontSize={70} fontWeight={900} textAnchor="middle" fill="#a16207" fontFamily="Arial, sans-serif">₹</text>
      <Pill x={80} y={385} text="Heads" size={13} fill="#1d4ed8" /><Pill x={220} y={385} text="Tails" size={13} fill="#be123c" />
    </>
  ),
  plinko: () => (
    <>
      <Bg id="pl" from="#831843" to="#1f0614" />
      {Array.from({ length: 8 }, (_, row) => Array.from({ length: row + 3 }, (_, k) => (
        <circle key={`${row}-${k}`} cx={150 - (row + 2) * 14 + k * 28} cy={150 + row * 26} r={4} fill="#fff" />
      )))}
      <circle cx={164} cy={228} r={9} fill="#f472b6" stroke="#fff" strokeWidth={2} />
      {['10x', '3x', '1.5x', '0.5x', '0.3x', '0.5x', '1.5x', '3x', '10x'].map((m, i) => (
        <g key={i}><rect x={20 + i * 29} y={360} width={26} height={22} rx={5} fill={i === 0 || i === 8 ? '#ef4444' : i === 4 ? '#facc15' : '#f97316'} /><text x={33 + i * 29} y={375} fontSize={8} fontWeight={800} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">{m}</text></g>
      ))}
    </>
  ),
  dice: () => (
    <>
      <Bg id="dc" from="#0e7490" to="#042f2e" />
      <DiceFace x={58} y={185} s={84} v={5} rot={-12} />
      <DiceFace x={160} y={205} s={84} v={3} rot={10} />
      <rect x={30} y={330} width={240} height={12} rx={6} fill="#0f172a" />
      <rect x={30} y={330} width={120} height={12} rx={6} fill="#22c55e" />
      <circle cx={150} cy={336} r={12} fill="#fff" stroke="#0f172a" strokeWidth={3} />
      <Pill x={150} y={378} text="Roll under 50 · 1.98x" size={12} />
    </>
  ),
  andar_bahar: () => <CardTableScene id="ab" felt="#7f1d1d" labels={['ANDAR', 'BAHAR']} left={[['3', '♣'], ['9', '♥']]} right={[['K', '♦'], ['7', '♠']]} center={['9', '♠']} />,
  dragon_tiger: () => (
    <>
      <CardTableScene id="dt" felt="#9a3412" labels={['DRAGON', 'TIGER']} left={[['K', '♥']]} right={[['8', '♣']]} />
      <Emoji x={78} y={300} size={34}>🐉</Emoji><Emoji x={222} y={300} size={34}>🐯</Emoji>
    </>
  ),
  baccarat: () => <CardTableScene id="bc" felt="#854d0e" labels={['PLAYER', 'BANKER']} left={[['8', '♦'], ['A', '♣']]} right={[['5', '♠'], ['2', '♥']]} />,
  blackjack: () => (
    <>
      <Bg id="bj" from="#14532d" to="#020617" glow="rgba(255,255,255,0.12)" />
      <path d="M20,150 A140,140 0 0 0 280,150" fill="none" stroke="#fde68a" strokeOpacity={0.6} strokeWidth={2} />
      <text x={150} y={190} fontSize={11} fontWeight={800} textAnchor="middle" fill="#fde68a" fontFamily="Arial, sans-serif">BLACKJACK PAYS 3 TO 2</text>
      <Card x={88} y={215} rank="A" suit="♠" w={58} rot={-8} />
      <Card x={146} y={215} rank="K" suit="♥" w={58} rot={8} />
      <Pill x={150} y={350} text="21" size={22} fill="#16a34a" />
    </>
  ),
  poker: () => (
    <>
      <Bg id="pk" from="#155e75" to="#020617" />
      <ellipse cx={150} cy={270} rx={145} ry={110} fill="#0e7490" stroke="#082f49" strokeWidth={8} />
      {[['A', '♥'], ['K', '♥'], ['Q', '♥'], ['J', '♥'], ['10', '♥']].map(([r, s], i) => <Card key={r} x={28 + i * 50} y={225} rank={r} suit={s} w={44} />)}
      <Chip x={110} y={340} color="#111827" label="1K" /><Chip x={150} y={346} color="#dc2626" label="500" /><Chip x={190} y={340} color="#16a34a" label="100" />
    </>
  ),
  roulette: () => <WheelScene id="rl" from="#14532d" to="#020617" colors={Array.from({ length: 18 }, (_, i) => (i === 0 ? '#16a34a' : i % 2 ? '#dc2626' : '#111827'))} labels={['0', '32', '15', '19', '4', '21', '2', '25', '17', '34', '6', '27', '13', '36', '11', '30', '8', '23']} />,
  wheel: () => <WheelScene id="wh" from="#0f766e" to="#042f2e" colors={['#ef4444', '#f59e0b', '#22c55e', '#3b82f6', '#a855f7', '#ec4899', '#ef4444', '#f59e0b', '#22c55e', '#3b82f6']} labels={['2x', '5x', '1x', '3x', '10x', '2x', '1x', '5x', '50x', '3x']} />,
  gems: () => <SlotsScene id="sg" from="#c2410c" to="#431407" symbols={['💎', '👑', '💎', '🔔', '💎', '💰', '👑', '💎', '🔔']} />,
  rabbit: () => <SlotsScene id="sr" from="#a21caf" to="#2e0533" symbols={['🐰', '🥕', '🍀', '🥕', '🐰', '🐰', '🍀', '🥕', '🐰']} />,
  sevens: () => <SlotsScene id="s7" from="#ca8a04" to="#422006" symbols={['7️⃣', '🍒', '🔔', '⭐', '7️⃣', '🍋', '🔔', '🍒', '7️⃣']} />,
  fruits: () => <SlotsScene id="sf" from="#be123c" to="#4c0519" symbols={['🍒', '🍋', '🍉', '🍇', '🍒', '🍊', '🍉', '🍇', '🍒']} />,
  keno: () => (
    <>
      <Bg id="kn" from="#3730a3" to="#0b0a2e" />
      {Array.from({ length: 40 }, (_, i) => {
        const hit = [3, 9, 14, 18, 22, 27, 31, 36].includes(i), picked = [9, 18, 27, 33].includes(i)
        const x = 22 + (i % 8) * 33, y = 160 + Math.floor(i / 8) * 40
        return <g key={i}><rect x={x} y={y} width={29} height={34} rx={6} fill={hit && picked ? '#22c55e' : hit ? '#f59e0b' : picked ? '#3b82f6' : 'rgba(255,255,255,0.12)'} /><text x={x + 14.5} y={y + 22} fontSize={12} fontWeight={800} textAnchor="middle" fill="#fff" fontFamily="Arial, sans-serif">{i + 1}</text></g>
      })}
      <Pill x={150} y={378} text="3 of 4 hits · 12x" size={12} />
    </>
  ),
  cricket: () => <FieldScene id="fc" grass="#15803d" kind="cricket" icon="🏏" score="IND 182/4 (18.2)" />,
  football: () => <FieldScene id="ff" grass="#166534" kind="football" icon="⚽" score="2 : 1  · 78'" />,
  kabaddi: () => <FieldScene id="fk" grass="#9a3412" kind="kabaddi" icon="🤼" score="PAT 32 – 29 BEN" />,
  tennis: () => <FieldScene id="ft" grass="#3f6212" kind="tennis" icon="🎾" score="6-4  3-2  40-15" />,
}

export const hasGameArt = (id: string): boolean => id in SCENES

/** The scene for a lobby game, filling its tile. */
export const GameArt: React.FC<{ id: string; className?: string }> = ({ id, className = '' }) => {
  const Scene = SCENES[id]
  if (!Scene) return null
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid slice" className={className} aria-hidden>
      <Scene />
    </svg>
  )
}
