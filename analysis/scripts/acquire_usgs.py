"""Download immutable USGS sensor inputs. No training/analysis is written to raw.

USGS legacy IV API retains qualifier details; current OGC API supplies interval
measurement methods, which distinguish in-situ UV instruments from proxy models.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import requests

WORK = Path('D:/MLWork/NitrateAdaptiveSampling_20261005')
RAW = Path('F:/AcademicData/NitrateAdaptiveSampling_20261005/raw')
BASE = 'https://api.waterdata.usgs.gov/ogcapi/v1/collections'
DEFAULT_SITES = ['05484500', '05465500', '05482000', '03374100', '05447500', '05595000']

def fetch(url, params):
    for trial in range(4):
        try:
            r = requests.get(url, params=params, timeout=(25, 150))
            r.raise_for_status()
            j = r.json()
            return r, j
        except (requests.RequestException, ValueError):
            if trial == 3:
                raise
            time.sleep(2 ** trial)

def immutable_save(path, content):
    """Create once; do not edit, replace, chmod, move or delete existing raw."""
    with path.open('xb') as f:
        f.write(content)
    path.chmod(stat.S_IREAD)

def metadata(site, run_dir):
    saved, series = [], []
    for parameter in ['99133', '00060']:
        r, j = fetch(BASE + '/time-series-metadata/items',
                     {'f': 'json', 'monitoring_location_id': 'USGS-' + site,
                      'parameter_code': parameter, 'limit': 100})
        p = run_dir / f'{site}_{parameter}_series_metadata.json'
        immutable_save(p, r.content)
        saved.append({'path': str(p), 'url': r.url, 'bytes': len(r.content)})
        for f in j.get('features', []):
            props = f['properties']
            if props.get('computation_period_identifier') != 'Points':
                continue
            mid = props['id']
            r2, j2 = fetch(BASE + '/time-series-methods/items',
                           {'f': 'json', 'time_series_id': mid, 'limit': 100})
            p2 = run_dir / f'{site}_{parameter}_{mid}_methods.json'
            immutable_save(p2, r2.content)
            saved.append({'path': str(p2), 'url': r2.url, 'bytes': len(r2.content)})
            methods = []
            for method in j2.get('features', []):
                interval = method['properties']
                code = interval['method_id']
                r3, j3 = fetch(BASE + '/methods/items/' + code, {'f': 'json'})
                p3 = run_dir / f'{site}_{parameter}_{mid}_{code}_definition.json'
                if not p3.exists():
                    immutable_save(p3, r3.content)
                    saved.append({'path': str(p3), 'url': r3.url, 'bytes': len(r3.content)})
                methods.append({'interval': interval, 'definition': j3.get('properties')})
            series.append({'series': props, 'geometry': f.get('geometry'), 'methods': methods})
    return {'site': site, 'series': series, 'raw_files': saved}

def download_year(site, year, run_dir):
    # UTC interval includes first point of next year for future boundary checks.
    r, j = fetch('https://waterservices.usgs.gov/nwis/iv/',
                 {'format': 'json', 'sites': site, 'parameterCd': '00060,99133',
                  'startDT': f'{year}-01-01T00:00:00Z',
                  'endDT': f'{year+1}-01-01T00:00:00Z', 'siteStatus': 'all'})
    content = gzip.compress(r.content, compresslevel=6, mtime=0)
    path = run_dir / f'{site}_{year}_iv.json.gz'
    immutable_save(path, content)
    summary = []
    for ts in j.get('value', {}).get('timeSeries', []):
        summary.append({'parameter': ts['variable']['variableCode'][0]['value'],
                        'site_name': ts['sourceInfo']['siteName'],
                        'n': sum(len(v['value']) for v in ts['values']),
                        'method': [v.get('method') for v in ts['values']]})
    rec = {'site': site, 'year': year, 'path': str(path), 'url': r.url,
           'retrieved_utc': datetime.now(timezone.utc).isoformat(),
           'sha256': hashlib.sha256(content).hexdigest(),
           'compressed_bytes': len(content), 'response_bytes': len(r.content),
           'series_summary': summary}
    print(json.dumps({'downloaded': site, 'year': year,
                      'megabytes': round(len(r.content)/1e6, 2), 'series': summary}), flush=True)
    return rec

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sites', nargs='+', default=DEFAULT_SITES)
    p.add_argument('--years', nargs='+', type=int, default=[2021, 2022, 2023, 2024])
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--locations-only', action='store_true', help='Archive official location metadata without downloading observations')
    a = p.parse_args()
    for folder in [WORK/'temp', WORK/'cache', WORK/'datasets', RAW]:
        folder.mkdir(parents=True, exist_ok=True)
    os.environ['TEMP'] = os.environ['TMP'] = str(WORK/'temp')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run_dir = RAW / ('usgs_' + stamp)
    run_dir.mkdir(exist_ok=False)
    if a.locations_only:
        locations=[]
        for site in a.sites:
            r,j=fetch(BASE+'/monitoring-locations/items/USGS-'+site,{'f':'json'})
            path=run_dir/f'{site}_location.json'
            immutable_save(path,r.content)
            locations.append({'site':site,'path':str(path),'url':r.url,
                              'sha256':hashlib.sha256(r.content).hexdigest(),
                              'data':j})
        out=WORK/'datasets'/f'location_manifest_{stamp}.json'
        out.write_text(json.dumps(locations,indent=2),encoding='utf-8')
        print('LOCATIONS='+str(out),flush=True)
        return
    meta = []
    for site in a.sites:
        rec = metadata(site, run_dir)
        meta.append(rec)
        print(json.dumps({'metadata': site, 'methods': [m['definition'] for s in rec['series'] if s['series']['parameter_code']=='99133' for m in s['methods']]}), flush=True)
    jobs = [(s, y, run_dir) for s in a.sites for y in a.years]
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        records = list(pool.map(lambda x: download_year(*x), jobs))
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(),
                'raw_run': str(run_dir), 'sites': a.sites, 'years': a.years,
                'metadata': meta, 'downloads': records}
    output = WORK/'datasets'/f'acquisition_manifest_{stamp}.json'
    output.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('MANIFEST=' + str(output), flush=True)
    print('RAW_RESPONSE_MB=' + str(sum(r['response_bytes'] for r in records)/1e6), flush=True)

if __name__ == '__main__':
    main()
