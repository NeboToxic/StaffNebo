"""Package the compiled executable and clean source."""
import hashlib
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from config import VERSION

def package():
    exe=ROOT/'dist/NeboProject.exe'
    if not exe.is_file():raise SystemExit('Build dist/NeboProject.exe first')
    out=ROOT/'release';out.mkdir(exist_ok=True)
    archives=[]
    windows=out/f'NeboProject-{VERSION}-Windows.zip'
    with ZipFile(windows,'w',ZIP_DEFLATED) as z:
        z.write(exe,'NeboProject.exe')
        for name in ('README.md','CHANGELOG.md','BUILD_README.txt','TEST_RESULTS.txt','GUI_TEST_RESULTS.txt'):
            path=ROOT/name
            if path.is_file():z.write(path,name)
    archives.append(windows)
    source=out/f'NeboProject-{VERSION}-Source.zip'
    excluded={'build','dist','release','__pycache__','.git','.venv','venv','data','screenshots','.pytest_cache','.mypy_cache'}
    allowed={'.py','.md','.txt','.bat','.spec','.yml','.yaml','.png','.jpg','.jpeg','.ico','.wav','.mp3','.qss','.qrc','.svg'}
    with ZipFile(source,'w',ZIP_DEFLATED) as z:
        for path in sorted(ROOT.rglob('*')):
            rel=path.relative_to(ROOT)
            if not path.is_file() or any(part in excluded for part in rel.parts):continue
            if path.suffix.lower() not in allowed and path.name!='.gitignore':continue
            z.write(path,Path(f'NeboProject-{VERSION}')/rel)
    archives.append(source)
    lines=[hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name for path in archives]
    (out/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='ascii')
    for path in archives:
        with ZipFile(path) as z:
            if z.testzip():raise SystemExit('Archive integrity check failed')
        print(path)
if __name__=='__main__':package()
