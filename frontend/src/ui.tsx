import type { ReactNode } from 'react'
import type { Source } from './api'

export const C = { deep: '#0C4A44', teal: '#0C8A84', hero: '#1F4D3A', lime: '#C9E29A', red: '#B5523A', gold: '#C98B00', mut: '#6B7C77', faint: '#8A9A95', water: '#3B7EA1', ink: '#10302C', line: '#E5EBE7' }

export const Icon = ({ d, c = C.deep, s = 19 }: { d: string; c?: string; s?: number }) => (
  <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>
)
export const I = {
  leaf: 'M12 20v-8 M12 12c0-3.5 2.5-6 7-6 0 4.5-2.5 6-7 6z M12 15c0-3-2-5-6-5 0 4 2 5 6 5z',
  chat: 'M4 5h16v11H9l-5 4z',
  doc: 'M7 3h8l4 4v14H7z M15 3v4h4 M10 12h6 M10 16h6',
  home: 'M4 11l8-7 8 7v9h-5v-6H9v6H4z',
  map: 'M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z M9 4v14 M15 6v14',
  plans: 'M12 3l9 5-9 5-9-5 9-5z M3 13l9 5 9-5',
  drop: 'M12 3s6 6.5 6 11a6 6 0 01-12 0c0-4.5 6-11 6-11z',
  clock: 'M12 7v5l3 2 M3 12a9 9 0 1018 0 9 9 0 00-18 0',
  x: 'M6 6l12 12 M18 6L6 18',
  back: 'M15 6l-6 6 6 6',
  send: 'M5 12h14M13 6l6 6-6 6',
  plus: 'M12 5v14 M5 12h14',
}

const SRC: Record<string, [string, string]> = {
  live: ['#0C8A84', 'Live'], cached: ['#C98B00', 'Cached'], none: ['#B5523A', 'Not available'],
  observed: ['#3B7EA1', 'Observed'], projected: ['#795E22', 'Projected'], modelled: ['#0C8A84', 'Modelled'],
  entered: ['#C98B00', 'You entered'], map: ['#A9BAB5', 'Map estimate'], pending: ['#A9BAB5', 'Not calculated yet'],
}
export const Tag = ({ k, text }: { k: string; text?: string }) => {
  const [c, l] = SRC[k] || ['#A9BAB5', k]
  return <span className="src"><i style={{ background: c }} />{text ?? l}</span>
}
export const SourceTag = ({ s, what }: { s: Source; what?: string }) =>
  <Tag k={s} text={s === 'live' ? `Live${what ? ' · ' + what : ''}` : s === 'cached' ? `Cached${what ? ' · ' + what : ''}` : 'Not available'} />

export const Hero = ({ eyebrow, title, sub, bg = C.hero, children }: { eyebrow: string; title: string; sub?: string; bg?: string; children?: ReactNode }) => (
  <section className="hero" style={{ background: bg }}>
    <svg width="190" height="190" viewBox="0 0 100 100" fill="none" stroke="rgba(255,255,255,0.09)" strokeWidth="1.2" aria-hidden="true" style={{ position: 'absolute', right: -40, bottom: -50 }}>
      <path d="M50 95V45 M50 45C50 22 66 8 92 8c0 28-16 40-42 40z M50 62C50 44 38 32 14 32c0 22 12 32 36 32z" />
    </svg>
    <div className="e"><i /><b>{eyebrow.toUpperCase()}</b></div>
    <div className="t">{title}</div>
    {sub && <div className="s">{sub}</div>}
    {children}
  </section>
)

export const Kpi = ({ v, unit, l, color }: { v: string; unit?: string; l: string; color?: string }) => (
  <div className="kpi"><div className="v" style={{ color }}>{v}{unit && <small> {unit}</small>}</div><div className="l">{l}</div></div>
)

export const Spinner = ({ text }: { text: string }) => <div className="row muted"><span className="spin" />{text}</div>

/** Small line chart in the Vercel style: thin lines, hairline grid, labelled ends. */
export function LineChart({ labels, series, unit, height = 150, min, max, selected, onPick }: {
  labels: string[]; series: { name: string; color: string; values: (number | null)[]; dashed?: boolean; band?: [number, number][] }[]
  unit: string; height?: number; min?: number; max?: number; selected?: number; onPick?: (i: number) => void
}) {
  const W = 318, H = height, top = 12, bottom = H - 22, left = 34, right = W - 10
  const all = series.flatMap(s => [...s.values.filter((v): v is number => v != null), ...(s.band?.flat() ?? [])])
  const lo = min ?? Math.floor(Math.min(...all) - (Math.max(...all) - Math.min(...all)) * 0.15)
  const hi = max ?? Math.ceil(Math.max(...all) + (Math.max(...all) - Math.min(...all)) * 0.15)
  const n = labels.length
  const x = (i: number) => n === 1 ? (left + right) / 2 : left + (i * (right - left)) / (n - 1)
  const y = (v: number) => bottom - ((v - lo) / (hi - lo || 1)) * (bottom - top)
  const fmt = (v: number) => (Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : v.toFixed(1))
  return (
    <div style={{ position: 'relative', height: H }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ position: 'absolute', inset: 0, overflow: 'visible' }} aria-hidden="true">
        {[hi, (hi + lo) / 2, lo].map((g, k) => <line key={k} x1={left} x2={right} y1={y(g)} y2={y(g)} stroke={k === 2 ? C.line : '#EEF2EF'} />)}
        {selected != null && <line x1={x(selected)} x2={x(selected)} y1={top - 4} y2={bottom} stroke="#C9D3CF" />}
        {series.map(s => s.band && (
          <path key={s.name + 'b'} fill={s.color} opacity={0.12}
            d={'M' + s.band.map((b, i) => `${x(i)} ${y(b[1])}`).join(' L') + ' L' + s.band.map((b, i) => `${x(i)} ${y(b[0])}`).reverse().join(' L') + ' Z'} />
        ))}
        {series.map(s => {
          const pts = s.values.map((v, i) => (v == null ? null : `${x(i).toFixed(1)} ${y(v).toFixed(1)}`)).filter(Boolean)
          return <path key={s.name} d={'M' + pts.join(' L')} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? '5 4' : undefined} strokeLinejoin="round" strokeLinecap="round" />
        })}
        {series.map(s => s.values.map((v, i) => v == null ? null :
          <circle key={s.name + i} cx={x(i)} cy={y(v)} r={selected === i ? 4.5 : 3} fill="#fff" stroke={s.color} strokeWidth={2} />))}
      </svg>
      {[hi, lo].map((g, k) => <span key={k} className="faint" style={{ position: 'absolute', left: 0, top: y(g) - 7, background: '#fff', paddingRight: 3 }}>{fmt(g)}</span>)}
      <span className="faint" style={{ position: 'absolute', left: 0, top: (y(hi) + y(lo)) / 2 - 7 }}>{unit}</span>
      {labels.map((l, i) => (
        <button key={l} onClick={onPick ? () => onPick(i) : undefined} style={{ position: 'absolute', left: x(i) - 24, width: 48, top: bottom + 4, border: 0, background: 'transparent', fontSize: 10.5, fontWeight: selected === i ? 700 : 400, color: selected === i ? C.deep : C.faint, padding: 0 }}>{l}</button>
      ))}
      {selected != null && series.map((s, k) => {
        const v = s.values[selected]; if (v == null) return null
        return <span key={s.name} className="an" style={{ position: 'absolute', left: Math.min(x(selected) + 8, W - 56), top: y(v) - 10 + (k ? 0 : 0), fontSize: 11.5, fontWeight: 700, color: '#fff', background: s.color, padding: '2px 6px', borderRadius: 6 }}>{fmt(v)}</span>
      })}
    </div>
  )
}

export function Bars({ items, unit, color = C.water }: { items: { label: string; value: number | null }[]; unit: string; color?: string }) {
  const max = Math.max(1, ...items.map(i => i.value ?? 0))
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 10, height: 130, borderBottom: '1.5px solid #D5DFDB' }}>
      {items.map(i => (
        <div key={i.label} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, height: '100%', justifyContent: 'flex-end' }}>
          <span style={{ fontSize: 11.5, fontWeight: 700 }}>{i.value == null ? '–' : Math.round(i.value)}<span className="faint"> {unit}</span></span>
          <span className="an" style={{ width: '70%', height: `${((i.value ?? 0) / max) * 95}px`, background: color, borderRadius: '5px 5px 0 0' }} />
        </div>
      ))}
    </div>
  )
}
