// Simple crop pictures (drawn, no external images) used in the season simulation.
type P = { size?: number }
const S = ({ size = 56, children }: { size?: number; children: React.ReactNode }) =>
  <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">{children}</svg>

const Maize = ({ size }: P) => <S size={size}>
  <path d="M32 60V30" stroke="#3E7B4A" strokeWidth="3" strokeLinecap="round" />
  <path d="M32 44c-10-2-16-10-18-18 8 2 14 8 18 14M32 38c10-2 15-10 17-17-8 2-13 8-17 13" fill="#5E9C5A" />
  <ellipse cx="38" cy="22" rx="6" ry="13" fill="#E8B53A" transform="rotate(18 38 22)" />
  <path d="M35 12l5 20M33 16l7 2M32 21l9 2M32 26l8 2" stroke="#C9952A" strokeWidth="1.2" />
  <path d="M33 34c-3-8-1-18 3-24" stroke="#7FB06A" strokeWidth="3" fill="none" />
</S>
const Tomato = ({ size }: P) => <S size={size}>
  <circle cx="32" cy="38" r="17" fill="#D9503C" /><circle cx="26" cy="33" r="4" fill="#F08A70" opacity=".7" />
  <path d="M32 22l-8-5 6 1-2-7 4 6 4-6-2 7 6-1z" fill="#3E7B4A" />
</S>
const Onion = ({ size }: P) => <S size={size}>
  <path d="M32 58c-12 0-18-8-18-16 0-10 10-16 18-26 8 10 18 16 18 26 0 8-6 16-18 16z" fill="#C98A5A" />
  <path d="M32 58c-5-6-6-20 0-42M32 58c5-6 6-20 0-42" stroke="#A86A3E" strokeWidth="1.5" fill="none" />
  <path d="M31 17c-2-6-1-11 1-14M33 17c2-5 4-8 6-10" stroke="#5E9C5A" strokeWidth="2.5" strokeLinecap="round" />
</S>
const Cabbage = ({ size }: P) => <S size={size}>
  <circle cx="32" cy="36" r="20" fill="#7DB36A" /><circle cx="32" cy="36" r="13" fill="#A8D08A" />
  <path d="M32 23c-6 4-6 22 0 26M32 23c6 4 6 22 0 26M19 36c6-5 20-5 26 0" stroke="#5E9C5A" strokeWidth="1.5" fill="none" />
</S>
const Pod = ({ size, nut }: P & { nut?: boolean }) => <S size={size}>
  <path d="M10 44c6-18 26-30 44-30-4 18-24 32-44 30z" fill={nut ? '#D4B07A' : '#6FA85A'} />
  {[0, 1, 2, 3].map(i => <circle key={i} cx={20 + i * 8} cy={38 - i * 5} r="4" fill={nut ? '#B8925A' : '#9CCB7A'} />)}
  <path d="M54 14c2-4 5-6 8-6" stroke="#3E7B4A" strokeWidth="2.5" strokeLinecap="round" />
</S>
const SweetPotato = ({ size }: P) => <S size={size}>
  <path d="M8 40c4-12 20-20 36-18 10 2 14 8 12 14-4 10-22 16-36 14C10 49 6 45 8 40z" fill="#B85C4A" />
  <path d="M20 34l2 3M34 30l2 3M44 36l2 2M28 42l2 2" stroke="#8E3F32" strokeWidth="1.6" strokeLinecap="round" />
  <path d="M48 24c2-6 6-10 10-12M50 24c4-3 8-4 11-3" stroke="#5E9C5A" strokeWidth="2.5" strokeLinecap="round" />
</S>
const Bare = ({ size }: P) => <S size={size}>
  <path d="M6 46h52" stroke="#B39A6A" strokeWidth="3" strokeDasharray="4 4" />
  <path d="M10 52h44" stroke="#C9B58A" strokeWidth="2" strokeDasharray="3 5" />
</S>

export function CropPic({ id, size = 56 }: { id: string; size?: number }) {
  switch (id) {
    case 'maize': return <Maize size={size} />
    case 'tomato': return <Tomato size={size} />
    case 'onion': return <Onion size={size} />
    case 'cabbage': return <Cabbage size={size} />
    case 'cowpea': return <Pod size={size} />
    case 'groundnut': return <Pod size={size} nut />
    case 'sweet_potato': return <SweetPotato size={size} />
    default: return <Bare size={size} />
  }
}

// Growth stages shown month by month in the season simulation.
const Seed = ({ size }: P) => <S size={size}>
  <ellipse cx="32" cy="48" rx="7" ry="5" fill="#9A6B3C" /><path d="M27 47c3-2 7-2 10 0" stroke="#7A512A" strokeWidth="1.5" fill="none" />
</S>
const Sprout = ({ size }: P) => <S size={size}>
  <path d="M32 56V40" stroke="#4E8A4A" strokeWidth="3" strokeLinecap="round" />
  <path d="M32 42c-8 0-12-5-12-10 7 0 12 4 12 10zM32 42c8 0 12-5 12-10-7 0-12 4-12 10z" fill="#7FBF6A" />
</S>
const Leafy = ({ size }: P) => <S size={size}>
  <path d="M32 58V26" stroke="#3E7B4A" strokeWidth="3" strokeLinecap="round" />
  <path d="M32 50c-12-1-18-8-19-15 9 1 16 7 19 15zM32 50c12-1 18-8 19-15-9 1-16 7-19 15zM32 38c-9-2-13-9-13-15 7 2 12 8 13 15zM32 38c9-2 13-9 13-15-7 2-12 8-13 15z" fill="#5E9C5A" />
  <path d="M32 28c-3-6-2-12 0-16 2 4 3 10 0 16z" fill="#7FBF6A" />
</S>
const Flowering = ({ size }: P) => <S size={size}>
  <path d="M32 58V22" stroke="#3E7B4A" strokeWidth="3" strokeLinecap="round" />
  <path d="M32 50c-12-1-18-8-19-15 9 1 16 7 19 15zM32 50c12-1 18-8 19-15-9 1-16 7-19 15zM32 38c-9-2-13-9-13-15 7 2 12 8 13 15zM32 38c9-2 13-9 13-15-7 2-12 8-13 15z" fill="#5E9C5A" />
  {[[32, 16], [21, 22], [43, 22]].map(([x, y], i) => <g key={i}>{[0, 72, 144, 216, 288].map(a => <circle key={a} cx={x + 3.2 * Math.cos(a * Math.PI / 180)} cy={y + 3.2 * Math.sin(a * Math.PI / 180)} r="2.6" fill="#F4D35E" />)}<circle cx={x} cy={y} r="1.8" fill="#C98B00" /></g>)}
</S>
export const STAGES = ['Seed', 'Sprout', 'Leaves', 'Flowering', 'Harvest'] as const
export function StagePic({ stage, id, size = 56 }: { stage: number; id: string; size?: number }) {
  if (stage <= 0) return <Seed size={size} />
  if (stage === 1) return <Sprout size={size} />
  if (stage === 2) return <Leafy size={size} />
  if (stage === 3) return <Flowering size={size} />
  return <CropPic id={id} size={size} />
}
