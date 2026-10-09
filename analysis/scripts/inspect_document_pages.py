from pathlib import Path
import json,sys
from pypdf import PdfReader
root=Path(sys.argv[1]);p=list(root.glob('*.pdf'))[0]
reader=PdfReader(p);rows=[]
for i,page in enumerate(reader.pages,1):
    text=page.extract_text();heads=[s for s in text.splitlines() if s.startswith(('Table ','Fig. ','Online Resource','Results','Discussion','References'))]
    rows.append({'page':i,'chars':len(text),'headings':heads,'first':text[:110]})
(root/'page_inventory.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
