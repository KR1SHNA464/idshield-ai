"""Build the in-app source download without secrets, databases, or build recursion."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root=Path(__file__).resolve().parents[1]
out=root/'public/downloads/IDShield-AI-source.zip';out.parent.mkdir(parents=True,exist_ok=True)
excluded={'node_modules','.git','.wrangler','dist','desktop-dist','data','__pycache__','.pytest_cache','build','downloads'}
with ZipFile(out,'w',ZIP_DEFLATED) as z:
    for f in root.rglob('*'):
        rel=f.relative_to(root)
        if not f.is_file() or any(p in excluded for p in rel.parts):continue
        if f.name=='.env' or f.suffix in {'.exe','.spec','.key','.db','.pyc'}:continue
        z.write(f,Path('IDShield-AI')/rel)
print(out)
