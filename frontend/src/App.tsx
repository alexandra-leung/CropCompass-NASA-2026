import { useEffect, useMemo, useRef, useState } from 'react'
import * as api from './api'
import type { Source } from './api'
import { Bars, C, Hero, I, Icon, Kpi, LineChart, SourceTag, Spinner, Tag } from './ui'
import { CropPic } from './crops'
import { SatelliteField } from './satellite'

type Tab = 'home' | 'fields' | 'plans' | 'water' | 'future'
type Sheet = null | { kind: 'field' } | { kind: 'add' } | { kind: 'ask' } | { kind: 'passport' }

const USER = 'Sanjana'
const CROP_NAMES: Record<string, string> = { maize: 'Maize', tomato: 'Tomato', onion: 'Onion', cabbage: 'Cabbage', cowpea: 'Cowpea', groundnut: 'Groundnut', sweet_potato: 'Sweet potato' }
const crop = (id: string) => CROP_NAMES[id] ?? id
const nice = (n?: string) => (n ?? '').replace(/ Field \d+$/, '')
const rot = (r?: string[] | null) => (r && r.length ? r.map(crop).join(' → ') : 'Not entered')
const TEXTURES: [string, string][] = [['sandy_loam', 'Sandy loam'], ['loam', 'Loam'], ['clay_loam', 'Clay loam'], ['clay', 'Clay'], ['unknown', "Don't know"]]
const WATER: [string, string][] = [['rain_only', 'Rain only'], ['tank', 'Tank or pond'], ['borehole', 'Borehole'], ['irrigation_scheme', 'Irrigation scheme']]
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
  const [gen, setGen] = useState<api.Res<any> | null>(null)
  const [analysis, setAnalysis] = useState<api.Res<any> | null>(null)
  const [analysing, setAnalysing] = useState(false)
  const [scenario, setScenario] = useState('ssp245')

  const loadFarms = async (select?: string) => { const r = await api.getFarms(); setFarms(r); if (select) setFarmId(select) }
  const loadFarm = async (id = farmId) => setFarm(await api.getFarm(id))
  useEffect(() => { loadFarms() }, [])
  useEffect(() => {
    setFarm({ data: null, source: 'none' }); setHistory(null); setScen(null); setGen(null); setAnalysis(null)
    loadFarm(farmId)
  }, [farmId])
  const p = farm.data
  useEffect(() => {
    if (!p) return
    const ctl = new AbortController(), live = () => !ctl.signal.aborted
    setHistory(api.cached.history(p.location_id)); setScen(api.cached.scenarios(p.location_id))
    if (p.current_rotation?.length) api.generateRotations(p.current_rotation).then(r => live() && setGen(r))
    api.getHistory(p.location_id, ctl.signal).then(r => live() && setHistory(prev => (r.source === 'live' || !prev ? r : prev)))
    api.getScenarios(p.location_id, ctl.signal).then(r => live() && setScen(prev => (r.source === 'live' || !prev ? r : prev)))
    return () => ctl.abort()
  }, [p?.farm_id, p?.location_id, (p?.current_rotation || []).join()])

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
        {tab === 'home' && <Home p={p} loc={loc} farms={farmList} history={history} openField={() => setSheet({ kind: 'field' })} farmsSrc={farms.source} goFields={() => setTab('fields')} />}
        {tab === 'fields' && <Fields farms={farmList} src={farms.source} open={(id: string) => { setFarmId(id); setSheet({ kind: 'field' }) }} add={() => setSheet({ kind: 'add' })} />}
        {tab === 'plans' && <Plans p={p} gen={gen} goFields={() => setTab('fields')} />}
        {tab === 'water' && <Water p={p} history={history} onSaved={(np: any) => setFarm({ data: np, source: 'live' })} />}
        {tab === 'future' && <Future p={p} loc={loc} scen={scen} scenario={scenario} setScenario={setScenario} gen={gen} />}
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
            {sheet.kind === 'ask' && <Ask close={() => setSheet(null)} analysis={analysis} analysing={analysing} p={p} />}
            {sheet.kind === 'passport' && <Passport close={() => setSheet(null)} analysis={analysis} analysing={analysing} p={p} rerun={runAnalysis} />}
          </div>
        </div>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ HOME */
function Home({ p, loc, farms, history, openField, farmsSrc, goFields }: any) {
  const h = history?.data
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
      <div><div className="eb">{date}</div><h1 className="h1" style={{ marginTop: 6 }}>{greet}<br /><span>{USER}.</span></h1></div>
    </div>
    <Hero eyebrow={`Farm status · ${nice(loc?.name)}`} title={title} sub={sub} />
    <div className="kpis">
      <Kpi onClick={goFields} v={String(farms.length || '…')} l="Fields" />
      <Kpi onClick={goFields} v={p?.irrigation?.budget_mm_per_season != null ? String(Math.round(p.irrigation.budget_mm_per_season)) : '…'} unit="mm" l={`Water · ${nice(p?.name)}`} />
      <Kpi onClick={goFields} v={m ? `${m.dataCompleteness}` : history && !h ? '–' : '…'} unit={m ? '%' : undefined} l="Climate data" />
    </div>
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
function Fields({ farms, src, open, add }: any) {
  return (<>
    <div className="eb">Your land, at a glance</div>
    <div className="row"><span style={{ fontSize: 34, fontWeight: 700, letterSpacing: -1, color: C.deep }}>Fields</span>
      <span style={{ fontSize: 12, fontWeight: 700, color: C.teal, background: '#E9F1EE', padding: '3px 8px', borderRadius: 8 }}>{String(farms.length).padStart(2, '0')}</span>
      <button className="btn" style={{ marginLeft: 'auto', minHeight: 42, padding: '0 14px', fontSize: 13.5 }} onClick={add}>+ Add field</button></div>
    <div className="between"><span className="muted">Farmer inputs and field outlines, from M3.</span><SourceTag s={src} /></div>
    {farms.map((f: any) => {
      const bad = f.missing_count > 0
      const col = bad ? C.red : C.teal
      return (
        <button key={f.farm_id} className="fcard" onClick={() => open(f.farm_id)}>
          <span className="bar" style={{ background: col }} />
          <span className="in">
            <span className="between"><span style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span className="faint" style={{ fontWeight: 700 }}>{rot(f.current_rotation)} · {f.district}</span><span style={{ fontSize: 17 }}>{nice(f.name)}</span></span><span style={{ color: '#A9BAB5', fontSize: 18 }}>›</span></span>
            <span style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
              <span className="stat"><span>Area</span><b>{f.field_area_ha ?? '–'} ha</b></span>
              <span className="stat"><span>Water</span><b>{f.irrigation_budget_mm ?? '–'} mm</b></span>
              <span className="stat"><span>Soil</span><b style={{ fontSize: 12.5 }}>{f.soil_texture}</b></span>
            </span>
            <span className="row" style={{ gap: 6, fontSize: 11.5 }}><span className="dot" style={{ background: col, marginTop: 0 }} /><b style={{ color: col }}>{bad ? `Needs ${f.missing_count} answer${f.missing_count > 1 ? 's' : ''}` : 'Complete'}</b>{f.demo && <span className="faint" style={{ marginLeft: 'auto' }}>Demo farm</span>}</span>
          </span>
        </button>)
    })}
  </>)
}

function FieldSheet({ p, src, close, onSaved, passport }: any) {
  const [err, setErr] = useState('')
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
      {p.boundary?.geometry?.coordinates?.[0] ? <SatelliteField ring={p.boundary.geometry.coordinates[0]} label={p.boundary.method === 'manual' ? 'Outline drawn by farmer' : 'Placeholder outline · redraw to match your field'} /> : <div className="err">No outline yet.</div>}
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
function Plans({ p, gen, goFields }: any) {
  const [i, setI] = useState(0)
  const [step, setStep] = useState<number | null>(null)
  const [suit, setSuit] = useState<Record<string, any>>({})
  const g = gen?.data
  const plans: any[] = g ? [g.current_rotation, ...(g.alternative_rotations ?? [])] : []
  const sel = plans[Math.min(i, Math.max(plans.length - 1, 0))]
  useEffect(() => { setI(0); setStep(null) }, [p?.farm_id])
  useEffect(() => {
    const ids = Array.from(new Set(plans.flatMap(x => x.rotation)))
    ids.forEach(id => { if (!suit[id]) api.suitability(id, p?.soil?.ph).then(r => setSuit(s => ({ ...s, [id]: r }))) })
  }, [g])
  useEffect(() => {
    if (step == null || !sel) return
    const t = window.setTimeout(() => setStep(step + 1 < sel.sequence.length ? step + 1 : null), 1400)
    return () => window.clearTimeout(t)
  }, [step, sel])
  if (!p) return <Spinner text="Loading farm…" />
  const head = (
    <>
      <div><div className="eb">Plans for this field</div><h1 className="h1" style={{ marginTop: 6 }}>{nice(p.name)}<br /><span>season by season.</span></h1></div>
      <button className="ctx" onClick={goFields}>
        <span><small>Soil</small><b>{TEXTURES.find(t => t[0] === p.soil.texture)?.[1] ?? 'Unknown'}</b></span>
        <span><small>pH</small><b>{p.soil.ph ?? '?'}</b></span>
        <span><small>Water</small><b>{p.irrigation.budget_mm_per_season ?? '?'} mm</b></span>
        <span className="go">Change field ›</span>
      </button>
    </>)
  if (!p.current_rotation?.length) return <>{head}<div className="err">Add the crops you grow in Fields to compare plans.</div></>
  if (!gen) return <>{head}<Spinner text="Asking M2 for other rotations…" /></>
  if (!g) return <>{head}<div className="err">M2 could not suggest plans{gen.error ? `: ${gen.error}` : ''}.</div></>
  const today = plans[0]
  const n = sel.sequence.length
  const legume = (x: any) => (x.nitrogen_fixing_crops?.length ?? 0) > 0
  const repeatAt = (k: number) => sel.sequence[k].family === sel.sequence[(k - 1 + n) % n].family
  const advice: string[] = []
  if (!legume(today)) advice.push(`Your rotation has no legume. Put cowpea or groundnut after ${crop(today.rotation[0]).toLowerCase()}: it adds nitrogen for the next crop.`)
  const reps = today.sequence.filter((s: any, k: number) => s.family === today.sequence[(k - 1 + today.sequence.length) % today.sequence.length].family)
  if (reps.length) advice.push(`Avoid ${crop(reps[0].crop_id).toLowerCase()} straight after the same family: changing family breaks pest and disease cycles.`)
  if (i > 0) {
    const fixes = [legume(sel) && !legume(today) ? 'adds a legume' : '', !sel.has_adjacent_family_repetition && today.has_adjacent_family_repetition ? 'stops the family repeating' : ''].filter(Boolean)
    advice.push(fixes.length ? `Plan ${String.fromCharCode(64 + i)} ${fixes.join(' and ')}.` : `Plan ${String.fromCharCode(64 + i)} does not improve on today's rotation rules${!legume(sel) ? ' and has no legume' : ''}.`)
  }
  if (p.soil.ph == null) advice.push('Test your soil pH, so each crop can be checked against its needs.')
  return (<>
    {head}
    <div className="tabs" role="tablist">{plans.map((_x, k) => <button key={k} role="tab" className={k === i ? 'on' : ''} onClick={() => { setI(k); setStep(null) }}>{k === 0 ? 'Today' : `Plan ${String.fromCharCode(64 + k)}`}</button>)}</div>

    <section className="card">
      <div className="between">
        <div><div className="eb">{i === 0 ? 'Your rotation' : `Plan ${String.fromCharCode(64 + i)}`}</div><div className="ct">{rot(sel.rotation)}</div></div>
        <button className="play" aria-label={step == null ? 'Play the seasons' : 'Stop'} onClick={() => setStep(step == null ? 0 : null)}>
          <Icon d={step == null ? 'M8 5l11 7-11 7z' : 'M6 5h4v14H6z M14 5h4v14h-4z'} c="#fff" s={16} /></button>
      </div>
      <div className="seasons" style={{ gridTemplateColumns: `repeat(${n}, 1fr)` }}>
        {sel.sequence.map((s: any, k: number) => {
          const on = step === k, nf = sel.nitrogen_fixing_crops?.includes(s.crop_id), rep = repeatAt(k)
          return <div key={k} className={'season' + (on ? ' on' : '') + (step != null && !on ? ' dim' : '')}>
            <span className="faint">Season {s.season}</span>
            <div className="plot"><CropPic id={s.crop_id} size={58} /></div>
            <b>{crop(s.crop_id)}</b>
            <span className="faint">{FAM[s.family] ?? s.family}</span>
            <span className="pill" style={{ background: nf ? '#E8F3EF' : '#F2F6F4', color: nf ? '#276146' : C.mut }}>{nf ? '+ Adds nitrogen' : 'Uses nitrogen'}</span>
            <span className="pill" style={{ background: rep ? '#F8ECE7' : '#E8F3EF', color: rep ? C.red : '#276146' }}>{rep ? 'Pests build up' : 'Breaks pest cycle'}</span>
          </div>
        })}
      </div>
      <span className="faint">Illustration from rotation rules (M2): legumes add nitrogen; the same family twice in a row lets pests and disease build up. Not a field measurement.</span>
    </section>

    <section className="advice">
      <div className="row" style={{ gap: 8 }}><Icon d={I.leaf} c="#8A6A12" s={18} /><b style={{ color: '#6E4E00' }}>Advice for {nice(p.name)}</b></div>
      {advice.map((a, k) => <div key={k} className="row" style={{ alignItems: 'flex-start' }}><span className="dot" style={{ background: '#C98B00' }} /><span style={{ fontSize: 13.5, lineHeight: '19px' }}>{a}</span></div>)}
      <span className="faint" style={{ color: '#8A6A12' }}>From rotation rules and your farm inputs. Plans are not ranked yet: M2 scores are not calibrated.</span>
    </section>

    {i > 0 && <section className="card">
      <div className="ct">Today versus Plan {String.fromCharCode(64 + i)}</div>
      <div className="cmp"><span /><b>Today</b><b>Plan {String.fromCharCode(64 + i)}</b>
        <span>Legume</span><span style={{ color: legume(today) ? '#276146' : C.red }}>{legume(today) ? 'Yes' : 'No'}</span><span style={{ color: legume(sel) ? '#276146' : C.red }}>{legume(sel) ? 'Yes' : 'No'}</span>
        <span>Family repeats</span><span style={{ color: today.has_adjacent_family_repetition ? C.red : '#276146' }}>{today.has_adjacent_family_repetition ? 'Yes' : 'No'}</span><span style={{ color: sel.has_adjacent_family_repetition ? C.red : '#276146' }}>{sel.has_adjacent_family_repetition ? 'Yes' : 'No'}</span>
        <span>Crop families</span><span>{new Set(today.sequence.map((s: any) => s.family)).size}</span><span>{new Set(sel.sequence.map((s: any) => s.family)).size}</span>
      </div>
    </section>}

    <section className="card">
      <div className="between"><div><div className="eb">Crop suitability</div><div className="ct">For this soil and climate</div></div><SourceTag s={gen.source} what="M2 · FAO" /></div>
      <div className="list">{Array.from(new Set(sel.rotation as string[])).map(id => {
        const s = suit[id]?.data, st = s?.status
        const col = st === 'suitable' ? C.teal : st === 'unsuitable' ? C.red : C.gold
        return <div key={id}><CropPic id={id} size={30} /><span style={{ flex: 1 }}><b>{crop(id)}</b><br /><span className="faint">{!s ? 'Checking…' : st === 'insufficient_data' ? `Not checked yet: missing ${(s.missing ?? []).map((x: string) => ({ temperature_c: 'temperature', soil_ph: 'soil pH', rainfall_mm: 'rainfall' } as any)[x] ?? x).join(', ')}` : st}</span></span><span className="dot" style={{ background: col }} /></div>
      })}</div>
    </section>

    <section className="card">
      <div className="ct">Coming from M2</div>
      <div className="list">
        <div><span className="dot" style={{ background: '#A9BAB5' }} /><span style={{ flex: 1 }}>Ranking and soil-health score<br /><span className="faint">Not calibrated yet, so plans are not ranked.</span></span></div>
        <div><span className="dot" style={{ background: '#A9BAB5' }} /><span style={{ flex: 1 }}>Water each plan needs (FAO-56)<br /><span className="faint">Not calculated yet.</span></span></div>
      </div>
    </section>
  </>)
}

/* ------------------------------------------------------------------ WATER */
function Water({ p, history, onSaved }: any) {
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
  const seas: any[] = history?.data?.seasonal ?? []
  const years = Array.from(new Set(seas.map(x => x.period.slice(0, 4))))
  const lastYear = years.filter(y => seas.filter(x => x.period.startsWith(y)).length === 4).pop() ?? null
  const year = seas.filter(s => s.period.startsWith(lastYear))
  const order = ['DJF', 'MAM', 'JJA', 'SON']
  const names: Record<string, string> = { DJF: 'Dec–Feb', MAM: 'Mar–May', JJA: 'Jun–Aug', SON: 'Sep–Nov' }
  return (<>
    <div><div className="eb">Smart irrigation</div><h1 className="h1" style={{ marginTop: 6, fontSize: 34, lineHeight: '36px' }}>Water,<br /><span>well spent.</span></h1></div>
    <Hero eyebrow={`Water wallet · ${nice(p.name)}`} title={mm > 0 ? `You can give\n${Math.round(mm)} mm a season.` : 'Rain only:\nno irrigation.'} sub={m3 != null ? `That is ${m3.toLocaleString()} m³ on ${p.field_area_ha} ha. How much each plan needs is not calculated yet (M2 water wallet).` : 'Add the field size to convert to m³.'} />
    <section className="card">
      <div className="between"><div><div className="eb">Water you can give</div><span className="muted">per season</span></div><Tag k="entered" /></div>
      <div className="row" style={{ alignItems: 'baseline', gap: 6 }}><span style={{ fontSize: 36, fontWeight: 700, color: C.deep }}>{Math.round(mm)}</span><span className="muted">mm</span>
        <span className="faint" style={{ marginLeft: 'auto' }}>{state === 'saving' ? 'Saving…' : state === 'saved' ? 'Saved to your farm' : state === 'error' ? 'Not saved: backend offline' : ''}</span></div>
      <input type="range" min={0} max={400} step={25} value={mm} onChange={e => change(+e.target.value)} aria-label="Water per season" />
    </section>
    <section className="card">
      <div className="between"><div><div className="eb">Rain by season</div><div className="ct">{lastYear ? `Rain in ${lastYear}` : 'Rain by season'}</div></div>{history && <SourceTag s={history.source} what="NASA POWER" />}</div>
      {!history ? <Spinner text="Reading NASA POWER…" /> : year.length === 0 ? <div className="err">No seasonal rain cached for this location.</div> :
        <Bars unit="mm" items={order.map(o => ({ label: names[o], value: year.find(s => s.period.endsWith(o))?.rainfallMm ?? null }))} />}
      {year.length > 0 && <div style={{ display: 'flex', gap: 10 }}>{order.map(o => <span key={o} className="faint" style={{ flex: 1, textAlign: 'center' }}>{names[o]}</span>)}</div>}
      <span className="faint">Dry season (Jun–Nov) is when irrigation matters most.</span>
    </section>
  </>)
}

/* ------------------------------------------------------------------ FUTURE */
function Future({ p, loc, scen, scenario, setScenario, gen }: any) {
  const [twin, setTwin] = useState<api.Res<any> | null>(null)
  const [stress, setStress] = useState<api.Res<any> | null>(null)
  const [yi, setYi] = useState(2)
  useEffect(() => { if (loc) { setTwin(api.cached.twin()); api.climateTwin(loc.latitude, loc.longitude, scenario).then(r => { if (r.source === 'live') setTwin(r) }) } }, [loc?.farm_id, scenario])
  const rotations = useMemo(() => {
    const g = gen?.data; if (!g) return null
    return [{ id: 'current', crops: g.current_rotation.rotation }, ...g.alternative_rotations.slice(0, 2).map((a: any, k: number) => ({ id: `alternative_${'ab'[k]}`, crops: a.rotation }))]
  }, [gen?.data])
  useEffect(() => { if (loc && rotations && p) { setStress(api.cached.stress()); api.stressTest(loc.latitude, loc.longitude, scenario, rotations, p.soil?.ph ?? null, p.irrigation_budget_m3 ?? 0).then(r => { if (r.source === 'live') setStress(r) }) } }, [loc?.farm_id, scenario, rotations])
  const s = scen?.data
  const ens = s?.ensemble?.find((e: any) => e.id === scenario)
  const vals: any[] = ens?.values ?? []
  const t0 = vals[0]?.temperatureC?.mean, t2 = vals[vals.length - 1]?.temperatureC?.mean
  const dT = t0 != null && t2 != null ? +(t2 - t0).toFixed(2) : null
  const v = vals[Math.min(yi, vals.length - 1)]
  return (<>
    <div><div className="eb">Farm time machine</div><h1 className="h1" style={{ marginTop: 6, fontSize: 34, lineHeight: '36px' }}>Your farm,<br /><span>later.</span></h1></div>
    <Hero eyebrow={`Projection · ${nice(loc?.name)}`} title={dT == null ? 'Loading the\nprojections…' : dT > 0 ? `Warmer by\n${vals[vals.length - 1].year}.` : `Little change\nby ${vals[vals.length - 1].year}.`}
      sub={dT == null ? (scen && !s ? 'Projections are not cached for this location; start the backend with internet.' : undefined) : `${dT > 0 ? '+' : ''}${dT} °C from ${vals[0].year} to ${vals[vals.length - 1].year} (${ens.label}, ${vals[0].contributingModels?.length ?? ''}-model average). Regional, not exact for your field.`} />
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
        {twin.source === 'cached' && <span className="faint">Cached example for a point near {twin.data.field.latitude}, {twin.data.field.longitude} ({twin.data.scenario}).</span>}
        <div className="list">{twin.data.analogs.map((a: any, k: number) => <div key={a.location.id}><span className="dot" style={{ background: k ? '#A9BAB5' : C.teal }} /><span style={{ flex: 1 }}><b>{a.location.name}</b><br /><span className="faint">Temperature off by {a.temperature_rmse_c} °C · rain off by {Math.round(a.precipitation_mae_mm_per_month)} mm a month</span></span><span className="faint">#{k + 1}</span></div>)}</div>
        <span className="faint">{twin.data.limitations?.[0]}</span>
      </>}
    </section>
    <section className="card">
      <div className="between"><div><div className="eb">Stress test</div><div className="ct">Do the plans hold up?</div></div>{stress && <SourceTag s={stress.source} what="M5" />}</div>
      {!stress ? <Spinner text="Running 4 scenarios…" /> : !stress.data ? <div className="err">Stress test unavailable{stress.error ? `: ${stress.error}` : ''}.</div> : <>
        <div className="list">{stress.data.scenarios.map((sc: any) => {
          const feas = Object.values(sc.rotations ?? {}).map((r: any) => r.feasible)
          const known = feas.some(f => f != null)
          return <div key={sc.scenario_id}><span className="dot" style={{ background: known ? C.teal : '#A9BAB5' }} /><span style={{ flex: 1 }}><b>{sc.scenario_id.replace(/_/g, ' ').replace(/^./, (c: string) => c.toUpperCase())}</b><br />
            <span className="faint">{sc.temperature_annual_mean_c?.toFixed(1)} °C · {Math.round(sc.precipitation_annual_total_mm ?? 0).toLocaleString()} mm · water {Math.round(sc.water_budget_m3 ?? 0)} m³</span><br />
            <span className="faint">Plans: {known ? feas.map(f => (f ? 'works' : 'fails')).join(', ') : 'result unknown until M2 scores plans'}</span></span></div>
        })}</div>
      </>}
    </section>
  </>)
}

/* ------------------------------------------------------------------ ASK + PASSPORT */
function Ask({ close, analysis, analysing, p }: any) {
  const [msgs, setMsgs] = useState<{ me: boolean; text: string; extra?: string }[]>([])
  const [q, setQ] = useState(''), [busy, setBusy] = useState(false)
  const bundle = analysis?.data?.bundle
  const send = async (text: string) => {
    if (!text.trim() || !bundle) return
    setMsgs(m => [...m, { me: true, text }]); setQ(''); setBusy(true)
    const r = await api.ask(text, bundle)
    setBusy(false)
    setMsgs(m => [...m, { me: false, text: r.data?.answer ?? `The assistant is not reachable (${r.error}).`, extra: r.data ? [r.data.mode === 'refused' ? 'Refused: no evidence for that' : `${r.data.cited_evidence?.length ?? 0} evidence records cited`, ...(r.data.limitations ?? []).slice(0, 1)].join(' · ') : undefined }])
  }
  const first = p?.current_rotation?.[0]
  const sugg = [first ? `Why ${crop(first).toLowerCase()}?` : 'Why this rotation?', 'What data is missing?', 'How sure is this analysis?', 'What will the climate be in 2050?']
  return (<>
    <SheetHead eyebrow="Ask CropCompass" title="Grounded in your data" close={close} />
    <div className="body" style={{ minHeight: 420 }}>
      {analysing && <Spinner text="Preparing your farm's analysis (M1–M5)…" />}
      {analysis?.source === 'cached' && <span className="faint">Backend offline: answering from a cached example analysis (Pamplemousses, maize → cowpea → cabbage).</span>}
      <div className="bubble" style={{ alignSelf: 'flex-start', background: '#fff', border: `1px solid ${C.line}` }}>Ask about {nice(p?.name) || 'your field'}. Answers come only from the analysis and its sources; if there's no evidence, I'll say so.</div>
      {msgs.map((m, k) => <div key={k} className="bubble" style={{ whiteSpace: 'pre-line', alignSelf: m.me ? 'flex-end' : 'flex-start', background: m.me ? C.deep : '#fff', color: m.me ? '#fff' : C.ink, border: m.me ? 0 : `1px solid ${C.line}` }}>{m.text}{m.extra && <div className="faint" style={{ marginTop: 6 }}>{m.extra}</div>}</div>)}
      {busy && <Spinner text="Thinking…" />}
      <div className="chips" style={{ marginTop: 'auto' }}>{sugg.map(s => <button key={s} className="chip" disabled={!bundle} onClick={() => send(s)}>{s}</button>)}</div>
      <div className="row">
        <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && send(q)} placeholder="Ask about your field" aria-label="Question" style={{ flex: 1, minHeight: 46, border: '1.5px solid #D5DFDB', borderRadius: 23, padding: '0 16px', fontSize: 14.5 }} />
        <button className="round" style={{ width: 46, height: 46, background: C.deep, border: 0 }} aria-label="Send" disabled={!bundle} onClick={() => send(q)}><Icon d={I.send} c="#fff" /></button>
      </div>
    </div>
  </>)
}

function Passport({ close, analysis, analysing, p, rerun }: any) {
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
      <button className="btn light" disabled={analysing} onClick={rerun}>{analysing ? 'Running…' : 'Run the analysis again'}</button>
      <span className="faint">CropCompass helps you explore choices. It is not a guarantee of harvest or profit.</span>
    </div>
  </>)
}

export type { Source }
