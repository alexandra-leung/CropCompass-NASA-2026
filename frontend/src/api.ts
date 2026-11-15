// API client: every call returns { data, source }.
// source = "live"   -> answered by the running backend just now
//        = "cached" -> backend unreachable; bundled real data captured from the backend earlier
// Nothing here invents numbers: when neither exists, data is null.
import fbFarms from './fallback/farms.json'
import fbProfiles from './fallback/farm_profiles.json'
import fbLocations from './fallback/locations.json'
import fbHistory from './fallback/history.json'
import fbHistAll from './fallback/history_all.json'
import fbThisYear from './fallback/thisyear.json'
import fbScenarios from './fallback/scenarios.json'
import fbTwin from './fallback/twin.json'
import fbStress from './fallback/stress.json'
import fbAnalyze from './fallback/analyze.json'
import fbCrops from './fallback/crops.json'
import fbGenerate from './fallback/generate.json'
import fbSuit from './fallback/suitability.json'
import fbPlans from './fallback/plans.json'
import fbM5Stress from './fallback/m5_stress.json'
import fbTwins from './fallback/m5_twins.json'

export type Source = 'live' | 'cached' | 'none'
export type Res<T> = { data: T | null; source: Source; error?: string }

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

async function call<T>(path: string, init?: RequestInit, timeoutMs = 30000, outer?: AbortSignal): Promise<T> {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(new Error(`no answer after ${Math.round(timeoutMs / 1000)} s`)), timeoutMs)
  outer?.addEventListener('abort', () => ctl.abort(new Error('cancelled')))
  try {
    const r = await fetch(BASE + path, { ...init, signal: ctl.signal, headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) } })
    if (!r.ok) {
      let detail = `${r.status}`
      try { const j = await r.json(); detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail ?? j) } catch { /* ignore */ }
      throw new Error(detail)
    }
    return r.status === 204 ? (null as T) : ((await r.json()) as T)
  } finally { clearTimeout(t) }
}

async function withFallback<T>(path: string, fallback: T | null, init?: RequestInit, timeoutMs?: number, signal?: AbortSignal): Promise<Res<T>> {
  try { return { data: await call<T>(path, init, timeoutMs, signal), source: 'live' } }
  catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    return { data: fallback, source: fallback ? 'cached' : 'none', error: /abort/i.test(msg) ? 'no answer in time' : msg }
  }
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

// ---------------- M3 farms
export const getFarms = () => withFallback<any>('/api/farms', fbFarms)
export const getLocations = () => withFallback<any>('/api/farms/locations', fbLocations)
export const getFarm = (id: string) => withFallback<any>(`/api/farms/${id}`, (fbProfiles as any)[id] ?? null, undefined, 60000)
export const createFarm = (body: any) => call<any>('/api/farms', post(body))
export const patchFarm = (id: string, body: any) => call<any>(`/api/farms/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
export const validateFarm = (body: any) => call<any>('/api/farms/validate', post(body))

// ---------------- M1 climate (cached fallback exists for pamplemousses-04 only)
export const getHistory = (loc: string, signal?: AbortSignal) => withFallback<any>(`/api/climate/history?location_id=${loc}`, (fbHistAll as any)[loc] ?? (loc === 'pamplemousses-04' ? fbHistory : null), undefined, 180000, signal)
export const getScenarios = (loc: string, signal?: AbortSignal) => withFallback<any>(`/api/climate/scenarios?location_id=${loc}`, loc === 'pamplemousses-04' ? fbScenarios : null, undefined, 240000, signal)

// ---------------- M2 agriculture
export const getCrops = async (): Promise<Res<any[]>> => {
  const r = await withFallback<any>('/api/agriculture/crops', null)
  const list = Array.isArray(r.data) ? r.data : r.data?.crops
  return list ? { data: list, source: 'live' } : { data: fbCrops as any[], source: 'cached', error: r.error }
}
export const generateRotations = (current: string[]) =>
  withFallback<any>('/api/agriculture/generate', (fbGenerate as any)[current.join('|')] ?? null, post({ current_rotation: current, max_alternatives: 3 }))
export const suitability = (crop: string, ph?: number | null) =>
  withFallback<any>(`/api/agriculture/suitability/${crop}${ph != null ? `?soil_ph=${ph}` : ''}`, (fbSuit as any)[crop] ?? null)

// ---------------- M5 resilience
export const climateTwin = (lat: number, lon: number, scenario: string, signal?: AbortSignal) =>
  withFallback<any>('/api/resilience/climate-twin', (fbTwins as any)[`${lat}|${lon}|${scenario}`] ?? fbTwin, post({ latitude: lat, longitude: lon, scenario, start_year: 2041, end_year: 2060, top_k: 3 }), 240000, signal)
export const stressTest = (lat: number, lon: number, scenario: string, rotation_request: any, budgetM3: number, key: string, signal?: AbortSignal) =>
  withFallback<any>('/api/resilience/stress-test', (fbM5Stress as any)[key] ?? null,
    post({ latitude: lat, longitude: lon, scenario, rotation_request, baseline_water_budget_m3: budgetM3, irrigation_reduction_fraction: 0.5 }), 240000, signal)
export const rescue = (stressOutput: any, signal?: AbortSignal) =>
  withFallback<any>('/api/resilience/rescue-mode', null, post({ stress_output: stressOutput }), 30000, signal)
export const suggestBoundary = (lat: number, lon: number) => call<any>(`/api/farms/boundary/suggest?lat=${lat}&lon=${lon}`, undefined, 40000)

// ---------------- M4 intelligence
export const analyze = (farm: any, scenario: string) =>
  withFallback<any>('/api/intelligence/analyze', fbAnalyze, post({ farm, scenario, year: 2050, max_alternatives: 3 }), 150000)
export const ask = (question: string, analysis: any) =>
  withFallback<any>('/api/intelligence/assistant', null, post({ question, analysis, use_llm: true }), 45000)

// Cached copies to show instantly while the live call runs (stale-while-revalidate).
export const cached = {
  history: (loc: string): Res<any> | null => ((fbHistAll as any)[loc] ? { data: (fbHistAll as any)[loc], source: 'cached' } : loc === 'pamplemousses-04' ? { data: fbHistory, source: 'cached' } : null),
  scenarios: (loc: string): Res<any> | null => (loc === 'pamplemousses-04' ? { data: fbScenarios, source: 'cached' } : null),
  twin: (lat?: number, lon?: number, scenario?: string): Res<any> => ({ data: (fbTwins as any)[`${lat}|${lon}|${scenario}`] ?? fbTwin, source: 'cached' }),
  stress: (): Res<any> => ({ data: fbStress, source: 'cached' }),
}

// ---------------- M2 ranked plans (engine) - key names the cached what-if variant
export const BALANCED = { water: 0.25, soil: 0.25, climate: 0.25, income: 0.25 }
export type PlanOpts = { temperature_change_c?: number; rainfall_change_pct?: number; water_budget_mm?: number; rotations?: string[][]; climate_monthly?: { temperature_c: number[]; precipitation_mm: number[] } }
export const plans = (farmId: string, opts: PlanOpts = {}, key = 'base', signal?: AbortSignal) =>
  withFallback<any>('/api/agriculture/plans', (fbPlans as any)[`${farmId}|${key}`] ?? null, post({ farm_id: farmId, priorities: BALANCED, ...opts }), 60000, signal)
export const putBoundary = (id: string, geometry: any) => call<any>(`/api/farms/${id}/boundary`, { method: 'PUT', body: JSON.stringify({ geometry, method: 'manual' }) })
export const landGrid = (id: string, buffer = 2) => call<any>(`/api/farms/${id}/land-efficiency`, post({ buffer_distance_m: buffer, cell_m: 5 }), 30000)
export const measure = (geometry: any) => call<any>('/api/farms/boundary/measure', post({ geometry }))
export const getThisYear = (loc: string, signal?: AbortSignal) => {
  const t = new Date(), y = t.getFullYear(), end = new Date(t.getTime() - 3 * 864e5).toISOString().slice(0, 10)
  return withFallback<any>(`/api/climate/history?location_id=${loc}&start=${y}-01-01&end=${end}`, (fbThisYear as any)[loc] ?? null, undefined, 120000, signal)
}
export const getHistoryLong = (loc: string, signal?: AbortSignal) =>
  withFallback<any>(`/api/climate/history?location_id=${loc}&start=2006-01-01&end=2025-12-31`, null, undefined, 240000, signal)

// ---------------- place search (OpenStreetMap Nominatim, called from the browser)
const NOM = 'https://nominatim.openstreetmap.org'
export const reverseGeo = async (lat: number, lon: number): Promise<{ place: string; country: string } | null> => {
  try {
    const r = await fetch(`${NOM}/reverse?format=jsonv2&zoom=10&lat=${lat}&lon=${lon}&accept-language=en`, { headers: { Accept: 'application/json' } })
    const j = await r.json(); const a = j.address ?? {}
    return { place: a.village || a.town || a.city || a.county || a.state || j.name || '', country: a.country || '' }
  } catch { return null }
}
export const searchPlace = async (q: string): Promise<{ name: string; country: string; lat: number; lon: number }[]> => {
  const r = await fetch(`${NOM}/search?format=jsonv2&addressdetails=1&limit=6&accept-language=en&q=${encodeURIComponent(q)}`, { headers: { Accept: 'application/json' } })
  const j = await r.json()
  return (j as any[]).map(x => ({ name: x.display_name.split(',').slice(0, 2).join(','), country: x.address?.country ?? '', lat: +x.lat, lon: +x.lon }))
}

// nearest mapped farmland (OpenStreetMap) to a point, so a twin close-up shows fields, not the town centre
const farmCache = new Map<string, { lat: number; lon: number } | null>()
export const nearestFarmland = async (lat: number, lon: number): Promise<{ lat: number; lon: number } | null> => {
  const key = `${lat.toFixed(3)},${lon.toFixed(3)}`
  if (farmCache.has(key)) return farmCache.get(key)!
  try {
    const q = `[out:json][timeout:20];way(around:15000,${lat},${lon})[landuse~"^(farmland|orchard|meadow|plantation)$"];out center 40;`
    let els: any[] | null = null
    for (const host of ['https://overpass-api.de', 'https://overpass.kumi.systems', 'https://overpass.private.coffee']) {
      try { const r = await fetch(`${host}/api/interpreter?data=${encodeURIComponent(q)}`, { signal: AbortSignal.timeout(9000) }); if (r.ok) { els = (await r.json()).elements ?? []; break } } catch { /* next mirror */ }
    }
    if (!els) return null
    let best: { lat: number; lon: number } | null = null, bd = Infinity
    for (const e of els) { const c = e.center; if (!c) continue; const d = (c.lat - lat) ** 2 + ((c.lon - lon) * Math.cos(lat * Math.PI / 180)) ** 2; if (d < bd) { bd = d; best = { lat: c.lat, lon: c.lon } } }
    farmCache.set(key, best); return best
  } catch { return null }
}

// real photos of each crop growth stage (Wikimedia Commons, open licences), looked up in the browser
const STAGE_Q: Record<string, string[]> = {
  maize: ['Zea mays seeds', 'maize seedling', 'maize plants young field', 'maize tassel', 'maize ear corn cob husk'],
  tomato: ['tomato seeds', 'tomato seedlings', 'tomato plant young', 'tomato flowers', 'tomatoes ripening on vine'],
  onion: ['onion seeds Allium cepa', 'onion seedlings', 'onion field green leaves', 'Allium cepa flower', 'onion harvest bulbs'],
  cabbage: ['cabbage seeds', 'cabbage seedlings', 'young cabbage plants field', 'Brassica oleracea flowers', 'cabbage heads field'],
  cowpea: ['cowpea seeds Vigna unguiculata', 'cowpea seedling', 'Vigna unguiculata plant', 'Vigna unguiculata flower', 'cowpea pods'],
  groundnut: ['peanut seeds Arachis hypogaea', 'peanut seedling', 'Arachis hypogaea plant', 'Arachis hypogaea flower', 'peanuts harvested plant pods'],
  sweet_potato: ['sweet potato slips', 'sweet potato sprouting', 'Ipomoea batatas leaves field', 'Ipomoea batatas flower', 'sweet potatoes harvest'],
}
export type Photo = { url: string; title: string; credit: string; page: string }
const photoCache = new Map<string, Photo | null>()
export const stagePhoto = async (crop: string, stage: number): Promise<Photo | null> => {
  const q = STAGE_Q[crop]?.[stage]; if (!q) return null
  const key = `${crop}|${stage}`
  if (photoCache.has(key)) return photoCache.get(key)!
  try {
    const u = `https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrsearch=${encodeURIComponent(q + ' filetype:bitmap')}&gsrnamespace=6&gsrlimit=1&prop=imageinfo&iiprop=url|extmetadata&iiurlwidth=480&format=json&origin=*`
    const j = await (await fetch(u, { signal: AbortSignal.timeout(8000) })).json()
    const pg: any = Object.values(j.query?.pages ?? {})[0]
    const ii = pg?.imageinfo?.[0]
    const ph = ii ? { url: ii.thumburl ?? ii.url, title: pg.title.replace(/^File:/, ''), page: ii.descriptionurl ?? 'https://commons.wikimedia.org',
      credit: `${(ii.extmetadata?.Artist?.value ?? '').replace(/<[^>]+>/g, '').trim().slice(0, 40) || 'Wikimedia Commons'} · ${ii.extmetadata?.LicenseShortName?.value ?? 'open licence'}` } : null
    photoCache.set(key, ph); return ph
  } catch { return null }
}
