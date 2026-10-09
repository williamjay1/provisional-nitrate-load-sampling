"""Extended immutable data acquisition; pilot inputs are reused, never overwritten.

Discovery is by published station list plus geographically diverse official
candidates, not by model performance. No prediction or 2025 policy score is run.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip, hashlib, json, os, shutil, time
from pathlib import Path
from acquire_usgs import fetch, immutable_save, metadata, download_year

WORK=Path('D:/MLWork/NitrateAdaptiveSampling_20261005')
RAW=Path('F:/AcademicData/NitrateAdaptiveSampling_20261005/raw')
BASE='https://api.waterdata.usgs.gov/ogcapi/v1/collections'
PILOT=['03346500','03374100','05447500','05465500','05482000','05484500','05595000','07144100']
SI=['05482000','05482300','05484000','05484500','05515500','05518000','05524500',
    '05537980','05543010','05586300','05595000','05599490','03216070','03290500',
    '03338780','03339000','03346500','03353200','03353415','03353420','03374100']
GEO=['12212050','06902000','01646500','02087500','02089500','01491000','01578310','01540500','02035000']
DEFAULT=list(dict.fromkeys(PILOT+SI+GEO))

def now():return datetime.now(timezone.utc).isoformat()

def station_discovery(site,run_dir):
    rec=metadata(site,run_dir)
    r,j=fetch(BASE+'/monitoring-locations/items/USGS-'+site,{'f':'json'})
    path=run_dir/f'{site}_location.json'
    immutable_save(path,r.content)
    rec['location']={'data':j,'path':str(path),'url':r.url,'sha256':hashlib.sha256(r.content).hexdigest()}
    active={p:[s for s in rec['series'] if s['series']['parameter_code']==p and s['series']['begin'] is not None] for p in ['00060','99133']}
    rec['has_same_site_q']=bool(active['00060'])
    rec['has_99133_points']=bool(active['99133'])
    rec['nox_method_codes']=sorted({m['interval']['method_id'] for s in active['99133'] for m in s['methods']})
    rec['nox_uv_method_found']=any(code.startswith('UV') for code in rec['nox_method_codes'])
    rec['nox_spans']=[{'begin':s['series']['begin'],'end':s['series']['end'],'series_id':s['series']['id'],'sublocation':s['series'].get('sublocation_identifier'),'primary':s['series'].get('primary'),'web_description':s['series'].get('web_description')} for s in active['99133']]
    rec['candidate_provenance']=['pilot' if site in PILOT else 'HESS2026_SI' if site in SI else 'geographic_extension']
    return rec

def existing_records():
    out={}
    for path in sorted(list((WORK/'datasets').glob('acquisition_manifest_*.json'))+list((WORK/'datasets').glob('extended_acquisition_*.json'))):
        m=json.loads(path.read_text(encoding='utf-8'))
        for rec in m.get('downloads',[]):
            key=(rec['site'],int(rec['year']))
            if key not in out:
                out[key]={**rec,'source_manifest':str(path)}
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--mode',choices=['discover','download'],required=True)
    p.add_argument('--sites',nargs='+',default=DEFAULT)
    p.add_argument('--years',nargs='+',type=int,default=list(range(2019,2026)))
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--max-new-response-mb',type=float,default=1400.)
    p.add_argument('--limit-to-known-nox-span',action='store_true',help='Skip years wholly outside discovered NOx span; retain explicit skip record')
    args=p.parse_args()
    for folder in [WORK/'temp',WORK/'cache',WORK/'datasets',WORK/'results',RAW]:folder.mkdir(parents=True,exist_ok=True)
    os.environ['TEMP']=os.environ['TMP']=str(WORK/'temp')
    disk={drive:shutil.disk_usage(drive).free for drive in ['D:/','E:/','F:/']}
    if disk['F:/']<args.max_new_response_mb*1e6 or disk['D:/']<5e9:raise RuntimeError('Insufficient designated drive capacity')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_dir=RAW/('usgs_extended_'+stamp);run_dir.mkdir(exist_ok=False)
    print(json.dumps({'mode':args.mode,'raw_run':str(run_dir),'free_bytes':disk}),flush=True)
    if args.mode=='discover':
        records=[];errors=[]
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            fs={ex.submit(station_discovery,s,run_dir):s for s in args.sites}
            for future in as_completed(fs):
                site=fs[future]
                try:
                    rec=future.result();records.append(rec)
                    print(json.dumps({'site':site,'name':rec['location']['data']['properties']['monitoring_location_name'],'q':rec['has_same_site_q'],'nox':rec['has_99133_points'],'methods':rec['nox_method_codes'],'spans':rec['nox_spans']}),flush=True)
                except Exception as e:
                    errors.append({'site':site,'error':repr(e)});print(json.dumps(errors[-1]),flush=True)
        path=WORK/'datasets'/f'extended_discovery_{stamp}.json'
        path.write_text(json.dumps({'created_utc':now(),'raw_run':str(run_dir),'storage_free_bytes':disk,'candidate_sites':args.sites,'records':sorted(records,key=lambda x:x['site']),'errors':errors},indent=2),encoding='utf-8')
        print('DISCOVERY='+str(path),flush=True);return
    have=existing_records();reused=[];jobs=[];skipped=[]
    discovered={}
    for f in sorted((WORK/'datasets').glob('extended_discovery_*.json')):
        for rec in json.loads(f.read_text(encoding='utf-8'))['records']:discovered[rec['site']]=rec
    for site in args.sites:
        for year in args.years:
            if (site,year) in have:reused.append(have[(site,year)])
            elif args.limit_to_known_nox_span and site in discovered and not any(int(s['begin'][:4])<=year<=int(s['end'][:4]) for s in discovered[site]['nox_spans']):
                skipped.append({'site':site,'year':year,'reason':'wholly_outside_official_nox_record_span'})
            else:jobs.append((site,year))
    # Cap is enforced per result, with at most workers outstanding responses.
    # Expected volume per site-year is ~5MB; concurrent overshoot is documented.
    completed=[];errors=[];response_bytes=0
    checkpoint=WORK/'datasets'/f'extended_acquisition_{stamp}.json'
    def save_checkpoint():
        checkpoint.write_text(json.dumps({'created_utc':now(),'raw_run':str(run_dir),'storage_free_bytes':disk,'requested_sites':args.sites,'years':args.years,'reused_downloads':reused,'downloads':completed,'skipped_by_metadata':skipped,'errors':errors,'new_response_bytes':response_bytes,'remaining_jobs':[{'site':s,'year':y} for s,y in jobs if (s,y) not in {(v['site'],v['year']) for v in completed}]},indent=2),encoding='utf-8')
    # Complete station batches so preparation can proceed while later sites run.
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for offset in range(0,len(jobs),args.workers):
            if response_bytes>args.max_new_response_mb*1e6:break
            batch=jobs[offset:offset+args.workers]
            fs={ex.submit(download_year,s,y,run_dir):(s,y) for s,y in batch}
            for future in as_completed(fs):
                site,year=fs[future]
                try:
                    rec=future.result();completed.append(rec);response_bytes+=rec['response_bytes']
                except Exception as e:
                    errors.append({'site':site,'year':year,'error':repr(e)})
                save_checkpoint()
    save_checkpoint()
    print('EXTENDED_MANIFEST='+str(checkpoint),flush=True)
    print(json.dumps({'new_records':len(completed),'reused_records':len(reused),'new_response_mb':response_bytes/1e6,'errors':errors}),flush=True)

if __name__=='__main__':main()
