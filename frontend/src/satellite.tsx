// Real satellite view of the field outline, anywhere in the world.
// Tiles: Sentinel-2 cloudless by EOX (ESA Copernicus data, 10 m), with Esri World Imagery as backup.
import { useMemo, useState } from 'react'

const Z = 17, T = 256
const lon2x = (lon: number) => ((lon + 180) / 360) * 2 ** Z * T
const lat2y = (lat: number) => { const r = (lat * Math.PI) / 180; return ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * 2 ** Z * T }

const SOURCES = [
  { name: 'Sentinel-2 cloudless 2021 · EOX · contains modified Copernicus data', url: (z: number, x: number, y: number) => `https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/${z}/${y}/${x}.jpg` },
  { name: 'Esri World Imagery', url: (z: number, x: number, y: number) => `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${z}/${y}/${x}` },
]

const x2lon = (x: number) => (x / (2 ** Z * T)) * 360 - 180
const y2lat = (y: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / (2 ** Z * T)))) * 180) / Math.PI

export function SatelliteField({ ring, label, draft, onTap }: { ring: number[][]; label: string; draft?: number[][]; onTap?: (lon: number, lat: number) => void }) {
  const [src, setSrc] = useState(0)
  const view = useMemo(() => {
    const xs = ring.map(c => lon2x(c[0])), ys = ring.map(c => lat2y(c[1]))
    const cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2
    const W = 600, H = 360, x0 = cx - W / 2, y0 = cy - H / 2
    const tiles: { x: number; y: number; left: number; top: number }[] = []
    for (let tx = Math.floor(x0 / T); tx <= Math.floor((x0 + W) / T); tx++)
      for (let ty = Math.floor(y0 / T); ty <= Math.floor((y0 + H) / T); ty++)
        tiles.push({ x: tx, y: ty, left: tx * T - x0, top: ty * T - y0 })
    const pts = ring.map(c => `${(lon2x(c[0]) - x0).toFixed(1)},${(lat2y(c[1]) - y0).toFixed(1)}`).join(' ')
    return { W, H, tiles, pts, x0, y0 }
  }, [ring])
  const S = SOURCES[src]
  return (
    <div style={{ position: 'relative', width: '100%', overflow: 'hidden', borderRadius: 14, background: '#3E5A3A' }}>
      <svg viewBox={`0 0 ${view.W} ${view.H}`} width="100%" style={{ display: 'block', cursor: onTap ? 'crosshair' : undefined }} aria-label="Satellite view of the field"
        onClick={onTap ? e => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const x = ((e.clientX - r.left) / r.width) * view.W + view.x0, y = ((e.clientY - r.top) / r.height) * view.H + view.y0; onTap(+x2lon(x).toFixed(7), +y2lat(y).toFixed(7)) } : undefined}>
        {view.tiles.map(t => <image key={`${t.x}-${t.y}-${src}`} href={S.url(Z, t.x, t.y)} x={t.left} y={t.top} width={T} height={T}
          onError={() => src < SOURCES.length - 1 && setSrc(src + 1)} />)}
        {!draft && <polygon points={view.pts} fill="rgba(201,226,154,0.18)" stroke="#E9F7C8" strokeWidth={3} />}
        {draft && draft.length > 0 && (() => {
          const pp = draft.map(c => `${(lon2x(c[0]) - view.x0).toFixed(1)},${(lat2y(c[1]) - view.y0).toFixed(1)}`)
          return <>{draft.length > 2 ? <polygon points={pp.join(' ')} fill="rgba(251,191,36,0.25)" stroke="#FBBF24" strokeWidth={3} /> : <polyline points={pp.join(' ')} fill="none" stroke="#FBBF24" strokeWidth={3} />}
            {pp.map((q, k) => { const [a, b] = q.split(',').map(Number); return <circle key={k} cx={a} cy={b} r={6} fill="#FBBF24" stroke="#fff" strokeWidth={2} /> })}</>
        })()}
      </svg>
      <span style={{ position: 'absolute', left: 10, bottom: 8, fontSize: 10.5, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,.6)' }}>{label}</span>
      <span style={{ position: 'absolute', right: 8, top: 6, fontSize: 9, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,.7)', maxWidth: '70%', textAlign: 'right' }}>{S.name}</span>
    </div>
  )
}

/** Satellite picture of a place today, centred on a point (used for climate twins). */
export function SatellitePlace({ lat, lon, zoom = 11, label }: { lat: number; lon: number; zoom?: number; label: string }) {
  const [src, setSrc] = useState(0)
  const W = 600, H = 300
  const n = 2 ** zoom
  const cx = ((lon + 180) / 360) * n * T
  const r = (lat * Math.PI) / 180
  const cy = ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n * T
  const x0 = cx - W / 2, y0 = cy - H / 2
  const tiles: { x: number; y: number; left: number; top: number }[] = []
  for (let tx = Math.floor(x0 / T); tx <= Math.floor((x0 + W) / T); tx++)
    for (let ty = Math.floor(y0 / T); ty <= Math.floor((y0 + H) / T); ty++)
      tiles.push({ x: ((tx % n) + n) % n, y: ty, left: tx * T - x0, top: ty * T - y0 })
  const S = SOURCES[src]
  return (
    <div style={{ position: 'relative', width: '100%', overflow: 'hidden', borderRadius: 12, background: '#3E5A3A' }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }} aria-label={`Satellite view of ${label}`}>
        {tiles.map(t => <image key={`${t.x}-${t.y}-${t.left}-${src}`} href={S.url(zoom, t.x, t.y)} x={t.left} y={t.top} width={T} height={T}
          onError={() => src < SOURCES.length - 1 && setSrc(src + 1)} />)}
        <circle cx={W / 2} cy={H / 2} r={7} fill="none" stroke="#fff" strokeWidth={2.5} />
      </svg>
      <span style={{ position: 'absolute', left: 10, bottom: 8, fontSize: 11, fontWeight: 700, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,.7)' }}>{label} today</span>
      <span style={{ position: 'absolute', right: 8, top: 6, fontSize: 9, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,.7)', maxWidth: '70%', textAlign: 'right' }}>{S.name}</span>
    </div>
  )
}
