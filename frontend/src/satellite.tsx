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

export function SatelliteField({ ring, label }: { ring: number[][]; label: string }) {
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
    return { W, H, tiles, pts }
  }, [ring])
  const S = SOURCES[src]
  return (
    <div style={{ position: 'relative', width: '100%', overflow: 'hidden', borderRadius: 14, background: '#3E5A3A' }}>
      <svg viewBox={`0 0 ${view.W} ${view.H}`} width="100%" style={{ display: 'block' }} aria-label="Satellite view of the field">
        {view.tiles.map(t => <image key={`${t.x}-${t.y}-${src}`} href={S.url(Z, t.x, t.y)} x={t.left} y={t.top} width={T} height={T}
          onError={() => src < SOURCES.length - 1 && setSrc(src + 1)} />)}
        <polygon points={view.pts} fill="rgba(201,226,154,0.18)" stroke="#E9F7C8" strokeWidth={3} />
      </svg>
      <span style={{ position: 'absolute', left: 10, bottom: 8, fontSize: 10.5, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,.6)' }}>{label}</span>
      <span style={{ position: 'absolute', right: 8, top: 6, fontSize: 9, color: '#fff', textShadow: '0 1px 2px rgba(0,0,0,.7)', maxWidth: '70%', textAlign: 'right' }}>{S.name}</span>
    </div>
  )
}
