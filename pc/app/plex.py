# -*- coding: utf-8 -*-
"""Fer sonar discos i temes al Plexamp a través del servidor Plex del NAS.

Com funciona (protocol de control remot de Plex, el mateix que fan servir les apps de Plex):
1. Es busca el disc a la biblioteca de música del Plex (artista i títol) i es comprova amb la carpeta
   del NAS («/Mi Musica/<carpeta>/» a la ruta dels arxius). La relació es desa a dades/plex.json.
2. Es crea una cua de reproducció al servidor (POST /playQueues), començant pel tema triat.
3. S'envia l'ordre «playMedia» al Plexamp triat (port 32500 de l'aparell), que la reprodueix.

La clau (plex_token) l'escriu l'Ignasi al config.ini i no surt mai ni a la pàgina ni al registre."""
import json, os, re, subprocess, time, uuid, urllib.error, urllib.parse, urllib.request

import comu
from comu import llegeix, desa, log, BLOC

PROD = 'com.plexapp.plugins.library'
_ESTAT = {'mid': None, 'seccio': None, 'cmd': int(time.time()) % 100000}


def _cfg():
    c = comu.config()
    tok = str(c.get('plex_token', '') or '').strip()
    adr = str(c.get('plex_adreca', '') or '').strip()
    if not adr:
        nas = comu.adreca_nas() or ''
        adr = (nas.split(':')[0] if nas else '192.168.0.27') + ':32400'
    return tok, adr


def configurat():
    return bool(_cfg()[0])


def _amaga(s):
    tok = _cfg()[0]
    return str(s).replace(tok, '***') if tok else str(s)


def _req(url, method='GET', headers=None, timeout=8):
    tok, _ = _cfg()
    h = {'Accept': 'application/json', 'X-Plex-Token': tok,
         'X-Plex-Client-Identifier': 'discoteca-' + uuid.uuid5(uuid.NAMESPACE_DNS, os.environ.get('COMPUTERNAME', 'pc')).hex[:12],
         'X-Plex-Product': 'Discoteca', 'X-Plex-Device-Name': 'Discoteca', 'X-Plex-Version': '1.0'}
    h.update(headers or {})
    r = urllib.request.Request(url, method=method, headers=h)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            b = f.read()
        try:
            return json.loads(b) if b.strip() else {}
        except ValueError:
            return {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Plex ha respost {e.code}') from None
    except Exception as e:
        raise RuntimeError(_amaga(e)) from None


def _srv(path, **kw):
    return _req('http://' + _cfg()[1] + path, **kw).get('MediaContainer', {})


def _mid():
    if not _ESTAT['mid']:
        _ESTAT['mid'] = _srv('/identity').get('machineIdentifier')
    return _ESTAT['mid']


def _seccio():
    """La biblioteca de música (la primera de tipus «artist»)."""
    if not _ESTAT['seccio']:
        for s in _srv('/library/sections').get('Directory', []) or []:
            if s.get('type') == 'artist':
                _ESTAT['seccio'] = s.get('key')
                break
    return _ESTAT['seccio']


def reproductors():
    """Els Plexamp i altres reproductors que el servidor veu ara mateix."""
    out = []
    for c in _srv('/clients').get('Server', []) or []:
        if 'playback' not in (c.get('protocolCapabilities') or ''):
            continue
        out.append({'id': c.get('machineIdentifier'), 'nom': c.get('name'), 'app': c.get('product'),
                    'url': f"http://{c.get('host')}:{c.get('port') or 32500}"})
    pc = (os.environ.get('COMPUTERNAME') or '').replace('-', ' ').lower()
    for r in out:
        r['pc'] = bool(pc) and r['nom'] and r['nom'].replace('-', ' ').lower() == pc
    return out


def obre_plexamp():
    """Si el Plexamp del PC és tancat, l'obre (si es troba l'executable)."""
    for ruta in (os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Plexamp', 'Plexamp.exe'),):
        if os.environ.get('LOCALAPPDATA') and os.path.isfile(ruta):
            subprocess.Popen([ruta], creationflags=0x08000000 if os.name == 'nt' else 0)
            return True
    return False


# ---------- trobar el disc al Plex ----------
def _n(s):
    return comu.NT(s)


def _temes_plex(rk):
    return _srv(f'/library/metadata/{rk}/children').get('Metadata', []) or []


def _encaixa_carpeta(temes, carpeta):
    if not carpeta:
        return None
    c = '/' + carpeta.strip().lower() + '/'
    for t in temes:
        for m in t.get('Media', []) or []:
            for p in m.get('Part', []) or []:
                f = (p.get('file') or '').replace('\\', '/').lower()
                if f:
                    return c in f
    return None


def album(d, artista):
    """ratingKey de l'àlbum del Plex que correspon al disc (i el desa a dades/plex.json)."""
    mapa = llegeix('plex.json', {})
    k = str(d.get('id'))
    if mapa.get(k, {}).get('rk'):
        return mapa[k]['rk']
    sec = _seccio()
    if not sec:
        raise RuntimeError('No trobo la biblioteca de música al Plex')
    titol = d.get('titol') or ''
    cands = []
    for cerca in dict.fromkeys([titol, comu.titol_net(titol)[0]]):
        if cerca:
            q = urllib.parse.urlencode({'type': 9, 'title': cerca})
            cands += _srv(f'/library/sections/{sec}/all?{q}').get('Metadata', []) or []
    # si el Plex té el disc amb un altre títol, es miren tots els discos de l'artista (la carpeta mana)
    q = urllib.parse.urlencode({'type': 8, 'title': artista or ''})
    for art in (_srv(f'/library/sections/{sec}/all?{q}').get('Metadata', []) or [])[:3] if artista else []:
        if comu.N(art.get('title')) == comu.N(artista):
            cands += _srv(f"/library/metadata/{art['ratingKey']}/children").get('Metadata', []) or []
    vist, millor = set(), None
    for a in cands:
        if a.get('ratingKey') in vist or a.get('type', 'album') != 'album':
            continue
        vist.add(a.get('ratingKey'))
        mateix_art = comu.N(a.get('parentTitle')) == comu.N(artista)
        mateix_tit = _n(a.get('title')) == _n(titol)
        ok = _encaixa_carpeta(_temes_plex(a['ratingKey']), d.get('carpeta'))
        if ok:
            millor = a
            break
        if ok is None and mateix_art and mateix_tit and not millor:
            millor = a
    if not millor:
        return None
    with BLOC:
        mapa = llegeix('plex.json', {})
        mapa[k] = {'rk': millor['ratingKey'], 'srv': _mid()}
        desa('plex.json', mapa)
    return millor['ratingKey']


def _tema(temes_plex, tema):
    """El tema del Plex que correspon a una fila [n, títol, compositor, cara/CD, ...] de la fitxa."""
    if not tema:
        return None
    disc = 1
    m = re.match(r'^(?:cd|disc)\s*(\d+)$', str(tema[3] if len(tema) > 3 else '').strip(), re.I)
    if m:
        disc = int(m.group(1))
    nt = _n(tema[1] if len(tema) > 1 else '')
    for t in temes_plex:
        if nt and _n(t.get('title')) == nt and int(t.get('parentIndex') or 1) == disc:
            return t
    for t in temes_plex:
        if nt and _n(t.get('title')) == nt:
            return t
    try:
        n = int(re.sub(r'\D', '', str(tema[0])) or 0)
    except ValueError:
        n = 0
    for t in temes_plex:
        if n and int(t.get('index') or 0) == n and int(t.get('parentIndex') or 1) == disc:
            return t
    return None


# ---------- fer sonar ----------
def reprodueix(d, artista, tema=None, desti=None):
    """Fa sonar el disc (o el disc a partir d'un tema) al reproductor `desti` (id) o al Plexamp del PC."""
    if not configurat():
        return {'ok': False, 'motiu': 'Falta la clau del Plex (plex_token) al config.ini'}
    rk = album(d, artista)
    if not rk:
        return {'ok': False, 'motiu': 'No trobo aquest disc al Plex'}
    temes = _temes_plex(rk)
    if _encaixa_carpeta(temes, d.get('carpeta')) is False:
        with BLOC:                                   # la relació desada ja no és bona: es torna a buscar
            mapa = llegeix('plex.json', {}); mapa.pop(str(d.get('id')), None); desa('plex.json', mapa)
        rk = album(d, artista)
        if not rk:
            return {'ok': False, 'motiu': 'No trobo aquest disc al Plex'}
        temes = _temes_plex(rk)
    inici = _tema(temes, tema)
    if tema and not inici:
        return {'ok': False, 'motiu': 'No trobo aquest tema al disc del Plex'}
    reps = reproductors()
    r = next((x for x in reps if x['id'] == desti), None) if desti else next((x for x in reps if x['pc']), None)
    if not r and not desti:
        if obre_plexamp():
            for _ in range(20):
                time.sleep(1)
                r = next((x for x in reproductors() if x['pc']), None)
                if r:
                    break
    if not r:
        return {'ok': False, 'motiu': 'El Plexamp no està obert (o no és a la xarxa de casa)'}
    mid = _mid()
    host, port = _cfg()[1].split(':')
    q = {'type': 'audio', 'uri': f'server://{mid}/{PROD}/library/metadata/{rk}', 'shuffle': 0, 'repeat': 0,
         'continuous': 0, 'includeChapters': 0, 'includeRelated': 0}
    if inici:
        q['key'] = inici['key']
    pq = _srv('/playQueues?' + urllib.parse.urlencode(q), method='POST')
    _ESTAT['cmd'] += 1
    cmd = {'providerIdentifier': PROD, 'machineIdentifier': mid, 'protocol': 'http', 'address': host, 'port': port,
           'offset': 0, 'key': (inici or (temes[0] if temes else {})).get('key', f'/library/metadata/{rk}'),
           'type': 'music', 'containerKey': f"/playQueues/{pq.get('playQueueID')}?window=100&own=1",
           'token': _cfg()[0], 'commandID': _ESTAT['cmd']}
    _req(f"{r['url']}/player/playback/playMedia?{urllib.parse.urlencode(cmd)}",
         headers={'X-Plex-Target-Client-Identifier': r['id']})
    log(f"Plex: «{artista} - {d.get('titol')}»{' des de «' + inici.get('title', '') + '»' if inici else ''} a {r['nom']}")
    return {'ok': True, 'on': 'Plexamp del PC' if r.get('pc') else r['nom']}


def mapeja_tots():
    """Relaciona tots els discos amb el seu àlbum del Plex (artista i títol iguals) i ho desa a dades/plex.json.
    Serveix per a l'enllaç «Obre al Plex» de la versió del mòbil. Una sola consulta al servidor."""
    if not configurat():
        return 0
    sec = _seccio()
    if not sec:
        return 0
    idx = {}
    for a in _srv(f'/library/sections/{sec}/all?type=9', timeout=60).get('Metadata', []) or []:
        idx.setdefault((comu.N(a.get('parentTitle')), _n(a.get('title'))), a.get('ratingKey'))
    mid = _mid()
    with BLOC:
        discs = llegeix('discs.json', [])
        arts = llegeix('artistes.json', {})
        mapa = llegeix('plex.json', {})
        nous = 0
        for d in discs:
            k = str(d.get('id'))
            if mapa.get(k, {}).get('rk'):
                continue
            rk = idx.get((comu.N(arts.get(str(d.get('artista')), '')), _n(d.get('titol'))))
            if rk:
                mapa[k] = {'rk': rk, 'srv': mid}
                nous += 1
        if nous:
            desa('plex.json', mapa)
    log(f'Plex: {nous} discos nous relacionats amb el Plex ({len(mapa)} en total)')
    return nous
