"""Vector companion tables from exactly the native Word source cells."""
from pathlib import Path
import json,hashlib,textwrap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from PIL import Image
R=Path(__file__).resolve().parents[1];out=R/'figures/tables';out.mkdir(exist_ok=True)
plt.rcParams.update({'font.family':'Arial','font.size':7.5,'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none','text.color':'black','savefig.facecolor':'white'})
tables=json.loads((R/'manuscript/table_source.json').read_text(encoding='utf-8'))[:3]
widths=[[43,29,29,28,24,30],[42,23.5,23.5,23.5,23.5,23.5,23.5],[22,29,36,36,30,30]]
reports=[]
for n,(data,ws) in enumerate(zip(tables,widths),1):
    ws=[v*177/sum(ws) for v in ws]
    rowh=8 if n==1 else 7;headh=15 if n!=2 else 10
    height=headh+rowh*(len(data)-1)+6
    fig=plt.figure(figsize=(183/25.4,height/25.4));ax=fig.add_axes([0,0,1,1]);ax.set_xlim(0,183);ax.set_ylim(height,0);ax.axis('off')
    tops=3;texts=[];x=3
    for j,(label,w) in enumerate(zip(data[0],ws)):
        wrap=max(8,int(w*2.83465/4.2))
        if n==2 and j>0:label=label.replace(' ','\n',1)
        else:label='\n'.join(textwrap.wrap(label,width=wrap,break_long_words=False))
        texts.append(ax.text(x+(1.5 if j<2 else w/2),tops+headh/2,label,ha='left' if j<2 else 'center',va='center',weight='bold',fontsize=7.5))
        x+=w
    for i,row in enumerate(data[1:]):
        x=3
        for j,(label,w) in enumerate(zip(row,ws)):
            texts.append(ax.text(x+(1.5 if j<2 else w/2),tops+headh+(i+.5)*rowh,label,ha='left' if j<2 else 'center',va='center',fontsize=7.5));x+=w
    lines=[tops,tops+headh,tops+headh+(len(data)-1)*rowh]
    for i,y in enumerate(lines):ax.plot([3,180],[y,y],color='black',lw=.75 if i!=1 else .45)
    fig.canvas.draw();renderer=fig.canvas.get_renderer();boxes=[t.get_window_extent(renderer) for t in texts]
    issues=[]
    for i,b in enumerate(boxes):
        for j,c in enumerate(boxes[i+1:],i+1):
            if b.overlaps(c):issues.append(('text_overlap',i,j))
        for y in lines:
            yp=ax.transData.transform((0,y))[1]
            if b.y0-.5<yp<b.y1+.5:issues.append(('text_rule_crossing',i,y))
    assert not issues,(n,issues)
    stem=out/f'Table{n}'
    for ext in ['pdf','svg']:fig.savefig(stem.with_suffix('.'+ext),bbox_inches=None)
    fig.savefig(stem.with_suffix('.png'),dpi=1200,bbox_inches=None)
    fig.savefig(out/f'Table{n}_preview.png',dpi=180,bbox_inches=None);plt.close(fig)
    assert '<image' not in stem.with_suffix('.svg').read_text(encoding='utf-8')
    im=Image.open(stem.with_suffix('.png'))
    report={'table':n,'status':'PASS','cells':sum(map(len,data)),'width_mm':183.0,'height_mm':height,'png_pixels':list(im.size),'png_dpi':im.info.get('dpi'),'text_overlaps':0,'text_line_crossings':0,'vector_raster_images':0,'source_sha256':hashlib.sha256((R/'manuscript/table_source.json').read_bytes()).hexdigest()}
    (out/f'Table{n}.qa.json').write_text(json.dumps(report,indent=2));reports.append(report)
(out/'tables_manifest.json').write_text(json.dumps(reports,indent=2));print(json.dumps(reports,indent=2))
