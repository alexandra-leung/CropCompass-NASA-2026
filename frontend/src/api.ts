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

export type Source = 'live' | 'cached' | 'none'
export type Res<T> = { data: T | null; source: Source; error?: string }

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

async function call<T>(path: string, init?: RequestInit, timeoutMs = 20000): Promise<T> {
  const ctl = new AbortController()
  const t = setTimeout(() => ctl.abort(), timeoutMs)
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

async function withFallback<T>(path: string, fallback: T | null, init?: RequestInit, timeoutMs?: number): Promise<Res<T>> {
  try { return { data: await call<T>(path, init, timeoutMs), source: 'live' } }
  catch (e) { return { data: fallback, source: fallback ? 'cached' : 'none', error: String((e as Error).message || e) } }
}

const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

// ---------------- M3 farms
export const getFarms = () => withFallback<any>('/api/farms', fbFarms)
export const getLocations = () => withFallback<any>('/api/farms/locations', fbLocations)
export const getFarm = (id: string) => withFallback<any>(`/api/farms/${id}`, (fbProfiles as any)[id] ?? null)
export const createFarm = (body: any) => call<any>('/api/farms', post(body))
export const patchFarm = (id: string, body: any) => call<any>(`/api/farms/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
export const validateFarm = (body: any) => call<any>('/api/farms/validate', post(body))

// ---------------- M1 climate (cached fallback exists for pamplemousses-04 only)
export const getHistory = (loc: string) => withFallback<any>(`/api/climate/history?location_id=${loc}`, loc === 'pamplemousses-04' ? fbHistory : null, undefined, 60000)
export const getScenarios = (loc: string) => withFallback<any>(`/api/climate/scenarios?location_id=${loc}`, loc === 'pamplemousses-04' ? fbScenarios : null, undefined, 120000)

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
export const climateTwin = (lat: number, lon: number, scenario: string) =>
  withFallback<any>('/api/resilience/climate-twin', fbTwin, post({ latitude: lat, longitude: lon, scenario, start_year: 2041, end_year: 2060, top_k: 3 }), 120000)
export const stressTest = (lat: number, lon: number, scenario: string, rotations: { id: string; crops: string[] }[], ph: number | null, budgetM3: number) =>
  withFallback<any>('/api/resilience/stress-test', fbStress,
    post({ latitude: lat, longitude: lon, scenario, rotation_request: { soil_ph: ph, rotations }, baseline_water_budget_m3: budgetM3, irrigation_reduction_fraction: 0.5 }), 120000)

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
