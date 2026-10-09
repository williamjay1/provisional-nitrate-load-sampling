"""Past-only model contexts for the full-paper experiment; original pilot untouched."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('JOBLIB_TEMP_FOLDER',str(ROOT/'temp'))
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from replay import causal_features,tree_predictions,define_events,historical_design_days

ORIGINAL_SITES={'03346500','03374100','05447500','05465500','05482000','05484500','05595000','07144100'}
RF_SPEC=dict(n_estimators=64,max_depth=12,min_samples_leaf=16,n_jobs=4)

def frame_digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(2**20),b''):h.update(block)
    return h.hexdigest()

def select_training_indices(mask,seed,max_points=12000):
    ix=np.flatnonzero(mask)
    if len(ix)>max_points:
        ix=np.sort(np.random.default_rng(seed).choice(ix,max_points,replace=False))
    return ix

def fit_context(data:pd.DataFrame,site:str,year:int,seed:int,history_years=3):
    """Target labels are returned as an environment table; never used in model fit."""
    start_clock=time.perf_counter()
    part=data.loc[data.site.astype(str)==site].copy()
    start=pd.Timestamp(f'{year-history_years}-01-01',tz='UTC')
    end=pd.Timestamp(f'{year+1}-01-01',tz='UTC')
    full=pd.date_range(start,end,freq='h',inclusive='left')
    if part.time_utc.duplicated().any():raise ValueError(f'Duplicate site time {site}')
    frame=part.set_index('time_utc').reindex(full).rename_axis('time_utc').reset_index()
    frame['site']=site
    yrs=frame.time_utc.dt.year.to_numpy()
    hist=yrs<year
    y=frame.nox_at_time_mg_l.to_numpy(float)
    valid=(frame.nox_sample_reference_ok.fillna(False).to_numpy(bool)
           &frame.q_sample_reference_ok.fillna(False).to_numpy(bool)
           &np.isfinite(y)&(y>=0)&frame.q_at_time_cms.notna().to_numpy())
    available={int(k):int(np.sum(valid&(yrs==k))) for k in np.unique(yrs[hist])}
    sufficiently_observed=[k for k,n in available.items() if n>=1000]
    if len(sufficiently_observed)<2:
        return {'site':site,'year':year,'seed':seed,'status':'insufficient_history','history_valid_counts':available}
    q_hist=frame.q_at_time_cms.where(frame.q_sample_reference_ok.fillna(False))
    qscale=float(q_hist[hist].median())
    if not np.isfinite(qscale) or qscale<=0:
        return {'site':site,'year':year,'seed':seed,'status':'insufficient_discharge'}
    features=causal_features(frame,qscale)
    cal_year=max(sufficiently_observed)
    calibration=valid&(yrs==cal_year)
    early=valid&(yrs<cal_year)
    early_ix=select_training_indices(early,seed)
    cal_ix=select_training_indices(calibration,seed,max_points=4000)
    calibration_model=RandomForestRegressor(**RF_SPEC,random_state=seed)
    calibration_model.fit(features.iloc[early_ix],y[early_ix])
    residuals=y[cal_ix]-calibration_model.predict(features.iloc[cal_ix])
    noise_floor=max(.02*float(np.nanmean(y[valid&hist])),.02)**2
    noise_variance=max(float(np.mean(residuals**2)),noise_floor)
    train_ix=select_training_indices(valid&hist,seed)
    model=RandomForestRegressor(**RF_SPEC,random_state=seed)
    model.fit(features.iloc[train_ix],y[train_ix])
    base,disagreement=tree_predictions(model,features)
    target_mask=yrs==year
    target=frame.loc[target_mask].reset_index(drop=True)
    q90=float(q_hist[hist].quantile(.90))
    events=define_events(target.q_at_time_cms.to_numpy(float),q90,24,12)
    leverage,design_info,design_order=historical_design_days(frame.loc[hist])
    return {'status':'ready','site':site,'year':year,'seed':seed,'target':target,
            'history':frame.loc[hist].reset_index(drop=True),'q_scale':qscale,
            'target_base':base[target_mask],'target_disagreement':disagreement[target_mask],
            'history_base':base[hist],'history_disagreement':disagreement[hist],
            'target_features':features.loc[target_mask].reset_index(drop=True),
            'history_features':features.loc[hist].reset_index(drop=True),
            'events':events,'design_order':design_order,'leverage':leverage,
            'audit':{'history_valid_counts':available,'calibration_year':cal_year,
                     'calibration_early_labels':len(early_ix),'calibration_labels':len(cal_ix),
                     'noise_variance_forward_mse':noise_variance,'noise_floor':noise_floor,
                     'calibration_bias':float(residuals.mean()),'training_labels':len(train_ix),
                     'training_last_timestamp':str(frame.loc[hist,'time_utc'].max()),
                     'q90':q90,'q_scale':qscale,'rf_spec':RF_SPEC,
                     'design':design_info,'fit_seconds':time.perf_counter()-start_clock}}

def load_context(data,site,year,seed,source_digest):
    code_digest=hashlib.sha256(Path(__file__).read_bytes()+(ROOT/'scripts/replay.py').read_bytes()).hexdigest()[:12]
    cache=ROOT/'cache'/'paper_contexts'/f'{source_digest[:12]}_{code_digest}'
    cache.mkdir(parents=True,exist_ok=True)
    path=cache/f'{site}_{year}_{seed}.joblib'
    if path.exists():return joblib.load(path)
    result=fit_context(data,site,year,seed)
    temp=path.with_suffix('.tmp')
    joblib.dump(result,temp,compress=2)
    temp.replace(path)
    return result
