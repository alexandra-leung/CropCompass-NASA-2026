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

export function SatelliteField({ ring, label, draft, onTap, grid, edit, onEdit }: { ring: number[][]; label: string; draft?: number[][]; onTap?: (lon: number, lat: number) => void; grid?: { cells: number[][]; half: number[] }; edit?: number[][]; onEdit?: (i: number, lon: number, lat: number) => void }) {
  const [src, setSrc] = useState(1)
  const [drag, setDrag] = useState<number | null>(null)
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
      <svg viewBox={`0 0 ${view.W} ${view.H}`} width="100%" style={{ display: 'block', cursor: onTap ? 'crosshair' : undefined, touchAction: edit ? 'none' : undefined }} aria-label="Satellite view of the field"
        onPointerMove={edit && drag != null ? e => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const x = ((e.clientX - r.left) / r.width) * view.W + view.x0, y = ((e.clientY - r.top) / r.height) * view.H + view.y0; onEdit?.(drag, +x2lon(x).toFixed(7), +y2lat(y).toFixed(7)) } : undefined}
        onPointerUp={() => setDrag(null)} onPointerLeave={() => setDrag(null)}
        onClick={onTap ? e => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const x = ((e.clientX - r.left) / r.width) * view.W + view.x0, y = ((e.clientY - r.top) / r.height) * view.H + view.y0; onTap(+x2lon(x).toFixed(7), +y2lat(y).toFixed(7)) } : undefined}>
        {view.tiles.map(t => <image key={`${t.x}-${t.y}-${src}`} href={S.url(Z, t.x, t.y)} x={t.left} y={t.top} width={T} height={T}
          onError={() => src < SOURCES.length - 1 && setSrc(src + 1)} />)}
        {edit && (() => { const pp = edit.map(c => [lon2x(c[0]) - view.x0, lat2y(c[1]) - view.y0]); return <>
          <polygon points={pp.map(q => q.join(',')).join(' ')} fill="rgba(251,191,36,0.22)" stroke="#FBBF24" strokeWidth={3} />
          {pp.map((q, k) => <circle key={k} cx={q[0]} cy={q[1]} r={drag === k ? 13 : 11} fill="#FBBF24" stroke="#fff" strokeWidth={3} style={{ cursor: 'grab' }} onPointerDown={e => { (e.target as Element).setPointerCapture?.(e.pointerId); setDrag(k) }} />)}</> })()}
        {!draft && !edit && <polygon points={view.pts} fill={grid ? 'none' : 'rgba(201,226,154,0.18)'} stroke="#E9F7C8" strokeWidth={3} />}
        {grid && grid.cells.map((c, k) => { const x1 = lon2x(c[0] - grid.half[0]) - view.x0, x2 = lon2x(c[0] + grid.half[0]) - view.x0, y1 = lat2y(c[1] + grid.half[1]) - view.y0, y2 = lat2y(c[1] - grid.half[1]) - view.y0
          return <rect key={k} x={x1} y={y1} width={Math.max(0.5, x2 - x1)} height={Math.max(0.5, y2 - y1)} fill={c[2] === 1 ? 'rgba(201,226,154,0.38)' : c[2] === 2 ? 'rgba(70,70,70,0.72)' : 'rgba(181,82,58,0.55)'} stroke="rgba(255,255,255,0.35)" strokeWidth={0.4} /> })}
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
export function SatellitePlace({ lat, lon, zoom: z0 = 14, label, square, caption, onTap }: { lat: number; lon: number; zoom?: number; label: string; square?: boolean; caption?: string; onTap?: (lat: number, lon: number) => void }) {
  const [src, setSrc] = useState(0)
  const [zoom, setZoom] = useState(z0)
  const W = square ? 320 : 600, H = square ? 320 : 300
  const n = 2 ** zoom
  const cx = ((lon + 180) / 360) * n * T
  const r = (lat * Math.PI) / 180
  const cy = ((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n * T
  const x0 = cx - W / 2, y0 = cy - H / 2
  const tiles: { x: number; y: number; left: number; top: number }[] = []
  for (let tx = Math.floor(x0 / T); tx <= Math.floor((x0 + W) / T); tx++)
    for (let ty = Math.floor(y0 / T); ty <= Math.floor((y0 + H) / T); ty++)
      tiles.push({ x: ((tx % n) + n) % n, y: ty, left: tx * T - x0, top: ty * T - y0 })
  const si = zoom >= 15 ? 1 : src, S = SOURCES[si]
  return (
    <div style={{ position: 'relative', width: '100%', overflow: 'hidden', borderRadius: 12, background: '#3E5A3A' }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block', cursor: onTap ? 'crosshair' : undefined }} aria-label={`Satellite view of ${label}`}
        onClick={onTap ? e => { const b = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const px = x0 + ((e.clientX - b.left) / b.width) * W, py = y0 + ((e.clientY - b.top) / b.height) * H
          const lo = (px / (n * T)) * 360 - 180, la = (Math.atan(Math.sinh(Math.PI * (1 - (2 * py) / (n * T)))) * 180) / Math.PI; onTap(+la.toFixed(6), +lo.toFixed(6)) } : undefined}>
        {tiles.map(t => <image key={`${t.x}-${t.y}-${t.left}-${si}`} href={S.url(zoom, t.x, t.y)} x={t.left} y={t.top} width={T} height={T}
          onError={() => si < SOURCES.length - 1 && setSrc(si + 1)} />)}
        <circle cx={W / 2} cy={H / 2} r={7} fill="none" stroke="#fff" strokeWidth={2.5} />
      </svg>
      <span style={{ position: 'absolute', left: 10, bottom: 8, fontSize: 11, fontWeight: 700, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,.7)' }}>{caption ?? `${label} today`}</span>
      <span className="zoomctl"><button aria-label="Zoom in" disabled={zoom >= 17} onClick={() => setZoom(zoom + 1)}>+</button><button aria-label="Zoom out" disabled={zoom <= 9} onClick={() => setZoom(zoom - 1)}>−</button></span>
      <span style={{ position: 'absolute', right: 8, top: 6, fontSize: 9, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,.7)', maxWidth: '70%', textAlign: 'right' }}>{S.name}</span>
    </div>
  )
}

/** Classify grid cells from the satellite picture: 1 = vegetation or soil, 0 = built or hard surface (roofs, roads, concrete). */
export async function classifyCells(cells: number[][], half: number[]): Promise<number[] | null> {
  if (!cells.length) return null
  const lons = cells.map(c => c[0]), lats = cells.map(c => c[1])
  const x0 = lon2x(Math.min(...lons) - half[0] * 2), x1 = lon2x(Math.max(...lons) + half[0] * 2)
  const y0 = lat2y(Math.max(...lats) + half[1] * 2), y1 = lat2y(Math.min(...lats) - half[1] * 2)
  const W = Math.ceil(x1 - x0), H = Math.ceil(y1 - y0)
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H
  const ctx = cv.getContext('2d', { willReadFrequently: true }); if (!ctx) return null
  const jobs: Promise<void>[] = []
  for (let tx = Math.floor(x0 / T); tx <= Math.floor(x1 / T); tx++)
    for (let ty = Math.floor(y0 / T); ty <= Math.floor(y1 / T); ty++)
      jobs.push(new Promise(res => { const im = new Image(); im.crossOrigin = 'anonymous'; im.onload = () => { ctx.drawImage(im, tx * T - x0, ty * T - y0); res() }; im.onerror = () => res(); im.src = SOURCES[1].url(Z, tx, ty) }))
  const ok = await Promise.race([Promise.all(jobs).then(() => true), new Promise<boolean>(r => setTimeout(() => r(false), 6000))])
  if (!ok) return null
  try {
    return cells.map(c => {
      const cx = lon2x(c[0]) - x0, cy = lat2y(c[1]) - y0, rx = Math.max(1, (lon2x(c[0] + half[0]) - lon2x(c[0])) * 0.8), ry = Math.max(1, (lat2y(c[1] - half[1]) - lat2y(c[1])) * 0.8)
      const d = ctx.getImageData(Math.max(0, Math.round(cx - rx)), Math.max(0, Math.round(cy - ry)), Math.max(1, Math.round(rx * 2)), Math.max(1, Math.round(ry * 2))).data
      let r = 0, g = 0, b = 0, n = 0
      for (let i = 0; i < d.length; i += 4) { r += d[i]; g += d[i + 1]; b += d[i + 2]; n++ }
      r /= n; g /= n; b /= n
      const mx = Math.max(r, g, b), mn = Math.min(r, g, b), sat = mx ? (mx - mn) / mx : 0, exg = 2 * g - r - b
      const built = (sat < 0.16 && mx > 95) || (sat < 0.1) || (b > g && b > r && mx > 110)
      return built && exg < 25 ? 0 : 1
    })
  } catch { return null }
}
