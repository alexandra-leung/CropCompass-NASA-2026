import { Fragment, useEffect, useRef, useState } from 'react'
import * as api from './api'
import type { Source } from './api'
import { C, Hero, I, Icon, Kpi, LineChart, SourceTag, Spinner, Tag } from './ui'
import { CropPic } from './crops'
import { SatelliteField, SatellitePlace } from './satellite'

type Tab = 'home' | 'fields' | 'plans' | 'water' | 'future'
type Sheet = null | { kind: 'field' } | { kind: 'add' } | { kind: 'ask' } | { kind: 'passport' }

const USER = 'Sanjana'
const CROP_NAMES: Record<string, string> = { maize: 'Maize', tomato: 'Tomato', onion: 'Onion', cabbage: 'Cabbage', cowpea: 'Cowpea', groundnut: 'Groundnut', sweet_potato: 'Sweet potato' }
const crop = (id: string) => CROP_NAMES[id] ?? id
// Repair text that was decoded with the wrong character set upstream (e.g. "RÃ©union" -> "Réunion").
const fixText = (t?: string) => { if (!t || !/[ÃÂ]/.test(t)) return t ?? ''; try { return decodeURIComponent(escape(t)) } catch { return t } }
const nice = (n?: string) => (n ?? '').replace(/ Field \d+$/, '')
const rot = (r?: string[] | null) => (r && r.length ? r.map(crop).join(' → ') : 'Not entered')
const TEXTURES: [string, string][] = [['sandy_loam', 'Sandy loam'], ['loam', 'Loam'], ['clay_loam', 'Clay loam'], ['clay', 'Clay'], ['unknown', "Don't know"]]
const WATER: [string, string][] = [['rain_only', 'Rain only'], ['tank', 'Tank or pond'], ['borehole', 'Borehole'], ['irrigation_scheme', 'Irrigation scheme']]
const MONTH_L = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
const SCEN: [string, string][] = [['ssp245', 'Middle path · SSP2-4.5'], ['ssp370', 'Higher emissions · SSP3-7.0']]
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
  const [scenario, setScenario] = useState('ssp245')

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

  const planKey = p ? [p.farm_id, p.irrigation?.budget_mm_per_season, JSON.stringify(p.priorities), JSON.stringify(p.prices_rs_per_kg ?? null), (p.current_rotation || []).join(), p.soil?.ph].join('|') : ''
  const loadPlans = () => { if (!p?.current_rotation?.length) return; setPlanRes(null); api.plans(p.farm_id).then(setPlanRes) }
  useEffect(() => { loadPlans() }, [planKey])
  const savePrices = async (pr: any) => { try { setFarm({ data: await api.patchFarm(p.farm_id, { prices_rs_per_kg: pr }), source: 'live' }); return true } catch { return false } }
  const savePriorities = async (w: any) => { try { setFarm({ data: await api.patchFarm(p.farm_id, { priorities: w }), source: 'live' }) } catch { /* offline */ } }

  const runAnalysis = async () => {
    if (!p || analysing) return
    setAnalysing(true)
    const ctx = { farm_id: p.farm_id, location_id: p.location_id, soil_ph: p.soil?.ph ?? null, field_area_ha: p.field_area_ha, irrigation_budget_m3: p.irrigation_budget_m3, current_rotation: p.current_rotation, source: 'M3' }
    setAnalysis(await api.analyze(ctx, scenario === 'ssp245' ? 'ssp245' : 'ssp370'))
    setAnalysing(false)
  }
  const needAnalysis = () => { if (!analysis && !analysing) runAnalysis() }

  const farmList: any[] = farms.data?.farms ?? []
  const loc = farmList.find(f => f.farm_id === farmId)

  return (
    <div className="phone">
      <div className="top">
        <span className="logo"><Icon d={I.leaf} c="#fff" s={20} /></span>
        <span className="brand"><span style={{ color: C.deep }}>crop</span><span style={{ color: C.teal }}>compass</span></span>
        <button className="iconbtn" aria-label="Ask CropCompass" onClick={() => { setSheet({ kind: 'ask' }); needAnalysis() }}><Icon d={I.chat} /></button>
        <button className="iconbtn" aria-label="Evidence passport" onClick={() => { setSheet({ kind: 'passport' }); needAnalysis() }}><Icon d={I.doc} />{(p?.validation?.missing?.length ?? 0) > 0 && <span className="dotbadge" />}</button>
      </div>

      <main>
        {tab === 'home' && <Home p={p} loc={loc} farms={farmList} history={history} openField={() => setSheet({ kind: 'field' })} farmsSrc={farms.source} goFields={() => setTab('fields')} planRes={planRes} goPlans={() => setTab('plans')} />}
        {tab === 'fields' && <Fields farms={farmList} src={farms.source} open={(id: string) => { setFarmId(id); setSheet({ kind: 'field' }) }} add={() => setSheet({ kind: 'add' })} plans={(id: string) => { setFarmId(id); setTab('plans') }} />}
        {tab === 'plans' && <Plans p={p} planRes={planRes} onPriorities={savePriorities} refresh={loadPlans} onPrices={savePrices} />}
        {tab === 'water' && <Water p={p} planRes={planRes} onSaved={(np: any) => setFarm({ data: np, source: 'live' })} />}
        {tab === 'future' && <Future p={p} loc={loc} scen={scen} scenario={scenario} setScenario={setScenario} />}
      </main>

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
            {sheet.kind === 'ask' && <Ask close={() => setSheet(null)} analysis={analysis} analysing={analysing} p={p} planRes={planRes} />}
            {sheet.kind === 'passport' && <Passport close={() => setSheet(null)} analysis={analysis} analysing={analysing} p={p} rerun={runAnalysis} planRes={planRes} />}
          </div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ HOME */
function Home({ p, loc, farms, history, openField, farmsSrc, goFields, planRes, goPlans }: any) {
  const [long, setLong] = useState<api.Res<any> | null>(null), [loadingLong, setLoadingLong] = useState(false)
  useEffect(() => { setLong(null) }, [loc?.farm_id])
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
    <Hero eyebrow={`Farm status · ${nice(loc?.name)}`} title={title} sub={sub} />
    <div className="kpis">
      <Kpi onClick={goFields} v={String(farms.length || '…')} l="Fields" />
      <Kpi onClick={goFields} v={p?.irrigation?.budget_mm_per_season != null ? String(Math.round(p.irrigation.budget_mm_per_season)) : '…'} unit="mm" l={`Water · ${nice(p?.name)}`} />
      <Kpi onClick={goFields} v={m ? `${m.dataCompleteness}` : history && !h ? '–' : '…'} unit={m ? '%' : undefined} l="Climate data" />
    </div>
    {planRes?.data && (() => {
      const pls: any[] = planRes.data.plans, best = pls.find((x: any) => x.id === planRes.data.best_plan_id), today = pls[0]
      return <section className="card">
        <div className="between"><div><div className="eb">Best plan for {nice(p?.name)}</div><div className="ct">{best.id === 'current' ? 'Keep your rotation' : `${best.label}: ${rot(best.rotation)}`}</div></div><SourceTag s={planRes.source} what="M2" /></div>
        <div className="row" style={{ gap: 6 }}>{best.rotation.map((c: string, k: number) => <span key={k} className="row" style={{ gap: 2 }}><CropPic id={c} size={34} />{k < best.rotation.length - 1 && <span className="faint">→</span>}</span>)}</div>
        <span className="muted" style={{ fontSize: 13.5 }}>{best.reasons[0]} Score {Math.round((best.score ?? 0) * 100)} vs {Math.round((today.score ?? 0) * 100)} today.{best.income?.harvest_value_rs ? ` Harvest about ${rs(best.income.harvest_value_rs)} a year.` : ''}</span>
        <button className="btn" onClick={goPlans}>See all plans ›</button>
      </section>
    })()}
    <section className="card">
      <div className="between"><div><div className="eb">Climate history</div><div className="ct">Rain and heat, by year</div></div>{history && <SourceTag s={history.source} what="NASA POWER" />}</div>
      {!history && <Spinner text={`Fetching NASA POWER for ${nice(loc?.name)} (first time can take a minute)…`} />}
      {history && !h && <div className="err">NASA POWER did not answer for {nice(loc?.name)} ({history.error}). The first fetch for a new location can take a minute; tap Home again to retry.</div>}
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
function AddField({ close, created }: any) {
  const [step, setStep] = useState(0)
  const [locs, setLocs] = useState<any[]>([])
  const [crops, setCrops] = useState<any[]>([])
  const [f, setF] = useState<any>({ name: '', location_id: 'pamplemousses-04', area: '0.5', rotation: [] as string[], water_source: 'tank', mm: '150', texture: 'unknown' })
  const [err, setErr] = useState(''), [busy, setBusy] = useState(false)
  useEffect(() => { api.getLocations().then(r => setLocs(r.data?.locations ?? [])); api.getCrops().then(r => setCrops(r.data ?? [])) }, [])
  const titles = ['Where is it?', 'What grows there?', 'Your water', 'Your soil']
  const ok = [f.name.trim().length > 0 && +f.area > 0, f.rotation.length > 0, f.water_source === 'rain_only' || +f.mm >= 0, true][step]
  const submit = async () => {
    setBusy(true); setErr('')
    try {
      const body = {
        name: f.name.trim(), location_id: f.location_id, field_area_ha: +f.area, current_rotation: f.rotation,
        irrigation: { water_source: f.water_source, budget_mm_per_season: f.water_source === 'rain_only' ? 0 : +f.mm },
        soil: f.texture === 'unknown' ? {} : { texture: f.texture, texture_source: 'farmer' },
      }
      const r = await api.createFarm(body); created(r.farm_id)
    } catch (e) { setErr(`Could not save: ${(e as Error).message}. Is the backend running?`) } finally { setBusy(false) }
  }
  return (<>
    <SheetHead eyebrow={`New field · step ${step + 1} of 4`} title={titles[step]} close={close} back={step ? () => setStep(step - 1) : undefined} />
    <div className="body">
      <div style={{ display: 'flex', gap: 4 }}>{[0, 1, 2, 3].map(i => <span key={i} className="an" style={{ flex: 1, height: 5, borderRadius: 3, background: i <= step ? C.teal : '#D5DFDB' }} />)}</div>
      {step === 0 && <>
        <label className="field">Field name<input value={f.name} placeholder="Behind the house" onChange={e => setF({ ...f, name: e.target.value })} /></label>
        <span className="eb">Nearest climate location</span>
        {locs.map(l => <button key={l.location_id} className="fcard" onClick={() => setF({ ...f, location_id: l.location_id })} style={{ border: f.location_id === l.location_id ? `2px solid ${C.deep}` : undefined }}>
          <span className="in"><b>{nice(l.name)}</b><span className="faint">{l.district} · {l.latitude.toFixed(3)}, {l.longitude.toFixed(3)}</span></span></button>)}
        <label className="field">Size (hectares)<input inputMode="decimal" value={f.area} onChange={e => setF({ ...f, area: e.target.value })} /></label>
        <span className="faint">Auto outline from satellite is not available yet; a placeholder outline of this size is saved, and you can redraw it later.</span>
      </>}
      {step === 1 && <>
        <span className="muted">Tap the crops in the order you grew them (last 3 seasons).</span>
        <div className="chips">{crops.map(c => <button key={c.crop_id} className={'chip' + (f.rotation.includes(c.crop_id) ? ' on' : '')} onClick={() => setF({ ...f, rotation: f.rotation.length < 3 ? [...f.rotation, c.crop_id] : f.rotation })}>{crop(c.crop_id)}</button>)}</div>
        <section className="card"><span className="eb">Your rotation</span><b>{rot(f.rotation)}</b>{f.rotation.length > 0 && <button className="chip" onClick={() => setF({ ...f, rotation: [] })}>Clear</button>}</section>
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

/* ------------------------------------------------------------------ PLANS */
const FAM: Record<string, string> = { Poaceae: 'grass family', Fabaceae: 'legume', Solanaceae: 'nightshade', Amaryllidaceae: 'onion family', Brassicaceae: 'cabbage family', Convolvulaceae: 'morning glory' }
const PRESETS: [string, string, Record<string, number>][] = [
  ['water', 'Water', { water: 0.55, soil: 0.15, climate: 0.15, income: 0.15 }],
  ['soil', 'Soil', { water: 0.15, soil: 0.55, climate: 0.15, income: 0.15 }],
  ['climate', 'Climate', { water: 0.15, soil: 0.15, climate: 0.55, income: 0.15 }],
  ['income', 'Income', { water: 0.15, soil: 0.15, climate: 0.15, income: 0.55 }],
  ['balanced', 'Balanced', { water: 0.25, soil: 0.25, climate: 0.25, income: 0.25 }],
]
const presetOf = (pr: any) => { if (!pr) return 'balanced'; const top = ['water', 'soil', 'climate', 'income'].sort((a, b) => (pr[b] ?? 0) - (pr[a] ?? 0)); return (pr[top[0]] ?? 0) - (pr[top[1]] ?? 0) < 0.05 ? 'balanced' : top[0] }
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

function PriceCard({ p, d, onSave }: any) {
  const ids: string[] = Array.from(new Set<string>((d?.plans ?? []).flatMap((x: any) => x.rotation)))
  const [vals, setVals] = useState<Record<string, string>>({})
  const [state, setState] = useState('')
  useEffect(() => { setVals(Object.fromEntries(ids.map(c => [c, String(p.prices_rs_per_kg?.[c] ?? d?.prices_rs_per_kg?.[c] ?? '')]))); setState('') }, [p.farm_id, ids.join()])
  if (!ids.length) return null
  const save = async () => {
    const out: Record<string, number> = {}
    for (const [k, v] of Object.entries(vals)) if (v !== '' && isFinite(+v) && +v >= 0) out[k] = +v
    setState('Saving…'); setState((await onSave(out)) ? 'Saved · plans updated' : 'Not saved: backend offline')
  }
  return <section className="card">
    <div className="between"><div><div className="eb">Your selling prices</div><div className="ct">Rs per kg, for harvest value</div></div><Tag k={p.prices_rs_per_kg ? 'entered' : 'pending'} text={p.prices_rs_per_kg ? 'You entered' : 'Example prices'} /></div>
    <div className="prices">{ids.map(c => <label key={c}><CropPic id={c} size={26} /><span>{crop(c)}</span><input inputMode="decimal" value={vals[c] ?? ''} onChange={e => setVals({ ...vals, [c]: e.target.value })} /></label>)}</div>
    <div className="row"><span className="faint" style={{ flex: 1 }}>{state || 'Yields: Mauritius averages, Statistics Mauritius 2023–24.'}</span><button className="btn" style={{ minHeight: 38 }} onClick={save}>Save prices</button></div>
  </section>
}

function Plans({ p, planRes, onPriorities, refresh, onPrices }: any) {
  const [i, setI] = useState(0)
  const [step, setStep] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const d = planRes?.data
  const plans: any[] = d?.plans ?? []
  const sel = plans[Math.min(i, Math.max(plans.length - 1, 0))]
  useEffect(() => { setI(0); setStep(null) }, [p?.farm_id])
  useEffect(() => {
    if (step == null || !sel) return
    const t = window.setTimeout(() => setStep(step + 1 < sel.crops.length ? step + 1 : null), 10000)
    return () => window.clearTimeout(t)
  }, [step, sel])
  if (!p) return <Spinner text="Loading farm…" />
  const preset = presetOf(p.priorities)
  const setPreset = async (w: Record<string, number>) => { setBusy(true); await onPriorities(w); setBusy(false) }
  const head = (<>
    <div><div className="eb">Plans for this field</div><h1 className="h1" style={{ marginTop: 6 }}>{nice(p.name)} <span>· season by season</span></h1></div>
    <div className="ctx">
      <span><small>Soil</small><b>{TEXTURES.find(t => t[0] === p.soil.texture)?.[1] ?? 'Unknown'}</b></span>
      <span><small>pH</small><b>{p.soil.ph ?? '?'}</b></span>
      <span><small>Water / season</small><b>{p.irrigation.budget_mm_per_season ?? '?'} mm</b></span>
      <span><small>Crops now</small><b>{rot(p.current_rotation)}</b></span>
    </div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span className="eb">Rank plans by what matters to you</span>
      <div className="seg" style={{ gridTemplateColumns: 'repeat(5,1fr)' }}>{PRESETS.map(([k, l, w]) => <button key={k} className={preset === k ? 'on' : ''} disabled={busy} onClick={() => setPreset(w)}>{l}</button>)}</div>
    </div>
  </>)
  if (!p.current_rotation?.length) return <>{head}<div className="err">Add the crops you grow in Fields to compare plans.</div></>
  if (!planRes || busy) return <>{head}<Spinner text="Comparing plans: water need, suitability, rotation rules…" /></>
  if (!d) return <>{head}<div className="err">The plan engine did not answer ({planRes.error}). <button className="chip" onClick={refresh}>Try again</button></div></>
  const best = plans.find((x: any) => x.id === d.best_plan_id) ?? plans[0]
  const today = plans[0]
  const lab = (x: any) => x.label
  const pct = (v: number | null) => (v == null ? '–' : `${Math.round(v * 100)}`)
  const bd = sel.score_breakdown || {}
  return (<>
    {head}
    <Hero bg={C.deep} eyebrow={`Best for ${nice(p.name)} · ${PRESETS.find(x => x[0] === preset)?.[1]}`}
      title={!plans.some((x: any) => x.feasible) ? 'No plan fits\nyour water yet.' : best.id === 'current' ? 'Your rotation\nis already the best.' : `${lab(best)}: ${rot(best.rotation)}`}
      sub={!plans.some((x: any) => x.feasible) ? `The thriftiest plan needs ${Math.round(Math.min(...plans.map((x: any) => x.water.peak_season_mm ?? 1e9)))} mm of watering in its driest season; you can give ${p.irrigation.budget_mm_per_season ?? 0} mm. Plans are still ranked below; add a tank or set your water in the Water tab.` : best.id === 'current' ? best.reasons[0] : `Score ${pct(best.score)} vs ${pct(today.score)} today.${best.income?.harvest_value_rs ? ` Harvest about ${rs(best.income.harvest_value_rs)} a year (today ${rs(today.income?.harvest_value_rs)}).` : ''} ${best.reasons[0]}`} />
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
      {sel.failed_constraints.map((f: any, k: number) => <div key={k} className="err">{f.message}</div>)}
      <div className="seasons" style={{ gridTemplateColumns: `repeat(${sel.crops.length}, 1fr)` }}>
        {sel.crops.map((s: any, k: number) => {
          const on = step === k, rep = sel.dna.repeated_family_seasons.includes(s.season), [sb, sf, st] = SUIT[s.suitability] ?? SUIT.unknown
          return <div key={k} className={'season' + (on ? ' on' : '') + (step != null && !on ? ' dim' : '')}>
            <span className="faint" style={{ fontWeight: 700 }}>{s.season_label}</span>
            <div className="plot"><span key={on ? 'g' + step : 'n'} className={on ? 'grow' : ''}><CropPic id={s.crop_id} size={58} /></span></div>
            {on && <span className="prog"><i key={'p' + step} /></span>}
            <b>{crop(s.crop_id)}</b>
            <span className="faint">{FAM[s.family] ?? s.family} · {s.months.length} mo</span>
            <span className="pill" style={{ background: s.legume ? '#E8F3EF' : '#F2F6F4', color: s.legume ? '#276146' : C.mut }}>{s.legume ? '+ Adds nitrogen' : 'Uses nitrogen'}</span>
            <span className="pill" style={{ background: rep ? '#F8ECE7' : '#E8F3EF', color: rep ? C.red : '#276146' }}>{rep ? 'Pests build up' : 'Breaks pest cycle'}</span>
            <span className="pill" style={{ background: sb, color: sf }}>{st}{s.season_temperature_c != null ? ` · ${s.season_temperature_c} °C` : ''}</span>
            {s.irrigation_need_mm != null && <span className="pill" style={{ background: '#E8F1F5', color: C.water }}>{Math.round(s.irrigation_need_mm)} mm water</span>}
            {s.harvest && <span className="pill" style={{ background: '#FBF5E6', color: '#6E4E00' }} title={`${s.harvest.tonnes} t at Rs ${s.harvest.price_rs_per_kg}/kg`}>≈ {s.harvest.tonnes} t · {rs(s.harvest.value_rs)}</span>}
          </div>
        })}
      </div>
      {step != null && <span className="muted" style={{ textAlign: 'center' }}>{sel.crops[step].season_label}: {crop(sel.crops[step].crop_id)} growing ({sel.crops[step].suitability_reason}) · next season in 10 s</span>}
    </section>

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

    <section className="card">
      <div className="ct">Why this score</div>
      {(['water', 'soil', 'climate', 'income'] as const).map(k => <div key={k} className="sbar">
        <span>{{ water: 'Water use', soil: 'Soil care', climate: 'Climate fit', income: 'Harvest value' }[k]}</span>
        <span className="track"><i style={{ width: `${Math.round((sel.scores[k] ?? 0) * 100)}%`, background: k === 'water' ? C.water : k === 'soil' ? '#8A6A43' : k === 'climate' ? C.teal : C.gold }} /></span>
        <b>{pct(sel.scores[k])}</b>
      </div>)}
      <span className="faint">Weights you chose: water {Math.round(d.weights.water * 100)}%, soil {Math.round(d.weights.soil * 100)}%, climate {Math.round(d.weights.climate * 100)}%, income {Math.round((d.weights.income ?? 0) * 100)}%.{sel.income?.harvest_value_rs ? ` Harvest about ${rs(sel.income.harvest_value_rs)} a year on ${sel.income.area_ha} ha.` : ''} Contribution to score: {['water', 'soil', 'climate', 'income'].map(k => `${k} ${pct(bd[k])}`).join(', ')}.</span>
    </section>

    <section className="advice">
      <div className="row" style={{ gap: 8 }}><Icon d={I.leaf} c="#8A6A12" s={18} /><b style={{ color: '#6E4E00' }}>Advice for {nice(p.name)}</b></div>
      {[...(best.id !== 'current' ? [`Switch to ${lab(best)} (${rot(best.rotation)}): ranked first for what you care about.`] : []), ...sel.reasons.slice(0, 5), ...(p.soil.ph == null ? ['Test your soil pH so each crop can be checked against its needs.'] : [])].map((a: string, k: number) =>
        <div key={k} className="row" style={{ alignItems: 'flex-start' }}><span className="dot" style={{ background: '#C98B00' }} /><span style={{ fontSize: 13.5, lineHeight: '19px' }}>{a}</span></div>)}
      <span className="faint" style={{ color: '#8A6A12' }}>Modelled by the M2 plan engine from NASA POWER climate, FAO-56 water use and FAO ECOCROP ranges. Check big changes with your extension officer.</span>
    </section>

    <PriceCard p={p} d={d} onSave={onPrices} />

    <details className="card">
      <summary className="ct" style={{ cursor: 'pointer' }}>How this is calculated</summary>
      <div className="list">{d.assumptions.map((a: string, k: number) => <div key={k}><span className="dot" style={{ background: '#A9BAB5' }} /><span style={{ flex: 1 }}>{a}</span></div>)}</div>
      <SourceTag s={planRes.source} what="M2 plan engine" />
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
    <Hero eyebrow={`Water wallet · ${nice(p.name)}`}
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
function Future({ p, loc, scen, scenario, setScenario }: any) {
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
      const st = await api.stressTest(loc.latitude, loc.longitude, scenario, { rotations: m5Rots, soil_ph: p.soil?.ph ?? null, field_area_ha: p.field_area_ha, priorities: p.priorities, prices_rs_per_kg: p.prices_rs_per_kg ?? undefined },
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
  return (<>
    <div><div className="eb">Farm time machine</div><h1 className="h1" style={{ marginTop: 6 }}>Your farm, <span>later.</span></h1></div>
    <Hero eyebrow={`Projection · ${nice(loc?.name)}`} title={dT == null ? (scen && !s ? 'Projections not\nloaded yet.' : 'Loading the\nprojections…') : dT > 0 ? `Warmer by\n${vals[vals.length - 1].year}.` : `Little change\nby ${vals[vals.length - 1].year}.`}
      sub={dT == null ? (scen && !s ? 'NASA projections for this field have not been fetched yet. Keep the backend running with internet; they load in the background.' : undefined) : `${dT > 0 ? '+' : ''}${dT} °C from ${vals[0].year} to ${vals[vals.length - 1].year} (${ens.label}, ${vals[0].contributingModels?.length ?? ''}-model average). Regional, not exact for your field.`} />
    <div className="seg" style={{ gridTemplateColumns: '1fr 1fr' }}>{SCEN.map(([k, l]) => <button key={k} className={scenario === k ? 'on' : ''} onClick={() => setScenario(k)}>{l}</button>)}</div>
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
        <span className="muted">Your field's climate in the 2050s is closest to these places today. Tap one to see it.</span>
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
              <SatellitePlace lat={a.location.latitude} lon={a.location.longitude} label={name} />
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
        <div className="sgrid" style={{ gridTemplateColumns: `1.4fr repeat(${stressE.data.cols.length}, 1fr)` }}>
          <span />{stressE.data.cols.map((c: any) => <span key={c.key} className="sh">{c.label}</span>)}
          {stressE.data.rows.map((r: any) => <Fragment key={r.id}>
            <span className="sn"><b>{r.label}</b><br /><span className="faint">{rot(r.rotation)}</span></span>
            {r.cells.map((c: any, k: number) => <span key={k} className="sc" title={c.tip} style={{ background: c.best ? C.deep : c.ok ? '#E8F3EF' : '#F8ECE7' }}><i style={{ background: c.best ? '#C9E29A' : c.ok ? C.teal : C.red }} /></span>)}
          </Fragment>)}
        </div>
        <div className="row" style={{ gap: 12, fontSize: 12, color: C.ink, flexWrap: 'wrap' }}>
          <span className="row" style={{ gap: 5 }}><i className="lg" style={{ background: C.teal }} />Works</span>
          <span className="row" style={{ gap: 5 }}><i className="lg" style={{ background: C.red }} />Fails (water or heat)</span>
          <span className="row" style={{ gap: 5 }}><i className="lg" style={{ background: '#C9E29A', outline: `2px solid ${C.deep}` }} />Best in that situation</span>
        </div>
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
function Ask({ close, analysis, analysing, p, planRes }: any) {
  const [msgs, setMsgs] = useState<{ me: boolean; text: string; extra?: string }[]>([])
  const [q, setQ] = useState(''), [busy, setBusy] = useState(false)
  const bundle = analysis?.data?.bundle
  const send = async (text: string) => {
    if (!text.trim()) return
    const pd = planRes?.data
    if (pd && /\b(plan|best|switch|rotation|harvest|income|money|earn|price|water need|how much water)\b/i.test(text)) {
      const best = pd.plans.find((x: any) => x.id === pd.best_plan_id), today = pd.plans[0]
      const money = /harvest|income|money|earn|price/i.test(text), water = /water/i.test(text)
      const lines = money ? pd.plans.map((x: any) => `${x.label} (${rot(x.rotation)}): about ${rs(x.income?.harvest_value_rs)} a year.`)
        : water ? pd.plans.map((x: any) => `${x.label}: ${x.water.peak_season_mm != null ? Math.round(x.water.peak_season_mm) : '?'} mm in its driest season, ${x.water.total_mm != null ? Math.round(x.water.total_mm) : '?'} mm a year (you can give ${p.irrigation.budget_mm_per_season ?? 0} mm a season).`)
        : [`Best for you: ${best.label}, ${rot(best.rotation)} (score ${Math.round((best.score ?? 0) * 100)} vs ${Math.round((today.score ?? 0) * 100)} today).`, ...best.reasons.slice(0, 4)]
      setMsgs(m => [...m, { me: true, text }, { me: false, text: lines.join('\n'), extra: `From the M2 plan engine · ${money ? 'example prices unless you entered yours · ' : ''}NASA POWER climate` }]); setQ('')
      return
    }
    if (!bundle) { setMsgs(m => [...m, { me: true, text }, { me: false, text: analysing ? 'Still preparing the analysis, try again in a moment.' : 'Open the Passport to run the analysis first.' }]); setQ(''); return }
    setMsgs(m => [...m, { me: true, text }]); setQ(''); setBusy(true)
    const r = await api.ask(text, bundle)
    setBusy(false)
    setMsgs(m => [...m, { me: false, text: r.data?.answer ?? `The assistant is not reachable (${r.error}).`, extra: r.data ? [r.data.mode === 'refused' ? 'Refused: no evidence for that' : `${r.data.cited_evidence?.length ?? 0} evidence records cited`, ...(r.data.limitations ?? []).slice(0, 1)].join(' · ') : undefined }])
  }
  const first = p?.current_rotation?.[0]
  const sugg = ['Which plan is best for me?', 'How much water does each plan need?', 'What is each plan worth?', first ? `Why ${crop(first).toLowerCase()}?` : 'Why this rotation?', 'What data is missing?', 'What will the climate be in 2050?']
  return (<>
    <SheetHead eyebrow="Ask CropCompass" title="Grounded in your data" close={close} />
    <div className="body" style={{ minHeight: 420 }}>
      {analysing && <Spinner text="Preparing your farm's analysis (M1–M5)…" />}
      {analysis?.source === 'cached' && <span className="faint">Backend offline: answering from a cached example analysis (Pamplemousses, maize → cowpea → cabbage).</span>}
      <div className="bubble" style={{ alignSelf: 'flex-start', background: '#fff', border: `1px solid ${C.line}` }}>Ask about {nice(p?.name) || 'your field'}. Answers come only from the analysis and its sources; if there's no evidence, I'll say so.</div>
      {msgs.map((m, k) => <div key={k} className="bubble" style={{ whiteSpace: 'pre-line', alignSelf: m.me ? 'flex-end' : 'flex-start', background: m.me ? C.deep : '#fff', color: m.me ? '#fff' : C.ink, border: m.me ? 0 : `1px solid ${C.line}` }}>{m.text}{m.extra && <div className="faint" style={{ marginTop: 6 }}>{m.extra}</div>}</div>)}
      {busy && <Spinner text="Thinking…" />}
      <div className="chips" style={{ marginTop: 'auto' }}>{sugg.map(s => <button key={s} className="chip" onClick={() => send(s)}>{s}</button>)}</div>
      <div className="row">
        <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && send(q)} placeholder="Ask about your field" aria-label="Question" style={{ flex: 1, minHeight: 46, border: '1.5px solid #D5DFDB', borderRadius: 23, padding: '0 16px', fontSize: 14.5 }} />
        <button className="round" style={{ width: 46, height: 46, background: C.deep, border: 0 }} aria-label="Send" onClick={() => send(q)}><Icon d={I.send} c="#fff" /></button>
      </div>
    </div>
  </>)
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
