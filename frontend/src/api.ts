// API client: every call returns { data, source }.
// source = "live"   -> answered by the running backend just now
//        = "cached" -> backend unreachable; bundled real data captured from the backend earlier
// Nothing here invents numbers: when neither exists, data is null.
import fbFarms from './fallback/farms.json'
import fbProfiles from './fallback/farm_profiles.json'
import fbLocations from './fallback/locations.json'
import fbHistory from './fallback/history.json'
import fbScenarios from './fallback/scenarios.json'
import fbTwin from './fallback/twin.json'
import fbStress from './fallback/stress.json'
import fbAnalyze from './fallback/analyze.json'
import fbCrops from './fallback/crops.json'
import fbGenerate from './fallback/generate.json'
import fbSuit from './fallback/suitability.json'
import fbPlans from './fallback/plans.json'

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
export const getHistory = (loc: string, signal?: AbortSignal) => withFallback<any>(`/api/climate/history?location_id=${loc}`, loc === 'pamplemousses-04' ? fbHistory : null, undefined, 180000, signal)
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
  withFallback<any>('/api/resilience/climate-twin', fbTwin, post({ latitude: lat, longitude: lon, scenario, start_year: 2041, end_year: 2060, top_k: 3 }), 240000, signal)
export const stressTest = (lat: number, lon: number, scenario: string, rotations: { id: string; crops: string[] }[], ph: number | null, budgetM3: number, signal?: AbortSignal) =>
  withFallback<any>('/api/resilience/stress-test', fbStress,
    post({ latitude: lat, longitude: lon, scenario, rotation_request: { soil_ph: ph, rotations }, baseline_water_budget_m3: budgetM3, irrigation_reduction_fraction: 0.5 }), 240000, signal)

// ---------------- M4 intelligence
export const analyze = (farm: any, scenario: string) =>
  withFallback<any>('/api/intelligence/analyze', fbAnalyze, post({ farm, scenario, year: 2050, max_alternatives: 3 }), 150000)
export const ask = (question: string, analysis: any) =>
  withFallback<any>('/api/intelligence/assistant', null, post({ question, analysis, use_llm: false }), 30000)

// Cached copies to show instantly while the live call runs (stale-while-revalidate).
export const cached = {
  history: (loc: string): Res<any> | null => (loc === 'pamplemousses-04' ? { data: fbHistory, source: 'cached' } : null),
  scenarios: (loc: string): Res<any> | null => (loc === 'pamplemousses-04' ? { data: fbScenarios, source: 'cached' } : null),
  twin: (): Res<any> => ({ data: fbTwin, source: 'cached' }),
  stress: (): Res<any> => ({ data: fbStress, source: 'cached' }),
}

// ---------------- M2 ranked plans (engine) - key names the cached what-if variant
export type PlanOpts = { temperature_change_c?: number; rainfall_change_pct?: number; water_budget_mm?: number; rotations?: string[][] }
export const plans = (farmId: string, opts: PlanOpts = {}, key = 'base', signal?: AbortSignal) =>
  withFallback<any>('/api/agriculture/plans', (fbPlans as any)[`${farmId}|${key}`] ?? null, post({ farm_id: farmId, ...opts }), 60000, signal)
export const putBoundary = (id: string, geometry: any) => call<any>(`/api/farms/${id}/boundary`, { method: 'PUT', body: JSON.stringify({ geometry, method: 'manual' }) })
export const measure = (geometry: any) => call<any>('/api/farms/boundary/measure', post({ geometry }))
export const getHistoryLong = (loc: string, signal?: AbortSignal) =>
  withFallback<any>(`/api/climate/history?location_id=${loc}&start=2006-01-01&end=2025-12-31`, null, undefined, 240000, signal)
