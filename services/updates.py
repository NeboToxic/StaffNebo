import hashlib
import re
from pathlib import Path
import requests
from config import VERSION


def version_tuple(text):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)',text)
    if not match:raise ValueError('Неподдерживаемый номер версии')
    return tuple(int(x) for x in match.groups())


def check_update(repository,cancel=lambda:False):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository.strip()):
        raise ValueError('Укажите репозиторий GitHub в формате owner/repository')
    repo=repository.strip()
    response=requests.get(f'https://api.github.com/repos/{repo}/releases/latest',timeout=(5,20),headers={'Accept':'application/vnd.github+json','User-Agent':'NeboProject/'+VERSION})
    if response.status_code==404:raise RuntimeError('Репозиторий или опубликованный релиз не найден. Для проверки нужен публичный GitHub Release.')
    response.raise_for_status();data=response.json()
    if cancel():raise RuntimeError('Проверка отменена')
    tag=data['tag_name'];new=version_tuple(tag)>version_tuple(VERSION)
    assets=data.get('assets',[])
    candidates=[a for a in assets if a['name'].endswith('-Windows.zip')]
    checksums=next((a for a in assets if a['name']=='SHA256SUMS.txt'),None)
    if new and (not candidates or not checksums):raise RuntimeError('В релизе отсутствуют Windows ZIP или SHA256SUMS.txt')
    asset=candidates[0] if candidates else None
    for item in (asset,checksums):
        if item and not item.get('browser_download_url','').startswith(f'https://github.com/{repo}/releases/download/'):
            raise RuntimeError('Недопустимый адрес файла обновления')
    return {'new':new,'tag':tag,'notes':data.get('body','')[:12000],
            'asset':asset,'checksums':checksums,'repository':repo}


def download_update(info,destination,cancel=lambda:False,progress=lambda _:None):
    asset=info['asset'];path=Path(destination)
    if not asset or not info['new']:raise ValueError('Нет новой версии для скачивания')
    sums=requests.get(info['checksums']['browser_download_url'],timeout=(5,20));sums.raise_for_status()
    expected=None
    for line in sums.text.splitlines():
        parts=line.split()
        if len(parts)>=2 and parts[1].lstrip('*')==asset['name'] and re.fullmatch(r'[0-9a-fA-F]{64}',parts[0]):expected=parts[0].lower()
    if not expected:raise RuntimeError('В SHA256SUMS.txt нет контрольной суммы выбранного ZIP')
    temporary=path.with_name(path.name+'.part')
    digest=hashlib.sha256();count=0;size=int(asset.get('size',0))
    if size>300*1024*1024:raise ValueError('Файл обновления превышает 300 МБ')
    try:
        with requests.get(asset['browser_download_url'],stream=True,timeout=(5,30)) as response:
            response.raise_for_status()
            with temporary.open('wb') as file:
                for chunk in response.iter_content(256*1024):
                    if cancel():raise RuntimeError('Скачивание отменено')
                    if chunk:
                        count+=len(chunk)
                        if count>300*1024*1024:raise RuntimeError('Файл превышает допустимый размер')
                        file.write(chunk);digest.update(chunk)
                        if size:progress(min(99,int(count*100/size)))
        if size and count!=size:raise RuntimeError('Размер скачанного файла не совпадает с релизом')
        if digest.hexdigest()!=expected:raise RuntimeError('SHA-256 не совпадает. Файл удалён; обновление не принято.')
        temporary.replace(path);progress(100)
        return str(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
