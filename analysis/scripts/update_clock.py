from pathlib import Path
r=Path(__file__).resolve().parents[1]/'manuscript'
p=r/'Methods.md';s=p.read_text(encoding='utf-8')
s=s.replace('An analyst issued a provisional hourly concentration estimate and associated transport estimate, using only information available by that hour.', 'An analyst issued a provisional concentration estimate at the start of each hour using only information then available. That fixed concentration was combined with discharge as it was subsequently observed to accumulate transport; the complete hourly mass became evaluable after its discharge intervals elapsed.')
s=s.replace('all finite nonnegative observed native discharge values, including estimated or provisional values, subject to the documented interval assumptions', 'all finite nonnegative quarter-hour-grid discharge readings, each weighted by 900 s regardless of concentration availability, including estimated or provisional discharge values')
p.write_text(s,encoding='utf-8')
p=r/'Results.md';s=p.read_text(encoding='utf-8')
anchor='A historical model or pre-event sample can still provide information during these intervals.'
s=s.replace(anchor,anchor+' Actual policy returns gave a different timing summary: at temporal budget 96, the equal-station mean fraction of event reference mass before the first usable arrival was 48.13% for value and 46.97% for flow. No usable result arrived within the event for an equal-station mean 22.80% and 18.27% of events, respectively. Those cases can retain information from results returned before onset; the no-arrival indicator does not imply no concentration information.')
p.write_text(s,encoding='utf-8')
