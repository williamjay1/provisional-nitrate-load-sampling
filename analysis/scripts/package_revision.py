"""Package immutable scientific lineage and final reviewable revision assets."""
from pathlib import Path
import json,hashlib,zipfile
R=Path(__file__).resolve().parents[1];P=R.parent;D=R/'delivery'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(2**20),b''):h.update(b)
    return h.hexdigest()
def record(p,name):return {'path':name,'bytes':p.stat().st_size,'sha256':sha(p)}
def write_archive(dest,items,comment):
    assert not dest.exists(),'Use a new package version rather than replacing an archive.'
    rows=[record(p,n) for p,n in items]
    manifest={'version':'revision_20261009','note':comment,'files':rows}
    with zipfile.ZipFile(dest,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p,n in items:z.write(p,n,compress_type=zipfile.ZIP_STORED if p.suffix in ['.zip','.gz'] else zipfile.ZIP_DEFLATED)
        z.writestr('PACKAGE_CONTENTS.json',json.dumps(manifest,indent=2))
    with zipfile.ZipFile(dest) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(items)+1
        for x in rows:
            assert hashlib.sha256(z.read(x['path'])).hexdigest()==x['sha256'],x['path']
    return {'name':dest.name,'bytes':dest.stat().st_size,'sha256':sha(dest),'included_files':len(items)+1,'crc_and_all_entry_hashes':'PASS'}

visual=json.loads((R/'docs/FINAL_VISUAL_RELEASE.json').read_text(encoding='utf-8'))
audit=json.loads((R/'docs/DELIVERY_AUDIT.json').read_text(encoding='utf-8'))
assert visual['status']==audit['status']=='PASS'
assert visual['document_sha256']==audit['document_sha256']==sha(D/'Revised_River_Nutrient_Monitoring_Manuscript.docx')
assert visual['manuscript_sha256']==audit['manuscript_sha256']==sha(R/'manuscript/manuscript.md')
assert visual['pages']==36
readme='''# Final scientific figures and tables

Six main figures, five supplementary figures and vector companions to three main tables are supplied. Every figure/table has a genuine vector PDF and editable-text SVG, and a native 1200 dpi PNG at 183 mm width. Vector output does not have a DPI setting; the separate raster exceeds the requested 900 dpi. PDF/SVG contain no raster image objects. Word retains native editable tables and equations.

Figure design follows inspected Nature official figure guidance and the GitHub SciencePlots nature style, with Arial typography, consistent colour/shape identities, independent legends and uncluttered panels. The existing plotting environment actually applies SciencePlots; no new GitHub repository code was installed. Sources: https://github.com/garrettj403/SciencePlots ; https://github.com/callumrollo/cmcrameri ; https://research-figure-guide.nature.com/figures/building-and-exporting-figure-panels/ ; https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/ . Exact inspected commits and detailed export/layout checks are in FIGURE_DESIGN.md.

All assets were drawn from actual completed result files, checked for full data bounds and text/line conflicts, and individually visually inspected from final PDF renders. Original scientific failures and uncertainty remain visible. Source data and the full computation environment are provided in the separate revised reproducibility archive; scripts and table-cell sources accompany this artwork bundle.
'''
(D/'README_figures.md').write_text(readme,encoding='utf-8')
assets=[]
for sub in ['main','supplement','tables']:
    for p in sorted((R/'figures'/sub).glob('*')):
        if p.is_file() and '_preview' not in p.name and '_FAILED' not in p.name:
            assets.append((p,'figures/'+sub+'/'+p.name))
assets += [(R/'figures/final_figures_manifest.json','figures/final_figures_manifest.json'),
    (R/'docs/FIGURE_DESIGN.md','FIGURE_DESIGN.md'),(R/'docs/DELIVERY_AUDIT.json','DELIVERY_AUDIT.json'),
    (D/'README_figures.md','README.md'),(R/'manuscript/table_source.json','table_source.json'),
    (R/'scripts/plot_revision.py','scripts/plot_revision.py'),(R/'scripts/export_main_tables.py','scripts/export_main_tables.py'),
    (R/'support/figstyle.py','support/figstyle.py')]
reports=[write_archive(D/'Revised_Nature_Style_Figures_1200dpi.zip',assets,'Final vector artwork; source figures unchanged from the independently inspected freeze.')]
original=P/'delivery/reproducibility_archive.zip'
assert sha(original)=='195fafdc89c35e24027bce9266c24525edb343bb64ac441fd3dd2ef2d207d094'
items=[(original,'original_frozen/reproducibility_archive.zip'),
       (R/'README_revised_reproducibility.md','README.md'),(R/'ENVIRONMENT_REVISION.json','ENVIRONMENT_REVISION.json')]
for directory in ['scripts','docs','manuscript','support','figures','results']:
    for p in sorted((R/directory).rglob('*')):
        if not p.is_file():continue
        rel=p.relative_to(R)
        if p.name in ['refine_methods.py','update_clock.py']:continue
        if '__pycache__' in rel.parts or '_qa' in rel.parts:continue
        if '_FAILED' in p.name or '_preview' in p.name:continue
        if any('debug' in part for part in rel.parts):continue
        items.append((p,'revision_20261009/'+rel.as_posix()))
unit=json.loads((R/'results/context_unit_audit.json').read_text(encoding='utf-8'))
for x in unit['source_files']:
    p=Path(x['path']);assert sha(p)==x['sha256']
    items.append((p,'source_unit_records/'+p.name))
assert len(set(n for _,n in items))==len(items)
reports.append(write_archive(D/'Revised_Reproducibility_Archive.zip',items,'Original freeze retained unchanged; every revised experiment is post-result. Debug/layout fixtures are excluded.'))
report={'status':'PASS','manuscript':record(D/'Revised_River_Nutrient_Monitoring_Manuscript.docx','Revised_River_Nutrient_Monitoring_Manuscript.docx'),
    'packages':reports,'original_archive_preserved':True,'raw_unit_responses_preserved':True}
(D/'FINAL_DELIVERY_MANIFEST.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
