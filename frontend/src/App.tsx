import { Fragment, useEffect, useRef, useState } from 'react'
import * as api from './api'
import type { Source } from './api'
import { C, FarmPickCtx, Hero, I, Icon, Kpi, LineChart, SourceTag, Spinner, Tag } from './ui'
import { CropPic, STAGES, StagePic } from './crops'
import { SatelliteField, SatellitePlace } from './satellite'

type Tab = 'home' | 'fields' | 'plans' | 'water' | 'future'
type Sheet = null | { kind: 'field' } | { kind: 'add' } | { kind: 'passport' } | { kind: 'settings' }

const USER = 'Sanjana'
const CROP_NAMES: Record<string, string> = { maize: 'Maize', tomato: 'Tomato', onion: 'Onion', cabbage: 'Cabbage', cowpea: 'Cowpea', groundnut: 'Groundnut', sweet_potato: 'Sweet potato' }
const crop = (id: string) => CROP_NAMES[id] ?? id
// Repair text that was decoded with the wrong character set upstream (e.g. "RÃ©union" -> "Réunion").
const fixText = (t?: string) => { if (!t || !/[ÃÂ]/.test(t)) return t ?? ''; try { return decodeURIComponent(escape(t)) } catch { return t } }
const nice = (n?: string) => (n ?? '').replace(/ Field \d+$/, '')
const rot = (r?: string[] | null) => (r && r.length ? r.map(crop).join(' → ') : 'Not entered')
const TEXTURES: [string, string][] = [['sandy_loam', 'Sandy loam'], ['loam', 'Loam'], ['clay_loam', 'Clay loam'], ['clay', 'Clay'], ['unknown', "Don't know"]]
const WATER: [string, string][] = [['rain_only', 'Rain only'], ['tank', 'Tank or pond'], ['borehole', 'Borehole'], ['irrigation_scheme', 'Irrigation scheme']]
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const MONTH_FULL = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const MONTH_L = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
const srcKey = (s?: string) => (s === 'farmer' ? 'entered' : s === 'map_estimate' ? 'map' : 'missing')

export default function App() {
  const [tab, setTab] = useState<Tab>('home')
  const [sheet, setSheet] = useState<Sheet>(null)
  const [farms, setFarms] = useState<api.Res<any>>({ data: null, source: 'none' })
  const [farmId, setFarmId] = useState('pamplemousses-04')
  const [farm, setFarm] = useState<api.Res<any>>({ data: null, source: 'none' })
  const [history, setHistory] = useState<api.Res<any> | null>(null)
  const [scen, setScen] = useState<api.Res<any> | null>(null)
  const [planRes, setPlanRes] = useState<api.Res<any> | null>(null)
  const [analysis, setAnalysis] = useState<api.Res<any> | null>(null)
  const [analysing, setAnalysing] = useState(false)
  const scenario: string = 'ssp370'
  const [chat, setChat] = useState(false)

  const loadFarms = async (select?: string) => { const r = await api.getFarms(); setFarms(r); if (select) setFarmId(select) }
  const loadFarm = async (id = farmId) => setFarm(await api.getFarm(id))
  useEffect(() => { loadFarms() }, [])
  const warmed = useRef(false)
  useEffect(() => {
    const list: any[] = farms.data?.farms ?? []
    if (warmed.current || farms.source !== 'live' || !list.length) return
    warmed.current = true
    ;(async () => {  // warm the backend cache so switching fields is quick
      for (const f of list) await api.getHistory(f.location_id)
      for (const f of list) await api.getScenarios(f.location_id)
    })()
  }, [farms])
  useEffect(() => {
    setFarm({ data: null, source: 'none' }); setHistory(null); setScen(null); setPlanRes(null); setAnalysis(null)
    loadFarm(farmId)
  }, [farmId])
  const p = farm.data
  useEffect(() => {
    if (!p) return
    const ctl = new AbortController(), live = () => !ctl.signal.aborted
    setHistory(api.cached.history(p.location_id)); setScen(api.cached.scenarios(p.location_id))
    api.getHistory(p.location_id, ctl.signal).then(r => live() && setHistory(prev => (r.source === 'live' || !prev ? r : prev)))
    api.getScenarios(p.location_id, ctl.signal).then(r => live() && setScen(prev => (r.source === 'live' || !prev ? r : prev)))
    return () => ctl.abort()
  }, [p?.farm_id, p?.location_id, (p?.current_rotation || []).join()])

  const planKey = p ? [p.farm_id, p.irrigation?.budget_mm_per_season, JSON.stringify(p.prices_rs_per_kg ?? null), JSON.stringify(p.costs_rs_per_ha ?? null), (p.current_rotation || []).join(), p.soil?.ph].join('|') : ''
  const loadPlans = () => { if (!p?.current_rotation?.length) return; setPlanRes(null); api.plans(p.farm_id).then(setPlanRes) }
  useEffect(() => { loadPlans() }, [planKey])
  const savePrices = async (pr: any, co: any) => { try { setFarm({ data: await api.patchFarm(p.farm_id, { prices_rs_per_kg: pr, costs_rs_per_ha: co }), source: 'live' }); return true } catch { return false } }

  const runAnalysis = async () => {
    if (!p || analysing) return
    setAnalysing(true)
    const ctx = { farm_id: p.farm_id, location_id: p.location_id, soil_ph: p.soil?.ph ?? null, field_area_ha: p.field_area_ha, irrigation_budget_m3: p.irrigation_budget_m3, current_rotation: p.current_rotation, source: 'M3' }
    setAnalysis(await api.analyze(ctx, scenario))
    setAnalysing(false)
  }
  const needAnalysis = () => { if (!analysis && !analysing) runAnalysis() }

  const farmList: any[] = farms.data?.farms ?? []
  const loc = farmList.find(f => f.farm_id === farmId)

  return (
    <FarmPickCtx.Provider value={farmList.length ? { farms: farmList, active: farmId, set: setFarmId } : null}>
    <div className="phone">
      <div className="top">
        <span className="logo"><Icon d={I.leaf} c="#fff" s={20} /></span>
        <span className="brand"><span style={{ color: C.deep }}>crop</span><span style={{ color: C.teal }}>compass</span></span>
        <button className="iconbtn" aria-label="Settings" onClick={() => setSheet({ kind: 'settings' })}><Icon d="M12 15a3 3 0 100-6 3 3 0 000 6z M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z" /></button>
        <button className="iconbtn" aria-label="Evidence passport" onClick={() => { setSheet({ kind: 'passport' }); needAnalysis() }}><Icon d={I.doc} />{(p?.validation?.missing?.length ?? 0) > 0 && <span className="dotbadge" />}</button>
      </div>

      <main>
        {tab === 'home' && <Home p={p} loc={loc} farms={farmList} history={history} openField={() => setSheet({ kind: 'field' })} farmsSrc={farms.source} goFields={() => setTab('fields')} />}
        {tab === 'fields' && <Fields farms={farmList} src={farms.source} open={(id: string) => { setFarmId(id); setSheet({ kind: 'field' }) }} add={() => setSheet({ kind: 'add' })} plans={(id: string) => { setFarmId(id); setTab('plans') }} />}
        {tab === 'plans' && <Plans p={p} planRes={planRes} refresh={loadPlans} />}
        {tab === 'water' && <Water p={p} planRes={planRes} onSaved={(np: any) => setFarm({ data: np, source: 'live' })} />}
        {tab === 'future' && <Future p={p} loc={loc} scen={scen} scenario={scenario} />}
      </main>

      {!sheet && !chat && <button className="fab" aria-label="Ask CropCompass" onClick={() => { setChat(true); needAnalysis() }}><Icon d={I.chat} c="#fff" s={24} /></button>}
      {chat && <Ask close={() => setChat(false)} analysis={analysis} analysing={analysing} p={p} planRes={planRes} />}
      <nav className="tabbar" aria-label="Sections">
        {([['home', 'Home', I.home], ['fields', 'Fields', I.map], ['plans', 'Plans', I.plans], ['water', 'Water', I.drop], ['future', 'Future', I.clock]] as const).map(([k, l, d]) => (
          <button key={k} className={tab === k ? 'on' : ''} aria-current={tab === k ? 'page' : undefined} onClick={() => setTab(k)}>
            <span className="p"><Icon d={d} c={tab === k ? C.deep : '#94A3B8'} s={20} /></span>{l}
          </button>
        ))}
      </nav>

      {sheet && (
        <div className="scrim" onClick={e => { if (e.target === e.currentTarget) setSheet(null) }}>
          <div className="sheet">
            {sheet.kind === 'field' && <FieldSheet p={p} src={farm.source} close={() => setSheet(null)} onSaved={(np: any) => { setFarm({ data: np, source: 'live' }); loadFarms() }} passport={() => { setSheet({ kind: 'passport' }); needAnalysis() }} />}
            {sheet.kind === 'add' && <AddField close={() => setSheet(null)} created={(id: string) => { setSheet(null); loadFarms(id); setTab('plans') }} />}
            {sheet.kind === 'settings' && <Settings close={() => setSheet(null)} p={p} planRes={planRes} onPrices={savePrices} farms={farmList} farmId={farmId} setFarmId={setFarmId} />}
            {sheet.kind === 'passport' && <Passport close={() => setSheet(null)} analysis={analysis} analysing={analysing} p={p} rerun={runAnalysis} planRes={planRes} />}
          </div>
        </div>
      )}
    </div>
    </FarmPickCtx.Provider>
  )
}

/* ------------------------------------------------------------------ HOME */
function Home({ p, loc, farms, history, openField, farmsSrc, goFields }: any) {
  const [long, setLong] = useState<api.Res<any> | null>(null), [loadingLong, setLoadingLong] = useState(false)
  useEffect(() => { setLong(null) }, [loc?.farm_id])
  const [yr, setYr] = useState<api.Res<any> | null>(null)
  useEffect(() => { if (!p?.location_id) return; const c = new AbortController(); setYr(null); api.getThisYear(p.location_id, c.signal).then(r => !c.signal.aborted && setYr(r)); return () => c.abort() }, [p?.location_id])
  const h = long?.data ?? history?.data
  const ts: any[] = h?.timeseries ?? []
  const m = h?.metrics
  const hour = new Date().getHours()
  const greet = hour < 12 ? 'Good morning,' : hour < 18 ? 'Good afternoon,' : 'Good evening,'
  const date = new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'short' }).toUpperCase()
  const [sel, setSel] = useState<number | null>(null)
  const pick = sel ?? (ts.length ? ts.length - 1 : null)
  const shift = m?.rainfallShift as number | undefined
  const title = shift == null ? 'Your farm,\nat a glance.' : shift < -5 ? 'Rain is falling\nbelow normal.' : shift > 5 ? 'Rain is above\nnormal.' : 'Rain is close\nto normal.'
  const sub = m ? `NASA POWER, ${ts[0]?.label}–${ts[ts.length - 1]?.label}: rain ${shift! > 0 ? '+' : ''}${shift}%, longest dry spell ${m.longestDrySpell} days, temperature trend ${m.temperatureTrend > 0 ? '+' : ''}${m.temperatureTrend} °C a year.` : 'Loading climate history for this field…'
  const missing: any[] = p?.validation?.missing ?? []
  return (<>
    <div className="between" style={{ alignItems: 'flex-end' }}>
      <div><div className="eb">{date}</div><h1 className="h1" style={{ marginTop: 6 }}>{greet} <span>{USER}.</span></h1></div>
    </div>
    <Hero pick eyebrow={`Farm status · ${nice(loc?.name)}`} title={title} sub={sub} />
    <div className="kpis">
      <Kpi onClick={goFields} v={String(farms.length || '…')} l="Fields" />
      <Kpi onClick={goFields} v={p?.irrigation?.budget_mm_per_season != null ? String(Math.round(p.irrigation.budget_mm_per_season)) : '…'} unit="mm" l={`Water · ${nice(p?.name)}`} />
      <Kpi onClick={goFields} v={m ? `${m.dataCompleteness}` : history && !h ? '–' : '…'} unit={m ? '%' : undefined} l="Climate data" />
    </div>
    <ThisYear yr={yr} hist={history?.data} name={nice(p?.name)} />
    <section className="card">
      <div className="between"><div><div className="eb">Climate history</div><div className="ct">Rain and heat, by year</div></div></div>
      {!history && <Spinner text={`Loading climate history for ${nice(loc?.name)}…`} />}
      {history && !h && <div className="err">Climate history did not load for {nice(loc?.name)}. Tap Home again to retry.</div>}
      {ts.length > 0 && <>
        <LineChart labels={ts.map(t => t.label)} unit="mm" series={[{ name: 'Rain', color: C.water, values: ts.map(t => t.rainfallMm) }]} selected={pick ?? undefined} onPick={setSel} />
        {pick != null && <div className="list">
          <div><span className="dot" style={{ background: C.water }} /><span style={{ flex: 1 }}>Rain in {ts[pick].label}</span><b>{Math.round(ts[pick].rainfallMm)} mm</b></div>
          <div><span className="dot" style={{ background: C.red }} /><span style={{ flex: 1 }}>Average temperature</span><b>{ts[pick].temperatureC} °C</b></div>
          <div><span className="dot" style={{ background: C.gold }} /><span style={{ flex: 1 }}>Longest dry spell</span><b>{ts[pick].drySpellDays} days</b></div>
        </div>}
        <span className="faint">{h.provenance?.gridResolution ? `Grid ${h.provenance.gridResolution} · regional, not a field sensor.` : 'Regional grid, not a field sensor.'}</span>
        {!long?.data && <button className="chip" disabled={loadingLong} onClick={async () => { setLoadingLong(true); const r = await api.getHistoryLong(p.location_id); setLong(r); setLoadingLong(false) }}>{loadingLong ? 'Fetching 20 years from NASA POWER…' : 'Show 20 years (2006–2025)'}</button>}
        {long && !long.data && <span className="faint">20-year history not available right now ({long.error}).</span>}
      </>}
    </section>
    {missing.length > 0 && <section className="card">
      <div className="between"><div><div className="eb">Complete your farm</div><div className="ct">{missing.length} thing{missing.length > 1 ? 's' : ''} we don't know yet</div></div><Tag k={farmsSrc} /></div>
      <div className="list">{missing.slice(0, 4).map((x: any) => <div key={x.field}><span className="dot" style={{ background: C.red }} /><span style={{ flex: 1 }}>{x.prompt}</span></div>)}</div>
      <button className="btn light" onClick={openField}>Open field</button>
    </section>}
  </>)
}

/* ------------------------------------------------------------------ FIELDS */
const SEASON_NAME: Record<string, string> = { DJF: 'Dec–Feb', MAM: 'Mar–May', JJA: 'Jun–Aug', SON: 'Sep–Nov' }
function ThisYear({ yr, hist, name }: any) {
  const year = new Date().getFullYear()
  const [mode, setMode] = useState<'rain' | 'temp'>('rain')
  const cur: any[] = yr?.data?.seasonal ?? [], base: any[] = hist?.seasonal ?? []
  if (!yr) return <section className="card"><div className="eb">{year} so far</div><Spinner text={`Fetching ${year} from NASA POWER…`} /></section>
  if (!cur.length || !base.length) return null
  const rows = ['DJF', 'MAM', 'JJA', 'SON'].map(code => {
    const c = cur.find(x => x.period.endsWith(code)), b = base.filter(x => x.period.endsWith(code) && x.completenessStatus !== 'incomplete')
    if (!c || !b.length) return null
    const nr = b.reduce((a, x) => a + x.rainfallMm, 0) / b.length, nt = b.reduce((a, x) => a + x.temperatureC, 0) / b.length
    return { code, rain: c.rainfallMm, nr, dr: nr ? Math.round((c.rainfallMm / nr - 1) * 100) : 0, t: c.temperatureC, nt, dt: +(c.temperatureC - nt).toFixed(1), partial: c.completenessStatus === 'incomplete' }
  }).filter(Boolean) as any[]
  const full = rows.filter(r => !r.partial)
  const avgR = full.length ? Math.round(full.reduce((a, r) => a + r.dr, 0) / full.length) : null
  const avgT = full.length ? +(full.reduce((a, r) => a + r.dt, 0) / full.length).toFixed(1) : null
  const rain = mode === 'rain'
  const v = (r: any) => (rain ? r.rain : r.t), nv = (r: any) => (rain ? r.nr : r.nt)
  const lo = rain ? 0 : Math.min(...rows.flatMap(r => [r.t, r.nt])) - 2, hi = Math.max(...rows.flatMap(r => [v(r), nv(r)]), 1)
  const h = (x: number) => `${((x - lo) / (hi - lo)) * 90}px`
  const title = rain
    ? (avgR == null ? 'Rain this year vs normal' : avgR < -10 ? `${year} is drier than normal` : avgR > 10 ? `${year} is wetter than normal` : `${year} rain is close to normal`)
    : (avgT == null ? 'Heat this year vs normal' : avgT > 0.3 ? `${year} is warmer than normal` : avgT < -0.3 ? `${year} is cooler than normal` : `${year} heat is close to normal`)
  const summary = rain
    ? (avgR == null ? '' : `Rain in the finished seasons is ${Math.abs(avgR)}% ${avgR < 0 ? 'below' : 'above'} the 2021–2025 average.${avgR < -10 ? ' Plan for more watering and keep soil covered.' : ''}`)
    : (avgT == null ? '' : `The finished seasons were ${avgT > 0 ? '+' : ''}${avgT} °C compared with 2021–2025.${avgT > 0.3 ? ' Crops will need more water than usual.' : ''}`)
  const col = rain ? C.water : '#C0622E'
  return <section className="card">
    <div className="between"><div><div className="eb">{year} so far · {name}</div><div className="ct">{title}</div></div>
      <div className="toggle" role="tablist"><button className={rain ? 'on' : ''} onClick={() => setMode('rain')}>Rain</button><button className={!rain ? 'on' : ''} onClick={() => setMode('temp')}>Heat</button></div></div>
    {summary && <span className="muted">{summary}</span>}
    <div className="yrbars">{rows.map(r => {
      const d = rain ? r.dr : r.dt
      return <div key={r.code}>
        <div className="yb"><i style={{ height: h(nv(r)), background: '#CBD5D1' }} title={`Normal ${rain ? Math.round(r.nr) + ' mm' : r.nt.toFixed(1) + ' °C'}`} /><i style={{ height: h(v(r)), background: col, opacity: r.partial ? 0.5 : 1 }} title={`${year}: ${rain ? Math.round(r.rain) + ' mm' : r.t.toFixed(1) + ' °C'}`} /></div>
        <b style={{ color: rain ? (d < -10 ? C.red : d > 10 ? C.water : C.ink) : d > 0.3 ? C.red : d < -0.3 ? C.water : C.ink }}>{r.partial ? 'so far' : rain ? `${d > 0 ? '+' : ''}${d}%` : `${d > 0 ? '+' : ''}${d} °C`}</b>
        <span className="faint">{SEASON_NAME[r.code]}</span>
      </div>
    })}</div>
    <div className="row" style={{ gap: 14, fontSize: 11.5, color: C.mut }}><span className="row" style={{ gap: 5 }}><span style={{ width: 12, height: 10, background: '#CBD5D1', borderRadius: 2 }} />Normal 2021–2025</span><span className="row" style={{ gap: 5 }}><span style={{ width: 12, height: 10, background: col, borderRadius: 2 }} />{year}</span></div>
    <span className="faint">Plans are built on 2021–2025. NASA POWER updates within days, so {year} is checked live as a test year the model never saw.</span>
  </section>
}

function Fields({ farms, src, open, add, plans }: any) {
  return (<>
    <div className="eb">Your land, at a glance</div>
    <div className="row"><span className="h1">Fields</span>
      <span style={{ fontSize: 12, fontWeight: 700, color: C.teal, background: '#E9F1EE', padding: '3px 8px', borderRadius: 8 }}>{String(farms.length).padStart(2, '0')}</span>
      <button className="btn" style={{ marginLeft: 'auto', minHeight: 42, padding: '0 14px', fontSize: 13.5 }} onClick={add}>+ Add field</button></div>
    <div className="between"><span className="muted">Farmer inputs and field outlines, from M3.</span><SourceTag s={src} /></div>
    {farms.map((f: any) => {
      const bad = f.missing_count > 0
      const col = bad ? C.red : C.teal
      return (
        <div key={f.farm_id} className="fcard">
          <span className="bar" style={{ background: col }} />
          <span className="in"><button className="fopen" onClick={() => open(f.farm_id)}>
            <span className="between"><span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span className="faint" style={{ fontWeight: 700 }}>{rot(f.current_rotation)} · {f.district}</span><span style={{ fontSize: 17 }}>{nice(f.name)}</span></span><span style={{ color: '#A9BAB5', fontSize: 18 }}>›</span></span>
            <span style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
              <span className="stat"><span>Area</span><b>{f.field_area_ha ?? '–'} ha</b></span>
              <span className="stat"><span>Water</span><b>{f.irrigation_budget_mm ?? '–'} mm</b></span>
              <span className="stat"><span>Soil</span><b style={{ fontSize: 12.5 }}>{f.soil_texture}</b></span>
            </span>
            <span className="row" style={{ gap: 6, fontSize: 11.5 }}><span className="dot" style={{ background: col, marginTop: 0 }} /><b style={{ color: col }}>{bad ? `Needs ${f.missing_count} answer${f.missing_count > 1 ? 's' : ''}` : 'Complete'}</b>{f.demo && <span className="faint" style={{ marginLeft: 'auto' }}>Demo farm</span>}</span>
          </button>
          <button className="btn planbtn" onClick={() => plans(f.farm_id)}>See plans for {nice(f.name)} ›</button>
          </span>
        </div>)
    })}
  </>)
}

function FieldSheet({ p, src, close, onSaved, passport }: any) {
  const [err, setErr] = useState('')
  const [draw, setDraw] = useState<number[][] | null>(null)
  const [area, setArea] = useState<number | null>(null)
  const [auto, setAuto] = useState<string>('')
  const findAuto = async () => {
    const ring: number[][] = p.boundary?.geometry?.coordinates?.[0] ?? []
    if (!ring.length) return
    const pts = ring.slice(0, -1), lon = pts.reduce((a, c) => a + c[0], 0) / pts.length, lat = pts.reduce((a, c) => a + c[1], 0) / pts.length
    setAuto('Looking for your field in OpenStreetMap…')
    try {
      const r = await api.suggestBoundary(+lat.toFixed(6), +lon.toFixed(6))
      if (r.status === 'suggested') { setDraw(r.geometry.coordinates[0].slice(0, -1)); setAuto(`Found a mapped ${r.landuse} outline (${r.area_ha} ha) from OpenStreetMap. Check it, adjust or save.`) }
      else setAuto(`${r.reason} Tap the corners instead.`)
      if (r.status !== 'suggested') setDraw([])
    } catch { setAuto('Automatic outline unavailable (backend offline). Tap the corners instead.'); setDraw([]) }
  }
  const saveOutline = async () => {
    if (!draw || draw.length < 3) return
    const geometry = { type: 'Polygon', coordinates: [[...draw, draw[0]]] }
    setErr('')
    try { await api.measure(geometry); onSaved(await api.putBoundary(p.farm_id, geometry)); setDraw(null); setArea(null) }
    catch (e) { setErr(`Could not save the outline: ${(e as Error).message}`) }
  }
  useEffect(() => {
    if (!draw || draw.length < 3) { setArea(null); return }
    api.measure({ type: 'Polygon', coordinates: [[...draw, draw[0]]] }).then(r => setArea(r.area_ha)).catch(() => setArea(null))
  }, [draw])
  const [ph, setPh] = useState<string>(p?.soil?.ph != null ? String(p.soil.ph) : '')
  const save = async (body: any) => {
    setErr('')
    try { onSaved(await api.patchFarm(p.farm_id, body)) } catch (e) { setErr(`Could not save: ${(e as Error).message}. Is the backend running?`) }
  }
  if (!p) return <SheetHead eyebrow="Field" title="Loading…" close={close} />
  const v = p.validation
  return (<>
    <SheetHead eyebrow={`${p.field_area_ha ?? '?'} ha · climate location ${nice(p.name)}`} title={nice(p.name)} close={close} />
    <div className="body">
      {p.boundary?.geometry?.coordinates?.[0] ? <SatelliteField ring={p.boundary.geometry.coordinates[0]} draft={draw ?? undefined} onTap={draw ? (lon, lat) => setDraw([...draw, [lon, lat]]) : undefined}
        label={draw ? 'Tap the corners of your field' : p.boundary.method === 'manual' ? 'Outline drawn by farmer' : 'Placeholder outline · redraw to match your field'} /> : <div className="err">No outline yet.</div>}
      {!draw ? <div className="row"><button className="btn light" style={{ flex: 1 }} onClick={() => { setAuto(''); setDraw([]) }}>Draw by hand</button><button className="btn" style={{ flex: 1 }} onClick={findAuto}>Find my field automatically</button></div> :
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {auto && <span className="faint">{auto}</span>}
          <span className="muted">{draw.length < 3 ? `Tap at least 3 corners (${draw.length} so far).` : `${draw.length} corners${area != null ? ` · ${area} ha` : ''}${area != null && p.field_area_ha ? ` (you said ${p.field_area_ha} ha)` : ''}`}</span>
          <div className="row"><button className="chip" onClick={() => setDraw(draw.slice(0, -1))} disabled={!draw.length}>Undo</button><button className="chip" onClick={() => { setDraw(null); setAuto('') }}>Cancel</button>
            <button className="btn" style={{ flex: 1, minHeight: 40 }} disabled={draw.length < 3} onClick={saveOutline}>Save outline</button></div>
        </div>}
      <div className="between"><span className="faint">Satellite image works anywhere in the world · outline from M3</span><SourceTag s={src} /></div>
      <section className="card">
        <div className="ct">What we know</div>
        <div className="list">
          <div><span style={{ flex: 1 }}>Crops grown</span><b>{rot(p.current_rotation)}</b></div>
          <div><span style={{ flex: 1 }}>Water per season</span><span style={{ textAlign: 'right' }}><b>{p.irrigation.budget_mm_per_season ?? '–'} mm</b><br /><span className="faint">= {p.irrigation_budget_m3 ?? '–'} m³ · {WATER.find(w => w[0] === p.irrigation.water_source)?.[1] ?? 'unknown source'}</span></span></div>
          <div><span style={{ flex: 1 }}>Soil type</span><span style={{ textAlign: 'right' }}><b>{TEXTURES.find(t => t[0] === p.soil.texture)?.[1] ?? 'Unknown'}</b><br /><Tag k={srcKey(p.soil.texture_source)} /></span></div>
          <div><span style={{ flex: 1 }}>Soil pH</span><span style={{ textAlign: 'right' }}><b>{p.soil.ph ?? 'Unknown'}</b><br /><Tag k={srcKey(p.soil.ph_source)} /></span></div>
        </div>
      </section>
      <section className="card">
        <div className="ct">Confirm your soil</div>
        <div className="chips">{TEXTURES.map(([k, l]) => <button key={k} className={'chip' + (p.soil.texture === k && p.soil.texture_source === 'farmer' ? ' on' : '')} onClick={() => save({ soil: k === 'unknown' ? { texture: 'unknown', texture_source: 'unknown' } : { texture: k, texture_source: 'farmer' } })}>{l}</button>)}</div>
        <div className="row">
          <label className="field" style={{ flex: 1 }}>Soil pH (from a soil test)<input inputMode="decimal" value={ph} placeholder="6.5" onChange={e => setPh(e.target.value)} /></label>
          <button className="btn" style={{ alignSelf: 'flex-end', minHeight: 46, padding: '0 16px' }} disabled={!ph || isNaN(+ph) || +ph < 0 || +ph > 14} onClick={() => save({ soil: { ph: +ph, ph_source: 'farmer' } })}>Save</button>
        </div>
      </section>
      {v && (v.missing.length > 0 || v.warnings.length > 0) && <section className="card">
        <div className="ct">Blind spots</div>
        <div className="list">
          {v.missing.map((m: any) => <div key={m.field}><span className="dot" style={{ background: C.red }} /><span style={{ flex: 1 }}>{m.prompt}</span></div>)}
          {v.warnings.map((w: any, i: number) => <div key={i}><span className="dot" style={{ background: C.gold }} /><span style={{ flex: 1 }}>{w.message}</span></div>)}
        </div>
      </section>}
      {err && <div className="err">{err}</div>}
      <button className="btn" onClick={passport}>Evidence passport</button>
    </div>
  </>)
}

function SheetHead({ eyebrow, title, close, back }: any) {
  return <header>
    {back && <button className="round" aria-label="Back" onClick={back}><Icon d={I.back} s={18} /></button>}
    <span style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 2 }}><span className="eb">{eyebrow}</span><span style={{ fontSize: 20, fontWeight: 700, color: C.deep }}>{title}</span></span>
    <button className="round" aria-label="Close" onClick={close}><Icon d={I.x} s={16} /></button>
  </header>
}

/* ------------------------------------------------------------------ ADD FIELD */
type CropRow = { name: string; from: number; to: number }
function AddField({ close, created }: any) {
  const [step, setStep] = useState(0)
  const [crops, setCrops] = useState<any[]>([])
  const [f, setF] = useState<any>({ name: '', area: '0.5', water_source: 'tank', mm: '300', texture: 'unknown' })
  const [rows, setRows] = useState<CropRow[]>([{ name: '', from: 11, to: 2 }])
  const [here, setHere] = useState<{ lat: number; lon: number; place: string; country: string } | null>(null)
  const [geo, setGeo] = useState<'idle' | 'asking' | 'denied'>('idle')
  const [mode, setMode] = useState<'here' | 'world' | null>(null)
  const [site, setSite] = useState<{ lat: number; lon: number; place: string; country: string } | null>(null)
  const [q, setQ] = useState(''), [hits, setHits] = useState<any[]>([]), [searching, setSearching] = useState(false)
  const [err, setErr] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { api.getCrops().then(r => setCrops(r.data ?? [])) }, [])
  const locate = () => {
    if (!navigator.geolocation) { setGeo('denied'); return }
    setGeo('asking')
    navigator.geolocation.getCurrentPosition(async pos => {
      const lat = +pos.coords.latitude.toFixed(5), lon = +pos.coords.longitude.toFixed(5)
      const g = await api.reverseGeo(lat, lon)
      setHere({ lat, lon, place: g?.place ?? '', country: g?.country ?? 'this area' }); setGeo('idle')
    }, () => setGeo('denied'), { enableHighAccuracy: true, timeout: 12000 })
  }
  useEffect(() => { locate() }, [])
  const doSearch = async () => {
    if (!q.trim()) return
    setSearching(true)
    try { setHits(await api.searchPlace(mode === 'here' && here?.country ? `${q}, ${here.country}` : q)) } catch { setHits([]) }
    setSearching(false)
  }
  const idOf = (name: string) => { const n = name.trim().toLowerCase().replace(/\s+/g, '_'); return crops.find(c => c.crop_id === n || [String(c.crop_name ?? ''), crop(c.crop_id)].some(x => x.toLowerCase() === name.trim().toLowerCase()))?.crop_id ?? (crops.length ? null : n) }
  const parsed = rows.map(r => ({ ...r, id: r.name.trim() ? idOf(r.name) : null }))
  const unknown = parsed.filter(r => r.name.trim() && !r.id)
  const titles = ['Where is it?', 'What grows there?', 'Your water', 'Your soil']
  const ok = [f.name.trim().length > 0 && +f.area > 0 && !!site, parsed.some(r => r.id) && !unknown.length, f.water_source === 'rain_only' || +f.mm >= 0, true][step]
  const submit = async () => {
    setBusy(true); setErr('')
    try {
      const good = parsed.filter(r => r.id)
      const body = {
        name: f.name.trim(), site: { latitude: site!.lat, longitude: site!.lon, place: site!.place, country: site!.country }, field_area_ha: +f.area,
        current_rotation: good.map(r => r.id), rotation_calendar: good.map(r => ({ crop_id: r.id, start_month: r.from, end_month: r.to })),
        irrigation: { water_source: f.water_source, budget_mm_per_season: f.water_source === 'rain_only' ? 0 : +f.mm },
        soil: f.texture === 'unknown' ? {} : { texture: f.texture, texture_source: 'farmer' },
      }
      const r = await api.createFarm(body); created(r.farm_id)
    } catch (e) { setErr(`Could not save: ${(e as Error).message}. Is the backend running?`) } finally { setBusy(false) }
  }
  const setRow = (k: number, v: Partial<CropRow>) => setRows(rows.map((r, i) => (i === k ? { ...r, ...v } : r)))
  return (<>
    <SheetHead eyebrow={`New field · step ${step + 1} of 4`} title={titles[step]} close={close} back={step ? () => setStep(step - 1) : undefined} />
    <div className="body">
      <div style={{ display: 'flex', gap: 4 }}>{[0, 1, 2, 3].map(i => <span key={i} className="an" style={{ flex: 1, height: 5, borderRadius: 3, background: i <= step ? C.teal : '#D5DFDB' }} />)}</div>
      {step === 0 && <>
        <label className="field">Field name<input value={f.name} placeholder="Behind the house" onChange={e => setF({ ...f, name: e.target.value })} /></label>
        <section className="card" style={{ gap: 10 }}>
          <div className="row" style={{ gap: 10 }}><span className="ai" style={{ background: 'var(--mint)' }}><Icon d="M12 21s7-6.2 7-11.5A7 7 0 005 9.5C5 14.8 12 21 12 21z M12 12a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" c={C.deep} s={18} /></span>
            <span style={{ flex: 1 }}>{geo === 'asking' ? 'Finding where you are…' : here ? <>You are currently in <b>{here.place ? `${here.place}, ` : ''}{here.country}</b>.</> : geo === 'denied' ? 'Location is off. Search for the place instead.' : 'Allow location to start from where you are.'}</span>
            {geo === 'denied' && <button className="chip" onClick={locate}>Try again</button>}</div>
          <span className="eb">Where is this field?</span>
          <div className="seg" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <button className={mode === 'here' ? 'on' : ''} disabled={!here} onClick={() => { setMode('here'); setHits([]); if (here) setSite({ ...here }) }}>In {here?.country || 'my country'}</button>
            <button className={mode === 'world' ? 'on' : ''} onClick={() => { setMode('world'); setSite(null); setHits([]) }}>Elsewhere in the world</button>
          </div>
          {mode && <div className="row"><input className="tin" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && doSearch()} placeholder={mode === 'here' ? 'Village or area (optional)' : 'Town, region or country'} /><button className="btn" style={{ minHeight: 40 }} onClick={doSearch} disabled={searching}>{searching ? '…' : 'Search'}</button></div>}
          {hits.length > 0 && <div className="list">{hits.map((h, k) => <button key={k} className="hit" onClick={() => { setSite({ lat: h.lat, lon: h.lon, place: h.name, country: h.country }); setHits([]) }}><b>{h.name}</b><span className="faint">{h.country} · {h.lat.toFixed(3)}, {h.lon.toFixed(3)}</span></button>)}</div>}
          {site && <>
            <SatellitePlace square={false} zoom={15} lat={site.lat} lon={site.lon} label={site.place || 'Your field'} caption="Tap the map on your field" onTap={(la, lo) => setSite({ ...site, lat: la, lon: lo })} />
            <span className="faint">{site.place ? `${site.place}, ` : ''}{site.country} · {site.lat.toFixed(4)}, {site.lon.toFixed(4)}. NASA POWER and NASA climate projections cover every point on Earth.</span>
          </>}
        </section>
        <label className="field">Size (hectares)<input inputMode="decimal" value={f.area} onChange={e => setF({ ...f, area: e.target.value })} /></label>
      </>}
      {step === 1 && <>
        <span className="muted">Type each crop you grow and the months it is in the ground. Add one line per crop, in order through the year.</span>
        <datalist id="cropnames">{crops.map(c => <option key={c.crop_id} value={crop(c.crop_id)} />)}</datalist>
        {rows.map((r, k) => {
          const id = parsed[k].id
          return <section key={k} className="croprow">
            <div className="row" style={{ gap: 8 }}>
              <span className="plotsm">{id ? <CropPic id={id} size={30} /> : <span className="faint">{k + 1}</span>}</span>
              <input className="tin" list="cropnames" value={r.name} placeholder="Crop, e.g. Tomato" onChange={e => setRow(k, { name: e.target.value })} aria-label={`Crop ${k + 1}`} />
              {rows.length > 1 && <button className="round" aria-label="Remove crop" onClick={() => setRows(rows.filter((_, i) => i !== k))}><Icon d="M6 6l12 12M18 6L6 18" s={16} /></button>}
            </div>
            <div className="row" style={{ gap: 8 }}>
              <label className="mini">From<select value={r.from} onChange={e => setRow(k, { from: +e.target.value })}>{MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select></label>
              <label className="mini">To<select value={r.to} onChange={e => setRow(k, { to: +e.target.value })}>{MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}</select></label>
            </div>
            {r.name.trim() && !id && <span className="faint" style={{ color: C.red }}>Not in our crop list yet. We can model: {crops.map(c => crop(c.crop_id)).join(', ')}.</span>}
          </section>
        })}
        {rows.length < 6 && <button className="btn light" onClick={() => { const last = rows[rows.length - 1]; const from = last ? last.to % 12 + 1 : 1; setRows([...rows, { name: '', from, to: (from + 2) % 12 + 1 }]) }}>+ Add another crop</button>}
        <section className="card"><span className="eb">Your year</span>
          <div className="simmonths">{MONTHS.map((m, i) => { const r = parsed.find(x => x.id && (api_span(x.from, x.to).includes(i + 1))); return <span key={m} className={r ? 'on' : ''} title={r ? crop(r.id!) : 'bare'}>{m[0]}</span> })}</div>
          <b>{rot(parsed.filter(r => r.id).map(r => r.id!))}</b></section>
      </>}
      {step === 2 && <>
        <div className="chips">{WATER.map(([k, l]) => <button key={k} className={'chip' + (f.water_source === k ? ' on' : '')} onClick={() => setF({ ...f, water_source: k })}>{l}</button>)}</div>
        {f.water_source !== 'rain_only' && <label className="field">Water you can give per season (mm)<input inputMode="numeric" value={f.mm} onChange={e => setF({ ...f, mm: e.target.value })} /></label>}
        <span className="faint">{f.water_source === 'rain_only' ? 'Rain only: no irrigation.' : `= ${(+f.mm * +f.area * 10).toFixed(0)} m³ on ${f.area} ha`}</span>
      </>}
      {step === 3 && <>
        <div className="chips">{TEXTURES.map(([k, l]) => <button key={k} className={'chip' + (f.texture === k ? ' on' : '')} onClick={() => setF({ ...f, texture: k })}>{l}</button>)}</div>
        <span className="faint">Not sure? Leave it as “Don't know”: it stays a blind spot instead of a guess.</span>
      </>}
      {err && <div className="err">{err}</div>}
      <button className="btn" disabled={!ok || busy} onClick={() => (step < 3 ? setStep(step + 1) : submit())}>{step < 3 ? 'Next' : busy ? 'Saving…' : 'Save field'}</button>
    </div>
  </>)
}
const api_span = (a: number, b: number) => { const out = [a]; let m = a; while (m !== b && out.length < 12) { m = m % 12 + 1; out.push(m) } return out }

/* ------------------------------------------------------------------ PLANS */
const FAM: Record<string, string> = { Poaceae: 'grass family', Fabaceae: 'legume', Solanaceae: 'nightshade', Amaryllidaceae: 'onion family', Brassicaceae: 'cabbage family', Convolvulaceae: 'morning glory' }
const rs = (v: number | null | undefined) => (v == null ? '–' : `Rs ${Math.round(v).toLocaleString()}`)
const SUIT: Record<string, [string, string, string]> = { suitable: ['#E8F3EF', '#276146', 'Suits the season'], marginal: ['#FBF5E6', '#8A6A12', 'Marginal'], unsuitable: ['#F8ECE7', '#B5523A', 'Too hot or cold'], unknown: ['#F2F6F4', '#6B7C77', 'Not checked'] }

function YearStrip({ plan, label }: { plan: any; label: string }) {
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    <span className="faint" style={{ fontWeight: 700 }}>{label}</span>
    <div className="ystrip">{plan.calendar.map((m: any, k: number) => {
      const bareRisk = !m.crop_id && m.heavy_rain
      return <span key={k} title={`${m.month}: ${m.crop_id ? crop(m.crop_id) : 'bare soil'}${m.heavy_rain ? ', heavy rain' : ''}`}
        className={'ycell' + (m.crop_id ? '' : ' bare') + (bareRisk ? ' risk' : '')}>{m.crop_id ? <CropPic id={m.crop_id} size={20} /> : null}</span>
    })}</div>
  </div>
}

const advKind = (a: string): [string, string, string] =>
  /water|irrigation|mm /i.test(a) ? [I.drop, '#E8F1F5', C.water]
  : /Rs |harvest|worth/i.test(a) ? ['M12 4v16 M16 8c0-1.7-1.8-3-4-3s-4 1.3-4 3 1.8 2.6 4 3 4 1.3 4 3-1.8 3-4 3-4-1.3-4-3', '#FBF5E6', '#8A6A12']
  : /°C|hot|cold|tolerat|range/i.test(a) ? ['M12 7a5 5 0 100 10 5 5 0 000-10z M12 2v2 M12 20v2 M4 12H2 M22 12h-2', '#FBEFEA', C.red]
  : /pH/i.test(a) ? ['M9 3h6 M10 3v6l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3', '#F2F6F4', C.mut]
  : [I.leaf, '#E8F3EF', '#276146']

function planConfidence(p: any, planRes: any, best?: any, plans?: any[]) {
  const gaps: string[] = []
  if (p?.soil?.ph == null) gaps.push('soil pH not tested')
  if (!p?.soil?.texture || p.soil.texture === 'unknown' || p.soil.texture_source === 'map_estimate') gaps.push('soil type estimated')
  if (!p?.prices_rs_per_kg && !p?.costs_rs_per_ha) gaps.push('example prices')
  if (planRes?.data?.status && planRes.data.status !== 'modelled') gaps.push('no climate data')
  if (planRes?.source === 'cached') gaps.push('saved results, not live')
  if (best && plans && plans.length > 1) {
    const second = plans.filter(x => x.id !== best.id).sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0]
    if (second && (best.score ?? 0) - (second.score ?? 0) < 0.05) gaps.push(`close call with ${second.label}`)
  }
  const level = gaps.length <= 1 ? 'High' : gaps.length <= 3 ? 'Medium' : 'Low'
  return { level, gaps, why: `Confidence ${level.toLowerCase()}${gaps.length ? `: ${gaps.join(', ')}.` : ': all key inputs known.'}` }
}

function TwinPlans({ p, a, town }: any) {
  const [r, setR] = useState<{ base: any; twin: any } | null>(null)
  const mc: any[] = a.monthly_comparison ?? []
  useEffect(() => {
    if (!p?.current_rotation?.length || mc.length !== 12) return
    let on = true; setR(null)
    Promise.all([api.plans(p.farm_id, {}, 'base'), api.plans(p.farm_id, { climate_monthly: { temperature_c: mc.map(m => m.candidate_t_c), precipitation_mm: mc.map(m => m.candidate_p_mm) } }, `twin|${a.location.id}`)])
      .then(([b, t]) => on && setR({ base: b.data, twin: t.data }))
    return () => { on = false }
  }, [p?.farm_id, a.location.id])
  if (!r) return mc.length === 12 ? <div className="twinplan"><Spinner text={`Testing your plans in a ${town}-like climate…`} /></div> : null
  if (!r.twin || !r.base) return null
  const tb = r.twin.plans.find((x: any) => x.id === r.twin.best_plan_id), tt = r.twin.plans[0], bt = r.base.plans[0]
  const dw = tt.water.total_mm != null && bt.water.total_mm ? Math.round((tt.water.total_mm / bt.water.total_mm - 1) * 100) : null
  return <div className="twinplan">
    <b>What this means for {nice(p.name)}</b>
    <div className="adv"><span className="ai" style={{ background: '#F8ECE7' }}><Icon d="M12 3l9 16H3z M12 10v4 M12 17h.01" c={C.red} s={15} /></span><span>Keep {rot(tt.rotation)} and it ranks <b>#{tt.rank} of {r.twin.plans.length}</b> in a {town}-like climate.{dw != null ? ` It would need ${Math.abs(dw)}% ${dw >= 0 ? 'more' : 'less'} watering than today.` : ''}</span></div>
    {tb.id !== 'current' && <div className="adv"><span className="ai" style={{ background: 'var(--mint)' }}><Icon d="M5 12h12 M13 7l5 5-5 5" c={C.deep} s={15} /></span><span>Best for that climate: <b>{tb.label}, {rot(tb.rotation)}</b>.{tb.income?.profit_rs != null && tt.income?.profit_rs != null ? ` Profit about ${rs(tb.income.profit_rs)} a year vs ${rs(tt.income.profit_rs)} if you keep today's crops.` : ''}</span></div>}
    <span className="faint">Same plan engine, run on {town}'s climate today. Start the change now, so your farm keeps feeding you and paying when that climate arrives.</span>
  </div>
}

function TwinCompare({ p, loc, a, name, hist }: any) {
  const ring: number[][] = p?.boundary?.geometry?.coordinates?.[0] ?? []
  const pts = ring.slice(0, -1)
  const mine = pts.length ? { lat: pts.reduce((x, c) => x + c[1], 0) / pts.length, lon: pts.reduce((x, c) => x + c[0], 0) / pts.length } : { lat: loc.latitude, lon: loc.longitude }
  const [farm, setFarm] = useState<{ lat: number; lon: number } | null | undefined>(undefined)
  useEffect(() => { let on = true; setFarm(undefined); api.nearestFarmland(a.location.latitude, a.location.longitude).then(r => on && setFarm(r)); return () => { on = false } }, [a.location.id])
  const there = farm ?? { lat: a.location.latitude, lon: a.location.longitude }
  const town = name.split(',')[0]
  const mc: any[] = a.monthly_comparison ?? []
  const avg = (xs: number[]) => xs.reduce((x, y) => x + y, 0) / xs.length
  const now = hist?.temperature_c?.length === 12 ? { t: avg(hist.temperature_c), r: hist.precipitation_mm.reduce((x: number, y: number) => x + y, 0) } : null
  const fut = mc.length === 12 ? { t: avg(mc.map(m => m.future_t_c)), r: mc.reduce((x, m) => x + m.future_p_mm, 0) } : null
  const tw = mc.length === 12 ? { t: avg(mc.map(m => m.candidate_t_c)), r: mc.reduce((x, m) => x + m.candidate_p_mm, 0) } : null
  return <>
    <div className="twinpics">
      <SatellitePlace key={`m${mine.lat}`} square zoom={16} lat={+mine.lat.toFixed(6)} lon={+mine.lon.toFixed(6)} label={nice(loc.name)} caption="Your field today" />
      {farm === undefined ? <div className="twinwait"><Spinner text="Finding farmland…" /></div>
        : <SatellitePlace key={`t${there.lat}`} square zoom={16} lat={+there.lat.toFixed(6)} lon={+there.lon.toFixed(6)} label={name} caption={farm ? `Farmland near ${town}` : `${town} today`} />}
    </div>
    <TwinPlans p={p} a={a} town={town} />
    {now && fut && tw && <div className="twincmp">
      <div><small>Your field today</small><b>{now.t.toFixed(1)} °C</b><span>{Math.round(now.r)} mm rain</span></div>
      <div className="mid"><small>Your field, 2050s</small><b>{fut.t.toFixed(1)} °C</b><span>{Math.round(fut.r)} mm rain</span></div>
      <div className="tw"><small>{town} today</small><b>{tw.t.toFixed(1)} °C</b><span>{Math.round(tw.r)} mm rain</span></div>
    </div>}
    <span className="faint">{farm ? `Left: your field. Right: the nearest mapped farmland to ${town} (OpenStreetMap), so you can see what farms in a climate like your future one look like today.` : `Left: your field. Right: ${town}.`} Zoom with + and −.</span>
  </>
}

function StressPick({ data }: any) {
  const passes = (r: any) => r.cells.filter((c: any) => c.ok).length
  const [sel, setSel] = useState(0)
  useEffect(() => { setSel(0) }, [data.rows.length])
  const r = data.rows[Math.min(sel, data.rows.length - 1)]
  return <>
    <div className="splans">{data.rows.map((x: any, k: number) => <button key={x.id + k} className={k === sel ? 'on' : ''} onClick={() => setSel(k)}>
      <b>{x.label.replace(' (heat-ready)', '')}</b>{x.label.includes('heat-ready') && <small>heat-ready</small>}<span>{passes(x)}/{x.cells.length}</span></button>)}</div>
    <div className="srot">{r.rotation.map((c: string, k: number) => <span key={k} className="row" style={{ gap: 3 }}><CropPic id={c} size={26} />{k < r.rotation.length - 1 && <span className="faint">→</span>}</span>)}<span className="muted" style={{ marginLeft: 6 }}>{rot(r.rotation)}</span></div>
    <div className="scircles" key={sel}>{r.cells.map((c: any, k: number) => {
      const why = c.tip.split(': ').slice(1).join(': ')
      return <div key={k} className={'scirc ' + (c.ok ? 'ok' : 'bad') + (c.best ? ' best' : '')} title={c.tip}>
        <span className="ring"><Icon d={c.ok ? 'M5 12.5l4.5 4.5L19 7.5' : 'M7 7l10 10M17 7L7 17'} c={c.best ? C.deep : '#fff'} s={22} /></span>
        <b>{data.cols[k].label}</b>
        <small>{c.best ? 'Best here' : c.ok ? 'Works' : 'Fails'}</small>
        {!c.ok && why && <em>{why.replace(/^Needs /, 'Needs ').slice(0, 70)}</em>}
      </div>
    })}</div>
  </>
}

const FEAT: Record<string, [string, string]> = { water: ['Water use', '#3B7EA1'], soil: ['Soil care', '#8A6A43'], climate: ['Climate fit', '#0C8A84'], income: ['Profit', '#C98B00'] }
function ShapChart({ plan, weights }: any) {
  const sh = plan.shap
  if (!sh) return null
  const vals: [string, number][] = Object.entries(sh.values as Record<string, number>)
  const max = Math.max(0.05, ...vals.map(([, v]) => Math.abs(v)))
  const f = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(Math.round(v * 100))}`
  return <div className="shap">
    <span className="muted">Each bar shows how much a factor pushes <b>{plan.label}</b> above or below the average plan ({Math.round(sh.base_value * 100)}). Together they add up to its score of {Math.round((plan.score ?? 0) * 100)}.</span>
    <div className="shrow base"><span>Average plan</span><span className="shtrack" /><b>{Math.round(sh.base_value * 100)}</b></div>
    {vals.map(([k, v]) => <div key={k} className="shrow" title={`index ${Math.round(sh.features[k].index * 100)} vs average ${Math.round(sh.features[k].mean_index * 100)}, weight ${Math.round((weights[k] ?? 0) * 100)}%`}>
      <span>{FEAT[k]?.[0] ?? k}<small>{Math.round((weights[k] ?? 0) * 100)}% weight</small></span>
      <span className="shtrack"><i style={{ [v >= 0 ? 'left' : 'right']: '50%', width: `${(Math.abs(v) / max) * 50}%`, background: v >= 0 ? C.teal : C.red } as any} /></span>
      <b style={{ color: v >= 0 ? '#276146' : C.red }}>{f(v)}</b>
    </div>)}
    <div className="shrow total"><span>{plan.label} score</span><span className="shtrack" /><b>{Math.round((plan.score ?? 0) * 100)}</b></div>
    <span className="faint">{sh.method}. Green pushes the score up, red pulls it down.</span>
  </div>
}

function ProfitCard({ d, sel }: any) {
  const plans: any[] = d.plans
  if (!plans.some(p => p.income?.profit_rs != null)) return null
  const today = plans[0], max = Math.max(1, ...plans.map(p => Math.abs(p.income?.profit_rs ?? 0)))
  return <section className="card">
    <div className="between"><div><div className="eb">Profit per year</div><div className="ct">Harvest value minus growing costs</div></div><Tag k="modelled" text="Estimate" /></div>
    <div className="list">{plans.map(p => {
      const pf = p.income?.profit_rs ?? 0, dlt = pf - (today.income?.profit_rs ?? 0)
      return <div key={p.id} style={{ alignItems: 'center', background: p.id === sel.id ? 'var(--mint)' : undefined, borderRadius: 10, padding: '6px 6px' }}>
        <span style={{ width: 54, fontWeight: 700, fontSize: 13 }}>{p.label}</span>
        <span style={{ flex: 1, height: 10, background: '#EEF2EF', borderRadius: 5, overflow: 'hidden' }}><i style={{ display: 'block', height: 10, width: `${Math.max(0, pf) / max * 100}%`, background: pf >= 0 ? C.gold : C.red }} /></span>
        <span style={{ width: 120, textAlign: 'right', fontSize: 12.5 }}><b>{rs(pf)}</b><br /><span style={{ color: dlt > 0 ? '#276146' : dlt < 0 ? C.red : C.mut, fontWeight: 700 }}>{p.id === 'current' ? 'today' : `${dlt >= 0 ? '+' : '−'}${rs(Math.abs(dlt))}${today.income?.profit_rs > 0 ? ` (${dlt >= 0 ? '+' : '−'}${Math.abs(Math.round(dlt / today.income.profit_rs * 100))}%)` : ''}`}</span></span>
      </div>
    })}</div>
    <span className="faint">Harvest {rs(sel.income?.harvest_value_rs)} − costs {rs(sel.income?.cost_rs)} for {sel.label} on {sel.income?.area_ha} ha. Change prices and costs in Settings (gear, top right).</span>
  </section>
}

function SimPop({ plan, step, setStep }: any) {
  const n = plan.crops.length, done = step >= n, cur = plan.crops[Math.min(step, n - 1)]
  const months: string[] = cur.months, nm = Math.max(1, months.length)
  const [mi, setMi] = useState(0)
  const [paused, setPaused] = useState(false)
  const [photo, setPhoto] = useState<api.Photo | null | undefined>(undefined)
  useEffect(() => { setMi(0) }, [step])
  useEffect(() => {
    if (done || paused) return
    const t = window.setTimeout(() => (mi + 1 < nm ? setMi(mi + 1) : setStep(step + 1)), 5000 / nm)
    return () => window.clearTimeout(t)
  }, [mi, step, done, nm, paused])
  const stage = nm === 1 ? 4 : Math.round((mi / (nm - 1)) * 4)
  const [sb, sf, st] = SUIT[cur.suitability] ?? SUIT.unknown
  const curMonth = months[mi]
  useEffect(() => { if (done) return; let on = true; setPhoto(undefined); api.stagePhoto(cur.crop_id, stage).then(r => on && setPhoto(r)); return () => { on = false } }, [cur.crop_id, stage, done])
  return <div className="scrim center" onClick={() => setStep(null)}>
    <div className="simpop" onClick={e => e.stopPropagation()} role="dialog" aria-label="Season simulation">
      <div className="between"><div><div className="eb">{plan.label} · season simulation</div><div className="ct">{rot(plan.rotation)}</div></div>
        <button className="round" aria-label="Close" onClick={() => setStep(null)}><Icon d="M6 6l12 12M18 6L6 18" s={18} /></button></div>
      <div className="simdots">{plan.crops.map((c: any, k: number) => <button key={k} className={k === step ? 'on' : k < step ? 'past' : ''} onClick={() => setStep(k)}><CropPic id={c.crop_id} size={22} /><span>{c.season_label}</span></button>)}</div>
      {!done ? <>
        <div className={'simplot' + (photo ? ' photo' : '')}>
          {photo ? <img key={photo.url} className="stagephoto" src={photo.url} alt={`${crop(cur.crop_id)}, ${STAGES[stage].toLowerCase()} stage`} onError={() => setPhoto(null)} />
            : <span key={`${step}-${stage}`} className="stagein"><StagePic stage={stage} id={cur.crop_id} size={120} /></span>}
          <span className="simtag">{curMonth}</span>
          {paused && <span className="simtag" style={{ left: 'auto', right: 12, background: C.deep, color: '#fff' }}>Paused</span>}</div>
        {photo && <a className="faint" href={photo.page} target="_blank" rel="noreferrer" style={{ marginTop: -6, fontSize: 10.5 }}>Photo: {photo.credit}, Wikimedia Commons</a>}
        <div className="stages">{STAGES.map((sname, k) => <span key={sname} className={k === stage ? 'on' : k < stage ? 'past' : ''}>{sname}</span>)}</div>
        <div style={{ textAlign: 'center' }}><div className="ct">{crop(cur.crop_id)}: {STAGES[stage].toLowerCase()} in {MONTH_FULL[MONTHS.indexOf(curMonth)] ?? curMonth}</div><span className="muted">{cur.season_label} · month {mi + 1} of {nm}{paused ? ' · stopped' : ''}</span></div>
        <div className="simmonths">{MONTHS.map((m) => { const k = months.indexOf(m); return <span key={m} className={m === curMonth ? 'now' : k >= 0 && k < mi ? 'past' : k >= 0 ? 'on' : ''}>{m[0]}</span> })}</div>
        <div className="row" style={{ gap: 6, flexWrap: 'wrap', justifyContent: 'center' }}>
          <span className="pill" style={{ background: sb, color: sf }}>{st}{cur.season_temperature_c != null ? ` · ${cur.season_temperature_c} °C` : ''}</span>
          {cur.irrigation_need_mm != null && <span className="pill" style={{ background: '#E8F1F5', color: C.water }}>{Math.round(cur.irrigation_need_mm)} mm water this season</span>}
          {cur.harvest && stage === 4 && <span className="pill" style={{ background: '#F2F6F4', color: C.ink }}>≈ {cur.harvest.tonnes} t harvested</span>}
        </div>
        <div className="row" style={{ justifyContent: 'center', gap: 8 }}>
          <button className="btn light" style={{ minHeight: 40, padding: '0 18px' }} onClick={() => setPaused(!paused)}>{paused ? '▶ Resume' : '■ Stop here'}</button>
          {paused && <button className="chip" onClick={() => { setPaused(false); setMi(0) }}>Restart this season</button>}
        </div>
      </> : <>
        <div className="simplot" style={{ gap: 6 }}>{plan.crops.map((c: any, k: number) => <CropPic key={k} id={c.crop_id} size={64} />)}</div>
        <div style={{ textAlign: 'center' }}><div className="ct">One year done</div><span className="muted">{plan.water.total_mm != null ? `${Math.round(plan.water.total_mm)} mm of watering` : ''}{plan.income?.profit_rs != null ? ` · profit about ${rs(plan.income.profit_rs)}` : ''}</span></div>
        <button className="btn" onClick={() => setStep(0)}>Play again</button>
      </>}
    </div>
  </div>
}

function Settings({ close, p, planRes, onPrices, farms, farmId, setFarmId }: any) {
  return <>
    <SheetHead eyebrow="Settings" title="Prices and costs" close={close} />
    <div className="body">
      <span className="muted">Used for harvest value and profit in Plans. Each field keeps its own prices.</span>
      <div className="seg" style={{ gridTemplateColumns: `repeat(${Math.min(farms.length, 4)}, 1fr)` }}>{farms.slice(0, 4).map((f: any) => <button key={f.farm_id} className={f.farm_id === farmId ? 'on' : ''} onClick={() => setFarmId(f.farm_id)}>{nice(f.name)}</button>)}</div>
      {!p || !planRes?.data ? <Spinner text="Loading this field's plans…" /> : <PriceCard p={p} d={planRes.data} onSave={onPrices} />}
    </div>
  </>
}

function PriceCard({ p, d, onSave }: any) {
  const ids: string[] = Array.from(new Set<string>((d?.plans ?? []).flatMap((x: any) => x.rotation)))
  const [vals, setVals] = useState<Record<string, [string, string]>>({})
  const [state, setState] = useState('')
  const cost0 = (c: string) => d?.plans?.flatMap((x: any) => x.crops).find((cr: any) => cr.crop_id === c && cr.harvest)
  useEffect(() => {
    setVals(Object.fromEntries(ids.map(c => {
      const cr = cost0(c), area = d?.plans?.[0]?.income?.area_ha || 1
      return [c, [String(p.prices_rs_per_kg?.[c] ?? d?.prices_rs_per_kg?.[c] ?? ''), String(p.costs_rs_per_ha?.[c] ?? (cr ? Math.round(cr.harvest.cost_rs / area) : ''))]]
    }))); setState('')
  }, [p.farm_id, ids.join()])
  if (!ids.length) return null
  const save = async () => {
    const pr: Record<string, number> = {}, co: Record<string, number> = {}
    for (const [k, [a, b]] of Object.entries(vals)) { if (a !== '' && isFinite(+a) && +a >= 0) pr[k] = +a; if (b !== '' && isFinite(+b) && +b >= 0) co[k] = +b }
    setState('Saving…'); setState((await onSave(pr, co)) ? 'Saved · plans updated' : 'Not saved: backend offline')
  }
  const set = (c: string, i: 0 | 1, v: string) => setVals({ ...vals, [c]: (i === 0 ? [v, vals[c]?.[1] ?? ''] : [vals[c]?.[0] ?? '', v]) as [string, string] })
  const mine = p.prices_rs_per_kg || p.costs_rs_per_ha
  return <section className="card">
    <div className="between"><div><div className="eb">Your prices and costs</div><div className="ct">For profit per plan</div></div><Tag k={mine ? 'entered' : 'pending'} text={mine ? 'You entered' : 'Example values'} /></div>
    <div className="pricegrid"><span /><span className="faint">Sell Rs/kg</span><span className="faint">Cost Rs/ha</span>
      {ids.map(c => <Fragment key={c}><span className="row" style={{ gap: 6 }}><CropPic id={c} size={26} />{crop(c)}</span>
        <input inputMode="decimal" aria-label={`${crop(c)} price`} value={vals[c]?.[0] ?? ''} onChange={e => set(c, 0, e.target.value)} />
        <input inputMode="decimal" aria-label={`${crop(c)} cost`} value={vals[c]?.[1] ?? ''} onChange={e => set(c, 1, e.target.value)} /></Fragment>)}
    </div>
    <div className="row"><span className="faint" style={{ flex: 1 }}>{state || 'Yields: Mauritius averages (Statistics Mauritius 2023–24). Costs are per crop per hectare.'}</span><button className="btn" style={{ minHeight: 38 }} onClick={save}>Save</button></div>
  </section>
}

function Plans({ p, planRes, refresh }: any) {
  const [i, setI] = useState(0)
  const [step, setStep] = useState<number | null>(null)
  const busy = false
  const d = planRes?.data
  const plans: any[] = d?.plans ?? []
  const sel = plans[Math.min(i, Math.max(plans.length - 1, 0))]
  useEffect(() => { setI(0); setStep(null) }, [p?.farm_id])
  if (!p) return <Spinner text="Loading farm…" />
  const head = (<>
    <div><div className="eb">Plans for this field</div><h1 className="h1" style={{ marginTop: 6 }}>{nice(p.name)} <span>· season by season</span></h1></div>
    <div className="ctx">
      <span><small>Soil</small><b>{TEXTURES.find(t => t[0] === p.soil.texture)?.[1] ?? 'Unknown'}</b></span>
      <span><small>pH</small><b>{p.soil.ph ?? '?'}</b></span>
      <span><small>Water / season</small><b>{p.irrigation.budget_mm_per_season ?? '?'} mm</b></span>
      <span><small>Crops now</small><b>{rot(p.current_rotation)}</b></span>
    </div>
  </>)
  if (!p.current_rotation?.length) return <>{head}<div className="err">Add the crops you grow in Fields to compare plans.</div></>
  if (!planRes || busy) return <>{head}<Spinner text="Comparing plans: water need, suitability, rotation rules…" /></>
  if (!d) return <>{head}<div className="err">The plan engine did not answer ({planRes.error}). <button className="chip" onClick={refresh}>Try again</button></div></>
  const best = plans.find((x: any) => x.id === d.best_plan_id) ?? plans[0]
  const today = plans[0]
  const lab = (x: any) => x.label
  const pct = (v: number | null) => (v == null ? '–' : `${Math.round(v * 100)}`)
  const conf = planConfidence(p, planRes, best, plans)
  return (<>
    {head}
    <Hero bg={C.deep} eyebrow={`Best for ${nice(p.name)}`} badges={[`Score ${pct(best.score)}/100`, `Confidence: ${conf.level}`]}
      title={!plans.some((x: any) => x.feasible) ? 'No plan fits\nyour water yet.' : best.id === 'current' ? 'Your rotation\nis already the best.' : `${lab(best)}: ${rot(best.rotation)}`}
      sub={!plans.some((x: any) => x.feasible) ? `The thriftiest plan needs ${Math.round(Math.min(...plans.map((x: any) => x.water.peak_season_mm ?? 1e9)))} mm of watering in its driest season; you can give ${p.irrigation.budget_mm_per_season ?? 0} mm. Plans are still ranked below; add a tank or set your water in the Water tab.` : best.id === 'current' ? `${best.reasons[0]} ${conf.why}` : `${conf.why} Today's rotation scores ${pct(today.score)}.${best.income?.harvest_value_rs ? ` Profit ${rs(best.income.profit_rs)} a year, ${(best.income.profit_rs ?? 0) >= (today.income?.profit_rs ?? 0) ? '+' : '−'}${rs(Math.abs((best.income.profit_rs ?? 0) - (today.income?.profit_rs ?? 0)))} vs today.` : ''} ${best.reasons[0]}`} />
    <div className="tabs" role="tablist">{plans.map((x, k) => <button key={x.id} role="tab" className={k === i ? 'on' : ''} onClick={() => { setI(k); setStep(null) }}>{x.label} <span className="rk">#{x.rank}</span></button>)}</div>

    <section className="card">
      <div className="between">
        <div><div className="eb">{sel.label} · rank {sel.rank} of {plans.length}</div><div className="ct">{rot(sel.rotation)}</div></div>
        <button className="play" aria-label={step == null ? 'Play the seasons' : 'Stop'} onClick={() => setStep(step == null ? 0 : null)}><Icon d={step == null ? 'M8 5l11 7-11 7z' : 'M6 5h4v14H6z M14 5h4v14h-4z'} c="#fff" s={16} /></button>
      </div>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
        <span className="pill" style={{ background: sel.feasible ? '#E8F3EF' : '#F8ECE7', color: sel.feasible ? '#276146' : C.red, fontSize: 12 }}>{sel.feasible ? 'Works with your water' : 'Does not fit'}</span>
        <span className="pill" style={{ background: '#F2F6F4', color: C.ink, fontSize: 12 }}>Score {pct(sel.score)} / 100</span>
        {sel.water.peak_season_mm != null && <span className="pill" style={{ background: '#E8F1F5', color: C.water, fontSize: 12 }}>Needs {Math.round(sel.water.peak_season_mm)} mm in its driest season</span>}
      </div>
      {sel.id === 'current' && sel.rank === plans.length && <div className="note-last">If you keep this rotation for the coming year, it ranks last of the {plans.length} plans.</div>}
      {sel.failed_constraints.map((f: any, k: number) => <div key={k} className="err">{f.message}</div>)}
      <div className="seasons" style={{ gridTemplateColumns: `repeat(${sel.crops.length}, 1fr)` }}>
        {sel.crops.map((s: any, k: number) => {
          const [sb, sf, st] = SUIT[s.suitability] ?? SUIT.unknown
          return <div key={k} className="season">
            <span className="faint" style={{ fontWeight: 700 }}>{s.season_label}</span>
            <div className="plot"><CropPic id={s.crop_id} size={58} /></div>
            <b>{crop(s.crop_id)}</b>
            <span className="faint">{FAM[s.family] ?? s.family} · {s.months.length} mo</span>
            <span className="pill" style={{ background: sb, color: sf }}>{st}{s.season_temperature_c != null ? ` · ${s.season_temperature_c} °C` : ''}</span>
            {s.irrigation_need_mm != null && <span className="pill" style={{ background: '#E8F1F5', color: C.water }}>{Math.round(s.irrigation_need_mm)} mm water</span>}
            {s.harvest && <span className="pill" style={{ background: '#F2F6F4', color: C.ink }} title={`${s.harvest.tonnes} t at Rs ${s.harvest.price_rs_per_kg}/kg, cost ${rs(s.harvest.cost_rs)}`}>≈ {s.harvest.tonnes} t · profit {rs(s.harvest.profit_rs)}</span>}
          </div>
        })}
      </div>
    </section>
    {step != null && <SimPop plan={sel} step={step} setStep={setStep} />}

    <section className="card">
      <div className="ct">Your year, month by month</div>
      <div className="ystrip mhead">{MONTH_L.map((m, k) => <span key={k} className="ycell head">{m}</span>)}</div>
      <YearStrip plan={today} label="Today" />
      {sel.id !== 'current' && <YearStrip plan={sel} label={sel.label} />}
      <div className="row" style={{ gap: 12, flexWrap: 'wrap', fontSize: 11.5, color: C.mut }}>
        <span className="row" style={{ gap: 5 }}><span className="ycell bare" style={{ width: 14, height: 14 }} />Bare soil</span>
        <span className="row" style={{ gap: 5 }}><span className="ycell bare risk" style={{ width: 14, height: 14 }} />Bare in heavy rain: erosion</span>
      </div>
    </section>

    <ProfitCard d={d} sel={sel} />

    <section className="advice2">
      <div className="eb">What to do on {nice(p.name)}</div>
      {best.id !== 'current' && <div className="adv-main"><span className="ai" style={{ background: C.deep }}><Icon d="M5 12h12 M13 7l5 5-5 5" c="#fff" s={18} /></span>
        <div><b>Switch to {lab(best)}</b><span>{rot(best.rotation)}, ranked first for what you care about. Keeping {rot(today.rotation)} next year ranks #{today.rank} of {plans.length}{today.rank === plans.length ? ' (last)' : ''}.</span></div></div>}
      {today.income?.profit_rs != null && <div className="profitcmp">
        <div><small>Keep today's rotation</small><b>{rs(today.income.profit_rs)}</b><span>a year</span></div>
        {best.id !== 'current' && <><span className="arrow">→</span>
        <div className="win"><small>Switch to {lab(best)}</small><b>{rs(best.income.profit_rs)}</b><span className={best.income.profit_rs >= today.income.profit_rs ? 'up' : 'down'}>{best.income.profit_rs >= today.income.profit_rs ? '+' : '−'}{rs(Math.abs(best.income.profit_rs - today.income.profit_rs))}{today.income.profit_rs > 0 ? ` (${best.income.profit_rs >= today.income.profit_rs ? '+' : '−'}${Math.abs(Math.round((best.income.profit_rs / today.income.profit_rs - 1) * 100))}%)` : ''} a year</span></div></>}
      </div>}
      {[...sel.reasons.slice(0, 5), ...(p.soil.ph == null ? ['Test your soil pH so each crop can be checked against its needs.'] : [])].map((a: string, k: number) => {
        const t = advKind(a)
        return <div key={k} className="adv"><span className="ai" style={{ background: t[1] }}><Icon d={t[0]} c={t[2]} s={16} /></span><span>{a}</span></div>
      })}
      <span className="faint">From the M2 plan engine: NASA POWER climate, FAO-56 water use, FAO ECOCROP ranges. Check big changes with your extension officer.</span>
    </section>


    <details className="card xai">
      <summary><div><div className="eb">How this is calculated</div><div className="ct">Explainable AI · SHAP</div></div><span className="chev">⌄</span></summary>
      <ShapChart plan={sel} weights={d.weights} />
      <details><summary className="faint" style={{ cursor: 'pointer', fontWeight: 700 }}>Method and assumptions</summary>
        <div className="list" style={{ marginTop: 8 }}>{d.assumptions.map((a: string, k: number) => <div key={k}><span className="dot" style={{ background: '#A9BAB5' }} /><span style={{ flex: 1 }}>{a}</span></div>)}</div>
      </details>
    </details>
  </>)
}

/* ------------------------------------------------------------------ WATER */
function Water({ p, planRes, onSaved }: any) {
  const [mm, setMm] = useState<number>(p?.irrigation?.budget_mm_per_season ?? 0)
  const [state, setState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const t = useRef<number | undefined>(undefined)
  useEffect(() => { setMm(p?.irrigation?.budget_mm_per_season ?? 0) }, [p?.farm_id])
  if (!p) return <Spinner text="Loading farm…" />
  const rainOnly = p.irrigation.water_source === 'rain_only'
  const m3 = p.field_area_ha ? Math.round(mm * p.field_area_ha * 10) : null
  const change = (v: number) => {
    setMm(v); setState('saving'); window.clearTimeout(t.current)
    t.current = window.setTimeout(async () => {
      try { onSaved(await api.patchFarm(p.farm_id, { irrigation: { budget_mm_per_season: v, ...(rainOnly && v > 0 ? { water_source: 'tank' } : {}) } })); setState('saved') } catch { setState('error') }
    }, 600)
  }
  const d = planRes?.data
  const plans: any[] = d?.plans ?? []
  const today = plans[0], best = plans.find(x => x.id === d?.best_plan_id)
  const clim: any[] = d?.climate ?? []
  const fits = plans.filter(x => x.water.peak_season_mm != null && x.water.peak_season_mm <= mm).length
  const maxM = Math.max(1, ...plans.flatMap(x => x.water.monthly_mm ?? [0]))
  return (<>
    <div><div className="eb">Smart irrigation</div><h1 className="h1" style={{ marginTop: 6 }}>Water, <span>well spent.</span></h1></div>
    <Hero eyebrow={`Water wallet · ${nice(p.name)}`} badges={d ? [`Confidence: ${planConfidence(p, planRes).level}`] : undefined}
      title={!d ? 'Checking water\nneeds…' : `${fits} of ${plans.length} plans fit\nyour water.`}
      sub={`You can give ${Math.round(mm)} mm a season${m3 != null ? ` (${m3.toLocaleString()} m³ on ${p.field_area_ha} ha)` : ''}.${today?.water?.peak_season_mm != null ? ` Today's rotation needs ${Math.round(today.water.peak_season_mm)} mm in its driest season${best && best.id !== 'current' ? `; ${best.label} needs ${Math.round(best.water.peak_season_mm)} mm` : ''}.` : ''}`} />
    <section className="card">
      <div className="between"><div><div className="eb">Water you can give</div><span className="muted">per season, saved to your farm</span></div><Tag k="entered" /></div>
      <div className="row" style={{ alignItems: 'baseline', gap: 6 }}><span style={{ fontSize: 36, fontWeight: 700, color: C.deep }}>{Math.round(mm)}</span><span className="muted">mm</span>
        <span className="faint" style={{ marginLeft: 'auto' }}>{state === 'saving' ? 'Saving…' : state === 'saved' ? 'Saved · plans updated' : state === 'error' ? 'Not saved: backend offline' : ''}</span></div>
      <input type="range" min={0} max={1000} step={25} value={mm} onChange={e => change(+e.target.value)} aria-label="Water per season" />
      <div className="list">{plans.map(x => {
        const need = x.water.peak_season_mm, ok = need != null && need <= mm
        return <div key={x.id}><span className="dot" style={{ background: need == null ? '#A9BAB5' : ok ? C.teal : C.red }} /><span style={{ flex: 1 }}><b>{x.label}</b> · {rot(x.rotation)}</span><b style={{ color: need == null ? C.mut : ok ? '#276146' : C.red }}>{need == null ? '–' : `${Math.round(need)} mm`}</b></div>
      })}</div>
    </section>
    <section className="card">
      <div className="between"><div><div className="eb">Watering needed each month</div><div className="ct">Today vs {best && best.id !== 'current' ? best.label : 'best plan'}</div></div><Tag k="modelled" text="FAO-56" /></div>
      {!d ? <Spinner text="Calculating…" /> : !today.water.monthly_mm ? <div className="err">No climate for this location yet, so water need cannot be calculated.</div> : <>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 4, height: 130, borderBottom: '1.5px solid #D5DFDB' }}>
          {today.water.monthly_mm.map((v: number, k: number) => {
            const b = best && best.id !== 'current' ? best.water.monthly_mm[k] : null
            return <div key={k} style={{ flex: 1, height: '100%', position: 'relative' }} title={`${MONTH_L[k]}: today ${Math.round(v)} mm${b != null ? `, ${best.label} ${Math.round(b)} mm` : ''}`}>
              <span className="an" style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height: `${(v / maxM) * 120}px`, background: '#CBD5D1', borderRadius: '4px 4px 0 0' }} />
              {b != null && <span className="an" style={{ position: 'absolute', left: '25%', right: '25%', bottom: 0, height: `${(b / maxM) * 120}px`, background: C.water, borderRadius: '3px 3px 0 0' }} />}
            </div>
          })}
        </div>
        <div style={{ display: 'flex', gap: 4 }}>{MONTH_L.map((m, k) => <span key={k} style={{ flex: 1, textAlign: 'center', fontSize: 10.5, fontWeight: 700, color: clim[k]?.heavy_rain ? C.water : C.faint }}>{m}</span>)}</div>
        <div className="row" style={{ gap: 14, fontSize: 11.5, color: C.mut }}><span className="row" style={{ gap: 5 }}><span style={{ width: 14, height: 10, background: '#CBD5D1', borderRadius: 3 }} />Today</span>{best && best.id !== 'current' && <span className="row" style={{ gap: 5 }}><span style={{ width: 8, height: 10, background: C.water, borderRadius: 2 }} />{best.label}</span>}<span style={{ marginLeft: 'auto' }}>Blue months = heavy rain</span></div>
      </>}
    </section>
    {clim.length === 12 && <section className="card">
      <div className="between"><div><div className="eb">Rain and evaporation</div><div className="ct">Average month at this field</div></div><Tag k="observed" text="NASA POWER" /></div>
      <LineChart labels={MONTH_L} unit="mm" height={140} series={[{ name: 'Rain', color: C.water, values: clim.map(c => c.rain_mm) }, { name: 'Evaporation (ET0)', color: '#B5523A', values: clim.map(c => c.et0_mm), dashed: true }]} />
      <div className="row" style={{ gap: 14, fontSize: 11.5, color: C.mut }}><span className="row" style={{ gap: 5 }}><span style={{ width: 14, height: 3, background: C.water }} />Rain</span><span className="row" style={{ gap: 5 }}><span style={{ width: 14, height: 0, borderTop: '2px dashed #B5523A' }} />Evaporation (FAO-24)</span></div>
      <span className="muted">When the dashed line is above the blue line, crops need watering.</span>
    </section>}
  </>)
}

/* ------------------------------------------------------------------ FUTURE */
function Future({ p, loc, scen, scenario }: any) {
  const [stressE, setStressE] = useState<api.Res<any> | null>(null)
  const [twin, setTwin] = useState<api.Res<any> | null>(null)
  const [yi, setYi] = useState(2)
  const [twinOpen, setTwinOpen] = useState<number | null>(0)
  useEffect(() => { if (loc) { setTwin(api.cached.twin(loc.latitude, loc.longitude, scenario)); api.climateTwin(loc.latitude, loc.longitude, scenario).then(r => { if (r.source === 'live') setTwin(r) }) } }, [loc?.farm_id, scenario])
  useEffect(() => {
    if (!p?.current_rotation?.length) return
    const ctl = new AbortController()
    setStressE(null)
    const budget = p.irrigation?.budget_mm_per_season ?? 0
    const ens2 = scen?.data?.ensemble?.find((e: any) => e.id === scenario)?.values
    const fdt = ens2 && ens2.length > 1 ? +(ens2[ens2.length - 1].temperatureC.mean - ens2[0].temperatureC.mean).toFixed(2) : 1.5
    const SC: [string, string, api.PlanOpts][] = [['base', 'Today', {}], ['hot', '+2 °C', { temperature_change_c: 2 }], ['dry', '20% less rain', { rainfall_change_pct: -20 }], ['water', 'Half the water', { water_budget_mm: budget / 2 }], ['future', '2050s', { temperature_change_c: Math.max(fdt, 0.5) + 0.8, rainfall_change_pct: -10 }]]
    api.plans(p.farm_id, {}, 'base', ctl.signal).then(async r0 => {
      const base = r0.data
      if (ctl.signal.aborted) return
      if (!base) { setStressE({ data: null, source: 'none' }); return }
      // add the plans the engine itself picks for a hotter / 2050s farm, so the stress test can offer a way out
      const gens = await Promise.all([api.plans(p.farm_id, SC[1][2], 'genhot', ctl.signal), api.plans(p.farm_id, SC[4][2], 'genfuture', ctl.signal)])
      const rotations: string[][] = base.plans.slice(1).map((x: any) => x.rotation)
      for (const g of gens) { const b = g.data?.plans?.find((x: any) => x.id === g.data.best_plan_id && x.feasible && x.id !== 'current'); if (b && !rotations.some(r => r.join() === b.rotation.join())) rotations.push(b.rotation) }
      const res = await Promise.all(SC.map(([k, , o]) => api.plans(p.farm_id, { ...o, rotations }, 's' + k, ctl.signal)))
      if (ctl.signal.aborted) return
      const plansRows = (res[0].data ?? base).plans
      const rows: any[] = plansRows.map((pl: any, k: number) => ({ id: pl.id, label: k > base.plans.length - 1 ? `${pl.label} (heat-ready)` : pl.label, rotation: pl.rotation, cells: res.map((r, j) => {
        const q = r.data?.plans?.find((x: any) => x.rotation.join() === pl.rotation.join())
        const ok = !!q?.feasible, best = r.data?.best_plan_id === q?.id && ok
        return { ok, best, tip: `${pl.label} · ${SC[j][1]}: ${q ? (q.feasible ? 'works' : q.failed_constraints.map((f: any) => f.message).join(' ')) : 'not tested'}` }
      }) }))
      const cols = SC.map(([k, l]) => ({ key: k, label: k === 'future' ? '2050s (estimate)' : l }))
      const publish = (cols: any[], rows: any[], src: api.Source, m5: any, rescue: any) => {
        const nC = cols.length, futureIdx = cols.findIndex(c => c.key === 'future' || c.key === 'm5future')
        const passes = rows.map((r: any) => [r, r.cells.filter((c: any) => c.ok).length] as const).sort((a: any, b: any) => b[1] - a[1])
        const tough = passes[0][0], todayRow = rows[0]
        const todayFailsAt = cols.filter((_, j) => !todayRow.cells[j].ok).map(x => x.label)
        const fut = rows.find((r: any) => r.cells[futureIdx]?.best) ?? rows.find((r: any) => r.cells[futureIdx]?.ok)
        const path = [
          { when: 'Now', act: tough.id === 'current' ? 'Keep your rotation' : `Switch to ${tough.label}: ${rot(tough.rotation)}`, why: `It works in ${passes[0][1]} of ${nC} situations; today's rotation works in ${todayRow.cells.filter((c: any) => c.ok).length}.`, color: C.deep },
          { when: 'Each year', act: 'Cover bare soil in heavy-rain months', why: 'Sow a cover crop or leave residue in the bare months shown in Plans.', color: C.teal },
          { when: 'If dry years', act: todayFailsAt.some(l => /water|rain/.test(l)) ? 'Store water: add a tank or drip line' : 'Keep the same plan', why: todayFailsAt.length ? `Today's rotation fails with: ${todayFailsAt.join(', ')}.` : 'Your plan held up in every dry test.', color: C.water },
          { when: '2030s+', act: fut ? `Move to ${fut.label} as the climate warms` : 'No plan passes the 2050s test: plan for more water', why: m5 ? `Tested on NASA NEX-GDDP-CMIP6 2041–2060 (${scenario === 'ssp370' ? 'SSP3-7.0' : 'SSP2-4.5'}), via M5.` : 'Best plan under the 2050s-like estimate (warmer, 10% less rain).', color: '#A0602A' },
        ]
        const n = rows.filter((r: any) => r.cells.every((c: any) => c.ok)).length
        setStressE({ source: src, data: { cols, rows, path, m5, rescue, head: `${n} of ${rows.length} plans work in every situation. Toughest: ${tough.label} (${passes[0][1]} of ${nC}).` } })
      }
      publish(cols, rows, res[0].source, null, null)
      // M5: same plans on NASA CMIP6 2041-2060 climate, with full and half water
      if (!loc || !p.field_area_ha) return
      const m5Rots = rows.map((r: any, k: number) => ({ id: `r${k}`, crops: r.rotation }))
      const st = await api.stressTest(loc.latitude, loc.longitude, scenario, { rotations: m5Rots, soil_ph: p.soil?.ph ?? null, field_area_ha: p.field_area_ha, priorities: api.BALANCED, prices_rs_per_kg: p.prices_rs_per_kg ?? undefined, costs_rs_per_ha: p.costs_rs_per_ha ?? undefined },
        Math.round((p.irrigation?.budget_mm_per_season ?? 0) * p.field_area_ha * 10), `${p.farm_id}|${scenario}`, ctl.signal)
      if (ctl.signal.aborted || !st.data?.scenarios) return
      const scn = (id: string) => st.data.scenarios.find((x: any) => x.scenario_id === id)
      const mk = (id: string, label: string) => {
        const sc = scn(id); if (!sc) return null
        const bestId = sc.m2_ranking?.find((rid: string) => sc.rotations[rid]?.feasible)
        return { label, cells: rows.map((r: any, k: number) => { const o = sc.rotations[`r${k}`]; return { ok: !!o?.feasible, best: bestId === `r${k}`, tip: `${r.label} · ${label}: ${o ? (o.feasible ? 'works' : o.failed_constraints.map((f: any) => f.message).join(' ')) : 'not tested'}` } }) }
      }
      const f1 = mk('projected_future', '2050s · NASA'), f2 = mk('future_restricted_irrigation', '2050s, half water')
      if (!f1) return
      const keep = cols.map((c, j) => [c, j] as const).filter(([c]) => c.key !== 'future')
      const cols2 = [...keep.map(([c]) => c), { key: 'm5future', label: f1.label }, ...(f2 ? [{ key: 'm5half', label: f2.label }] : [])]
      const rows2 = rows.map((r: any, k: number) => ({ ...r, cells: [...keep.map(([, j]) => r.cells[j]), f1.cells[k], ...(f2 ? [f2.cells[k]] : [])] }))
      const rescue = await api.rescue(st.data, ctl.signal)
      if (ctl.signal.aborted) return
      const d = st.data.monthly_climate_differences_vs_historical ?? []
      const m5 = { source: st.source, dT: d.length ? +(d.reduce((a: number, x: any) => a + x.temperature_change_c, 0) / d.length).toFixed(2) : null,
        dP: d.length ? Math.round(d.reduce((a: number, x: any) => a + x.precipitation_change_mm, 0)) : null }
      publish(cols2, rows2, res[0].source, m5, rescue.data ? { data: rescue.data, rows } : null)
    })
    return () => ctl.abort()
  }, [p?.farm_id, p?.irrigation?.budget_mm_per_season, JSON.stringify(p?.priorities), JSON.stringify(p?.prices_rs_per_kg), scenario, !!scen?.data, loc?.farm_id])
  const s = scen?.data
  const ens = s?.ensemble?.find((e: any) => e.id === scenario)
  const vals: any[] = ens?.values ?? []
  const t0 = vals[0]?.temperatureC?.mean, t2 = vals[vals.length - 1]?.temperatureC?.mean
  const dT = t0 != null && t2 != null ? +(t2 - t0).toFixed(2) : null
  const v = vals[Math.min(yi, vals.length - 1)]
  const last = vals[vals.length - 1], spread = last?.temperatureC?.maximum != null ? +(last.temperatureC.maximum - last.temperatureC.minimum).toFixed(1) : null
  return (<>
    <div><div className="eb">Farm time machine</div><h1 className="h1" style={{ marginTop: 6 }}>Your farm, <span>later.</span></h1></div>
    <Hero eyebrow={`Projection · ${nice(loc?.name)}`} badges={spread != null ? [`Confidence: ${spread < 1 ? 'High' : spread < 2 ? 'Medium' : 'Low'}`] : undefined} title={dT == null ? (scen && !s ? 'Projections not\nloaded yet.' : 'Loading the\nprojections…') : dT > 0 ? `Warmer by\n${vals[vals.length - 1].year}.` : `Little change\nby ${vals[vals.length - 1].year}.`}
      sub={dT == null ? (scen && !s ? 'NASA projections for this field have not been fetched yet. Keep the backend running with internet; they load in the background.' : undefined) : `${dT > 0 ? '+' : ''}${dT} °C from ${vals[0].year} to ${vals[vals.length - 1].year} (${ens.label}, ${vals[0].contributingModels?.length ?? ''}-model average). Models agree within ${spread} °C, so confidence is ${spread != null && spread < 1 ? 'high' : spread != null && spread < 2 ? 'medium' : 'low'}. Regional, not exact for your field.`} />
    <div className="worst"><Icon d="M12 3l9 16H3z M12 10v4 M12 17h.01" c={C.red} s={16} /><span><b>Worst case shown:</b> higher emissions (SSP3-7.0). If your plan works here, it works in milder futures too.</span></div>
    <section className="card">
      <div className="between"><div><div className="eb">Average temperature</div><div className="ct">Projected, with model spread</div></div>{scen && <SourceTag s={scen.source} what="CMIP6" />}</div>
      {!scen ? <Spinner text="Fetching NASA NEX-GDDP-CMIP6 (can take a minute)…" /> : !vals.length ? <div className="err">No projections available{scen.error ? `: ${scen.error}` : ''}.</div> : <>
        <LineChart labels={vals.map(x => String(x.year))} unit="°C" selected={yi} onPick={setYi}
          series={[{ name: 'T', color: '#795E22', values: vals.map(x => x.temperatureC.mean), dashed: true, band: vals.map(x => [x.temperatureC.minimum, x.temperatureC.maximum] as [number, number]) }]} />
        {v && <div className="kpis" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <Kpi v={`${v.temperatureC.mean.toFixed(1)}`} unit="°C" l={`Temperature ${v.year} (models ${v.temperatureC.minimum.toFixed(1)}–${v.temperatureC.maximum.toFixed(1)})`} />
          <Kpi v={Math.round(v.rainfallMm.mean).toLocaleString()} unit="mm" l={`Rain ${v.year} (models ${Math.round(v.rainfallMm.minimum)}–${Math.round(v.rainfallMm.maximum)})`} />
        </div>}
        <span className="faint">{s.provenance?.gridResolution} grid. Spread = highest minus lowest model, not a probability.</span>
      </>}
    </section>
    <section className="card">
      <div className="between"><div><div className="eb">Climate twin · 2041–2060</div><div className="ct">Places that feel like your future</div></div>{twin && <SourceTag s={twin.source} what="NASA POWER" />}</div>
      {!twin ? <Spinner text="Matching climates…" /> : !twin.data ? <div className="err">Climate twin unavailable{twin.error ? `: ${twin.error}` : ''}.</div> : <>
        <div className="twinhead"><b>By the 2050s, {nice(p?.name)} will feel like {fixText(twin.data.analogs[0].location.name).split(',')[0]} does today.</b><span>Tap a place to see its farms, how the climate compares, and which rotation keeps your farm feeding you and paying in that climate.</span></div>
        {twin.data.analogs.map((a: any, k: number) => {
          const open = twinOpen === k, name = fixText(a.location.name)
          const mc: any[] = a.monthly_comparison ?? []
          return <div key={a.location.id} className={'twin' + (open ? ' on' : '')}>
            <button className="twinrow" onClick={() => setTwinOpen(open ? null : k)} aria-expanded={open}>
              <span className="rank">{k + 1}</span>
              <span style={{ flex: 1, textAlign: 'left' }}><b style={{ fontSize: 15 }}>{name}</b><br />
                <span className="muted">Temperature within {a.temperature_rmse_c.toFixed(1)} °C · rain within {Math.round(a.precipitation_mae_mm_per_month)} mm a month</span></span>
              <span style={{ fontSize: 18, color: C.teal }}>{open ? '–' : '+'}</span>
            </button>
            {open && <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 10 }}>
              <TwinCompare p={p} loc={loc} a={a} name={name} hist={twin.data.historical} />
              {mc.length === 12 && <>
                <div className="row" style={{ gap: 14, fontSize: 12, fontWeight: 700 }}>
                  <span className="row" style={{ gap: 6, color: '#795E22' }}><span style={{ width: 14, height: 3, background: '#795E22' }} />Your field, 2050s</span>
                  <span className="row" style={{ gap: 6, color: C.teal }}><span style={{ width: 14, height: 3, background: C.teal }} />{name.split(',')[0]} today</span>
                </div>
                <LineChart labels={['J', 'F', 'M', 'A', 'M ', 'J ', 'J  ', 'A ', 'S', 'O', 'N', 'D']} unit="°C" height={130}
                  series={[{ name: 'Yours', color: '#795E22', values: mc.map(m => +m.future_t_c.toFixed(1)), dashed: true }, { name: 'Twin', color: C.teal, values: mc.map(m => +m.candidate_t_c.toFixed(1)) }]} />
              </>}
              <span className="muted">Same climate does not mean the same crops will grow: soil, pests and markets differ.</span>
            </div>}
          </div>
        })}
        {twin.source === 'cached' && <span className="faint">{Math.abs(twin.data.field.latitude - loc.latitude) < 0.01 && Math.abs(twin.data.field.longitude - loc.longitude) < 0.01 ? 'Saved M5 run for this field (NASA POWER + NEX-GDDP-CMIP6). Live run takes several minutes.' : `Saved M5 example for a point near ${twin.data.field.latitude}, ${twin.data.field.longitude}.`}</span>}
      </>}
    </section>
    <section className="card">
      <div className="between"><div><div className="eb">Stress test</div><div className="ct">Which plans still work?</div></div>{stressE && <SourceTag s={stressE.source} what="M2 engine" />}</div>
      {!stressE ? <Spinner text="Re-running every plan in 5 situations…" /> : !stressE.data ? <div className="err">Stress test unavailable.</div> : <>
        <span className="muted" style={{ fontSize: 14 }}>{stressE.data.head}</span>
        <StressPick data={stressE.data} />
        <span className="faint">{stressE.data.m5 ? `2050s columns: NASA NEX-GDDP-CMIP6 2041–2060 climate for this field, run by M5 through the same plan engine. Today and 2050s use different NASA products, so compare plans within a column.` : 'Fetching the NASA 2050s projection from M5… the 2050s column is an estimate until it arrives.'}</span>
      </>}
    </section>
    {stressE?.data?.rescue && <section className="card">
      <div className="between"><div><div className="eb">Rescue shortlist · M5</div><div className="ct">Most robust plans first</div></div><Tag k="modelled" text="M5" /></div>
      <div className="list">{[...stressE.data.rescue.data.candidates].sort((a: any, b: any) => b.scenarios_passed - a.scenarios_passed || stressE.data.rescue.rows[+b.rotation_id.slice(1)].cells.filter((c: any) => c.ok).length - stressE.data.rescue.rows[+a.rotation_id.slice(1)].cells.filter((c: any) => c.ok).length).slice(0, 3).map((c: any, k: number) => {
        const r = stressE.data.rescue.rows[+c.rotation_id.slice(1)]
        return <div key={c.rotation_id}><span className="rnum">{k + 1}</span><span style={{ flex: 1 }}><b>{r?.label}</b> · {rot(r?.rotation ?? [])}<br /><span className="faint">{c.failed_scenarios.length ? `Fails: ${c.failed_scenarios.map((f: any) => ({ historical_baseline: 'today', projected_future: '2050s', historical_restricted_irrigation: 'half water today', future_restricted_irrigation: 'half water in 2050s' } as any)[f.scenario_id] ?? f.scenario_id).join(', ')}` : 'Passes every M5 test'}</span></span><b style={{ color: c.scenarios_passed === c.scenario_count ? '#276146' : C.ink }}>{c.scenarios_passed}/{c.scenario_count}</b></div>
      })}</div>
      <span className="faint">{fixText(stressE.data.rescue.data.explanation)}</span>
    </section>}
    {stressE?.data && <section className="card">
      <div className="between"><div><div className="eb">Path to the 2050s</div><div className="ct">What to do, and when</div></div><Tag k="pending" text="Proposed" /></div>
      <div>{stressE.data.path.map((st: any, k: number) => <div key={k} style={{ display: 'grid', gridTemplateColumns: '64px 16px 1fr', gap: 8 }}>
        <b style={{ fontSize: 13, color: C.deep }}>{st.when}</b>
        <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}><span style={{ width: 12, height: 12, borderRadius: 6, marginTop: 3, background: st.color }} />{k < stressE.data.path.length - 1 && <span style={{ flex: 1, width: 1.5, background: C.line }} />}</span>
        <span style={{ display: 'flex', flexDirection: 'column', gap: 3, paddingBottom: 16 }}><b style={{ fontSize: 14 }}>{st.act}</b><span className="muted">{st.why}</span></span>
      </div>)}</div>
      <span className="faint">Built from the stress test above. A plan to discuss, not a forecast.</span>
    </section>}
  </>)
}

/* ------------------------------------------------------------------ ASK + PASSPORT */
const FAQ: [RegExp, string][] = [
  [/how (does|do) (it|this|cropcompass|the app) work|what (is|does) cropcompass|what are you doing|what do you do/i, 'CropCompass helps you choose a crop rotation that still feeds you and pays in a changing climate.\n1. Your field: you add where it is, what you grow and when, your water and soil.\n2. NASA data: we read rain and temperature for your field from NASA POWER (2021 to now) and NASA climate projections for the 2050s.\n3. Plans: for each possible rotation we work out water need, whether each crop suits the season, soil health and profit, and rank them.\n4. Future: we test every plan in a hotter, drier, worst-case future and find places in the world whose climate today is like yours tomorrow.\n5. Evidence: every number shows where it came from and what is still missing.'],
  [/where.*data|which data|data source|nasa/i, 'Climate history: NASA POWER (daily weather from satellites and models, about 50 km grid). Future: NASA NEX-GDDP-CMIP6, 5 climate models, worst-case SSP3-7.0. Crop water use: FAO-56. Crop temperature ranges: FAO ECOCROP. Yields: Statistics Mauritius. Satellite pictures: Sentinel-2 and Esri.'],
  [/shap|explain|why.*score|how.*score/i, 'Each plan gets a score out of 100 from four parts: water use, soil care, climate fit and profit. SHAP (explainable AI) shows how much each part pushes a plan above or below the average plan, so you can see exactly why it ranks where it does.'],
  [/confidence|how sure|accurate|trust/i, 'Confidence goes down when inputs are missing or estimated: an untested soil pH, a soil type from the map, example prices, or two plans with almost the same score. Fill those in and confidence goes up.'],
  [/twin/i, 'A climate twin is a real place whose climate today matches what your field is expected to feel like in the 2050s. Seeing how farms there look and what grows there helps you prepare now.'],
  [/stress|worst/i, 'The stress test re-runs every plan in tougher situations: +2 °C, 20% less rain, half the water, and the NASA 2050s worst case. A plan that keeps working in most of them is a safer choice.'],
]

function Ask({ close, analysis, analysing, p, planRes }: any) {
  const [msgs, setMsgs] = useState<{ me: boolean; text: string; extra?: string }[]>([])
  const [q, setQ] = useState(''), [busy, setBusy] = useState(false)
  const bundle = analysis?.data?.bundle
  const send = async (text: string) => {
    if (!text.trim()) return
    const faq = FAQ.find(([re]) => re.test(text))
    if (faq) { setMsgs(m => [...m, { me: true, text }, { me: false, text: faq[1], extra: 'About CropCompass' }]); setQ(''); return }
    const pd = planRes?.data
    if (pd && /\b(plan|plans|best|switch|rotation|harvest|income|money|earn|price|profit|water need|how much water)\b/i.test(text)) {
      const best = pd.plans.find((x: any) => x.id === pd.best_plan_id), today = pd.plans[0]
      const money = /harvest|income|money|earn|price|profit/i.test(text), water = /water/i.test(text)
      const lines = money ? pd.plans.map((x: any) => `${x.label} (${rot(x.rotation)}): profit about ${rs(x.income?.profit_rs)} a year (harvest ${rs(x.income?.harvest_value_rs)} − costs ${rs(x.income?.cost_rs)}).`)
        : water ? pd.plans.map((x: any) => `${x.label}: ${x.water.peak_season_mm != null ? Math.round(x.water.peak_season_mm) : '?'} mm in its driest season, ${x.water.total_mm != null ? Math.round(x.water.total_mm) : '?'} mm a year (you can give ${p.irrigation.budget_mm_per_season ?? 0} mm a season).`)
        : [`Best for you: ${best.label}, ${rot(best.rotation)} (score ${Math.round((best.score ?? 0) * 100)} vs ${Math.round((today.score ?? 0) * 100)} today).`, ...best.reasons.slice(0, 4)]
      setMsgs(m => [...m, { me: true, text }, { me: false, text: lines.join('\n'), extra: `From the M2 plan engine · ${money ? 'example prices unless you entered yours · ' : ''}NASA POWER climate` }]); setQ('')
      return
    }
    if (!bundle) { setMsgs(m => [...m, { me: true, text }, { me: false, text: analysing ? 'Still reading your farm data, try again in a moment.' : 'I could not load your farm analysis yet. Try again in a moment.' }]); setQ(''); return }
    setMsgs(m => [...m, { me: true, text }]); setQ(''); setBusy(true)
    const r = await api.ask(text, bundle)
    setBusy(false)
    setMsgs(m => [...m, { me: false, text: r.data?.answer ?? `The assistant is not reachable (${r.error}).`, extra: r.data ? [r.data.mode === 'refused' ? 'Refused: no evidence for that' : `${r.data.cited_evidence?.length ?? 0} evidence records cited`, ...(r.data.limitations ?? []).slice(0, 1)].join(' · ') : undefined }])
  }
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs.length, busy])
  return (<div className="chatpanel" role="dialog" aria-label="Ask CropCompass">
    <header><span className="logo" style={{ width: 30, height: 30, borderRadius: 9 }}><Icon d={I.leaf} c="#fff" s={16} /></span><div style={{ flex: 1 }}><b>Ask CropCompass</b><small>Anything about how it works, your plans, water or climate</small></div>
      <button className="round" aria-label="Close chat" onClick={close}><Icon d="M6 6l12 12M18 6L6 18" s={16} /></button></header>
    <div className="chatbody">
      <div className="bubble" style={{ alignSelf: 'flex-start', background: '#fff', border: `1px solid ${C.line}` }}>Hi {USER}. Ask me anything, for example how CropCompass works, where the data comes from, or what to plant next season.</div>
      {msgs.map((m, k) => <div key={k} className="bubble" style={{ whiteSpace: 'pre-line', alignSelf: m.me ? 'flex-end' : 'flex-start', background: m.me ? C.deep : '#fff', color: m.me ? '#fff' : C.ink, border: m.me ? 0 : `1px solid ${C.line}` }}>{m.text}{m.extra && <div className="faint" style={{ marginTop: 6 }}>{m.extra}</div>}</div>)}
      {busy && <Spinner text="Thinking…" />}
      <div ref={end} />
    </div>
    <div className="chatin">
      <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && send(q)} placeholder="Ask anything…" aria-label="Question" />
      <button className="round" style={{ width: 42, height: 42, background: C.deep, border: 0 }} aria-label="Send" onClick={() => send(q)}><Icon d={I.send} c="#fff" s={18} /></button>
    </div>
  </div>)
}

function Passport({ close, analysis, analysing, p, rerun, planRes }: any) {
  const a = analysis?.data
  const pass = a?.passport, bs = a?.blind_spot_report
  const mod = a?.modules ?? {}
  return (<>
    <SheetHead eyebrow="Evidence passport" title="Where every number comes from" close={close} />
    <div className="body">
      {analysing && <Spinner text="Running the full analysis (M1 → M2 → M3 → M5 → M4)… this can take a minute." />}
      {analysis?.source === 'cached' && <div className="err">Backend offline: showing a cached example analysis, not {nice(p?.name)}. Start the backend and tap Run again.</div>}
      {a && <>
        <section className="hero" style={{ background: C.deep }}>
          <div className="e"><i /><b>{(pass?.recommendation_status ?? '').replace(/_/g, ' ').toUpperCase()}</b></div>
          <div className="t" style={{ fontSize: 20, lineHeight: '25px' }}>{rot(pass?.rotation)}</div>
          <div className="s">{pass?.evidence?.length ?? 0} evidence records · {bs?.blind_spots?.length ?? 0} blind spots</div>
        </section>
        <div className="kpis" style={{ gridTemplateColumns: 'repeat(4,1fr)' }}>{['M1', 'M2', 'M3', 'M5'].map(m => <Kpi key={m} v={m} l={(mod[m]?.status ?? '–').replace('_', ' ')} color={mod[m]?.status === 'ok' ? C.teal : mod[m]?.status === 'partial' ? C.gold : C.faint} />)}</div>
        <section className="card"><div className="ct">Blind spots</div>
          <div className="list">{(bs?.blind_spots ?? []).map((b: any) => <div key={b.code}><span className="dot" style={{ background: b.severity === 'warning' ? C.red : b.severity === 'info' ? '#A9BAB5' : C.gold }} /><span style={{ flex: 1 }}>{b.message}{b.farmer_action && <><br /><b style={{ fontSize: 12 }}>{b.farmer_action}</b></>}</span></div>)}</div>
        </section>
        <section className="card"><div className="ct">Evidence</div>
          <div className="list">{(pass?.evidence ?? []).slice(0, 30).map((e: any) => <div key={e.id}><span className="dot" style={{ background: e.status === 'supported' ? C.teal : C.gold }} /><span style={{ flex: 1 }}>{e.claim}{e.subject ? ` · ${crop(e.subject)}` : ''}<br /><span className="faint">{e.value != null ? `${typeof e.value === 'object' ? JSON.stringify(e.value) : e.value}${e.unit ? ' ' + e.unit : ''} · ` : ''}{e.provenance?.source_module} · {e.provenance?.dataset ?? e.provenance?.method ?? ''}</span></span></div>)}</div>
        </section>
        <section className="card"><div className="ct">Limitations</div>
          <div className="list">{(pass?.limitations ?? []).map((l: any, k: number) => <div key={k}><span className="dot" style={{ background: "#A9BAB5" }} /><span style={{ flex: 1 }}>{typeof l === "string" ? l : l.text}{l?.source_module ? <span className="faint"> · {l.source_module}</span> : null}</span></div>)}</div>
        </section>
      </>}
      {planRes?.data && <section className="card"><div className="ct">How plans are scored (M2 engine)</div>
        <div className="list">{planRes.data.assumptions.map((x: string, k: number) => <div key={k}><span className="dot" style={{ background: C.teal }} /><span style={{ flex: 1 }}>{x}</span></div>)}</div>
        <div className="list">{planRes.data.sources.map((x: any) => <div key={x.url}><span className="dot" style={{ background: '#A9BAB5' }} /><a href={x.url} target="_blank" rel="noreferrer" style={{ flex: 1, color: C.teal }}>{x.name}</a></div>)}</div>
      </section>}
      <div className="row"><button className="btn light" style={{ flex: 1 }} disabled={analysing} onClick={rerun}>{analysing ? 'Running…' : 'Run again'}</button><button className="btn" style={{ flex: 1 }} onClick={() => window.print()}>Save as PDF</button></div>
      <span className="faint">CropCompass helps you explore choices. It is not a guarantee of harvest or profit.</span>
    </div>
  </>)
}

export type { Source }
