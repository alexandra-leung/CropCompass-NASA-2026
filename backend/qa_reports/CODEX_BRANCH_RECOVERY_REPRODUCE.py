import json,os,collections,asyncio
from pathlib import Path
os.environ['M5_OFFLINE']='1'
from fastapi.testclient import TestClient
from app import app
import climateM1.services.cache as cache
cache.CACHE_TTL_SECONDS=10**12
# Explicit cache-only audit: fail network instead of accidentally refreshing source files.
import httpx
async def blocked(*a,**k): raise httpx.ConnectError('audit cache-only: network blocked')
httpx.AsyncClient.send=blocked
client=TestClient(app,raise_server_exceptions=False)
results={}
spec=client.get('/openapi.json').json()
Path('audit-openapi.json').write_text(json.dumps(spec,indent=2))
counts=collections.Counter((r.path,m) for r in app.routes for m in getattr(r,'methods',[]))
results['duplicate_routes']=[list(k) for k,n in counts.items() if n>1]
def call(name,method,path,body=None):
 r=client.request(method,path,json=body) if body is not None else client.request(method,path)
 try:d=r.json()
 except Exception:d=r.text
 results[name]={'status':r.status_code,'body':d}
 print(name,r.status_code,flush=True)
 return d
call('health','GET','/health')
call('m5_health','GET','/api/resilience/health')
call('farms','GET','/api/farms')
from mappingM3.farm_profile import get_farm_profile
results['qa_farm_context']={'label':'Repository illustrative demo farm, NOT verified farmer inputs','profile':get_farm_profile('pamplemousses-04')}
h=call('history_cached','GET','/api/climate/history?location_id=pamplemousses-04&start=2021-01-01&end=2025-12-31')
call('projections_cached','GET','/api/climate/scenarios?location_id=pamplemousses-04')
call('rotation','POST','/api/agriculture/rotation',{'crops':['maize','cowpea','cabbage']})
call('alternatives','POST','/api/agriculture/generate',{'current_rotation':['maize','cowpea','cabbage'],'max_alternatives':3})
call('suitability','GET','/api/agriculture/suitability/maize?temperature_c=25&soil_ph=6.5')
plans=call('plans_cached','POST','/api/agriculture/plans',{'farm_id':'pamplemousses-04'})
base={'latitude':-20.103,'longitude':57.575,'scenario':'ssp245','start_year':2041,'end_year':2060}
twin=call('twin_cached','POST','/api/resilience/climate-twin',base)
rr={'rotations':[{'id':'current','crops':['maize','maize','maize']},{'id':'alt1','crops':['cowpea','cabbage','maize']},{'id':'alt2','crops':['cowpea','tomato','maize']}],'field_area_ha':0.6}
stress=call('stress_qa_cached','POST','/api/resilience/stress-test',{**base,'rotation_request':rr,'baseline_water_budget_m3':3600,'irrigation_reduction_fraction':0.5})
if 'scenarios' in stress:call('rescue_qa_cached','POST','/api/resilience/rescue-mode',{'stress_output':stress})
an=call('analyze_cached','POST','/api/intelligence/analyze',{'farm':{'farm_id':'pamplemousses-04','location_id':'pamplemousses-04'},'scenario':'ssp245','year':2050})
if 'bundle' in an:
 bundle=an['bundle'];bundle['resilience']={'climate_twin':twin if 'analogs' in twin else None,'stress_tests':[stress] if 'scenarios' in stress else []}
 ev=call('evidence','POST','/api/intelligence/evidence',bundle)
 call('assistant','POST','/api/intelligence/assistant',{'question':'What evidence is missing?','analysis':bundle,'use_llm':False})
 records=ev.get('evidence',[])
 results['m5_exact_pass_through']={kind:any(e.get('value')==bundle['resilience'][kind] and e.get('provenance',{}).get('field_path')=='resilience.'+kind for e in records) for kind in ('climate_twin','stress_tests')}
# Diagnostic probes, QA-only: no scientific values presented as observed.
from agricultureM2.plan_engine import build_plans
p=build_plans(current=['maize','cowpea','cabbage'],seasonal=None,budget_mm=None,area_ha=None,soil_ph=None,priorities=None)
results['missing_inputs_probe']={'status':p['status'],'feasible':p['plans'][0]['feasible'],'income':p['plans'][0]['income'],'score':p['plans'][0]['score']}
call('unknown_crop_validation','POST','/api/agriculture/plans',{'farm_id':'pamplemousses-04','rotations':[['not-a-crop']]})
if 'scenarios' in stress:
 call('stress_unknown_crop_validation','POST','/api/resilience/stress-test',{**base,'rotation_request':{'rotations':[{'id':str(i),'crops':['not-a-crop']} for i in range(3)]},'baseline_water_budget_m3':100})
from agricultureM2.water_wallet import calculate_crop_water_demand
try:calculate_crop_water_demand('maize',[])
except ValueError as e:results['water_wallet_missing_daily_et0']={'blocked':str(e),'reason':'No verified daily reference ET0 series; no substitute invented.'}
Path('audit-workflow.json').write_text(json.dumps(results,indent=2))
print('SUMMARY',json.dumps({k:v.get('status') for k,v in results.items() if isinstance(v,dict)}),flush=True)
