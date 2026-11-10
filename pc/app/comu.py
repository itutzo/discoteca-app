# -*- coding: utf-8 -*-
"""Funcions comunes de la Discoteca: rutes, lectura i escriptura segura de dades."""
import json, os, re, shutil, threading, time, unicodedata, configparser, datetime

ARREL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # ...\Discoteca
DADES = os.path.join(ARREL, 'dades')
CARATULES = os.path.join(ARREL, 'caratules')
COPIES = os.path.join(DADES, 'copies')
REGISTRE = os.path.join(DADES, 'registre.txt')
CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.discoteca')
CONFIG = os.path.join(CONFIG_DIR, 'config.ini')

for d in (DADES, CARATULES, COPIES):
    os.makedirs(d, exist_ok=True)

BLOC = threading.RLock()

PLANTILLA_CONFIG = """[discoteca]
# Usuari de Discogs i de Last.fm
usuari_discogs = itutzo
usuari_lastfm = itutzo

# Escriu aquí la teva clau personal de Discogs (Discogs > Settings > Developers > Generate new token)
discogs_token =

# Escriu aquí la teva API key de Last.fm (https://www.last.fm/api/account/create)
lastfm_key =

# Carpeta de música del NAS
carpeta_musica = C:\\SynologyMusic\\Mi Musica

# Adreça del NAS a casa (per no canviar noms d'arxius quan no hi ha connexió). Si es deixa buida, es busca sola
nas_adreca =

# Clau del Plex per fer sonar els discos al Plexamp (app.plex.tv > disc > ⋯ > Info > Mostra l'XML: el codi del final de l'adreça, després de «X-Plex-Token=»)
plex_token =

# Quants discos completa cada vegada
discos_per_tanda = 100
"""


def config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(CONFIG):
        with open(CONFIG, 'w', encoding='utf-8') as f:
            f.write(PLANTILLA_CONFIG)
    c = configparser.ConfigParser(interpolation=None)
    c.read(CONFIG, encoding='utf-8')
    return c['discoteca'] if 'discoteca' in c else {}


def clau_mobil():
    """Clau d'accés per al mòbil i la tauleta (es crea sola el primer cop)."""
    import secrets
    config()
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(CONFIG, encoding='utf-8')
    if not cp.has_section('discoteca'):
        cp.add_section('discoteca')
    k = cp.get('discoteca', 'clau_mobil', fallback='').strip()
    if not k:
        k = secrets.token_urlsafe(12)
        with open(CONFIG, 'a', encoding='utf-8') as f:
            f.write(f"\n# Clau perquè el mòbil i la tauleta puguin entrar (no la comparteixis)\nclau_mobil = {k}\n")
    return k


def ip_local():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('192.168.1.1', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


def llegeix(nom, defecte):
    p = os.path.join(DADES, nom)
    if not os.path.exists(p):
        return defecte
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def desa(nom, dades):
    """Escriu de manera atòmica i guarda una còpia diària."""
    with BLOC:
        p = os.path.join(DADES, nom)
        if os.path.exists(p):
            avui = datetime.date.today().isoformat()
            copia = os.path.join(COPIES, f'{nom[:-5]}-{avui}.json')
            if not os.path.exists(copia):
                try:
                    shutil.copy2(p, copia)
                    netejar_copies()
                except OSError:
                    pass
        tmp = p + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(dades, f, ensure_ascii=False, separators=(',', ':'))
        # Dropbox o l'antivirus poden tenir l'arxiu obert uns segons: ho tornem a provar
        for intent in range(20):
            try:
                os.replace(tmp, p)
                return
            except PermissionError:
                time.sleep(0.5 + intent * 0.5)
        # últim recurs: escriure-hi directament
        with open(p, 'w', encoding='utf-8') as f:
            json.dump(dades, f, ensure_ascii=False, separators=(',', ':'))
        try:
            os.remove(tmp)
        except OSError:
            pass


def netejar_copies(guardar=30):
    fitxers = sorted(os.listdir(COPIES))
    per_nom = {}
    for f in fitxers:
        per_nom.setdefault(f.rsplit('-', 3)[0], []).append(f)
    for llista in per_nom.values():
        for f in llista[:-guardar]:
            try:
                os.remove(os.path.join(COPIES, f))
            except OSError:
                pass


def obre_navegador(url):
    """Obre la pàgina amb Chrome (mai amb Edge, encara que sigui el navegador predeterminat del Windows)."""
    import subprocess, webbrowser
    for base in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'), os.environ.get('LOCALAPPDATA')):
        chrome = os.path.join(base or '', 'Google', 'Chrome', 'Application', 'chrome.exe')
        if base and os.path.isfile(chrome):
            subprocess.Popen([chrome, url])
            return
    webbrowser.open(url)


MIDA_MAX_REGISTRE = 2 * 1024 * 1024


def log(text):
    linia = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {text}"
    try:
        print(linia, flush=True)
    except Exception:
        pass
    try:
        # quan el registre passa de 2 MB, el vell es guarda a registre-anterior.txt i se'n comença un de nou
        if os.path.getsize(REGISTRE) > MIDA_MAX_REGISTRE:
            os.replace(REGISTRE, os.path.join(DADES, 'registre-anterior.txt'))
    except OSError:
        pass
    with open(REGISTRE, 'a', encoding='utf-8') as f:
        f.write(linia + '\n')


# --- el NAS (Synology Drive) hi és? ---------------------------------------------------------------
# Si es reanomenen carpetes o arxius de «Mi Musica» mentre el Synology Drive no té connexió amb el NAS, el canvi
# només es fa al PC i, quan torna la connexió, el client es queda amb els dos noms (carpetes repetides i còpies
# «..._CaseConflict.mp3», com el 04/11/2026). Abans de canviar cap nom es comprova que el NAS respon.
SYNO = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'SynologyDrive')
_IP_LOCAL = re.compile(r'\b((?:192\.168|10)\.\d{1,3}\.\d{1,3}(?:\.\d{1,3})?|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}):(\d{2,5})\b')
_ERR_SYNO = re.compile(r'Fail to open channel|error while connecting|I/O error', re.I)
_nas = {'t': 0, 'ok': True, 'avis': False}


def _cua(ruta, n=65536):
    """Les últimes línies d'un arxiu de text (sense llegir-lo sencer)."""
    try:
        with open(ruta, 'rb') as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - n))
            return f.read().decode('utf-8', 'replace').splitlines()
    except OSError:
        return []


def adreca_nas():
    """L'adreça del NAS a la xarxa de casa: «nas_adreca = 192.168.0.27:6690» al config.ini o, si no hi és,
    la que fa servir el Synology Drive (la seva base de dades o el seu registre). None si no se sap."""
    a = str(config().get('nas_adreca', '') or '').strip()
    if a:
        h, _, p = a.partition(':')
        return h, int(p or 6690)
    try:
        import sqlite3, tempfile
        db = os.path.join(SYNO, 'data', 'db', 'sys.sqlite')
        if os.path.exists(db):
            tmp = os.path.join(tempfile.gettempdir(), 'discoteca-syno-sys.sqlite')
            shutil.copyfile(db, tmp)          # una còpia: el Synology Drive té l'original obert
            con = sqlite3.connect(tmp)
            try:
                for ip, port in con.execute('SELECT server_ip, server_port FROM connection_table'):
                    m = _IP_LOCAL.match(f'{ip}:{port}')
                    if m:
                        return m.group(1), int(m.group(2))
            finally:
                con.close()
    except Exception:
        pass
    # el registre de la interfície del Synology Drive porta l'adreça de casa a cada intent de connexió
    for linia in reversed(_cua(os.path.join(SYNO, 'log', 'ui.log'), 1 << 20)):
        m = _IP_LOCAL.search(linia)
        if m:
            return m.group(1), int(m.group(2))
    return None


def nas_connectat(cache=120):
    """True si es poden reanomenar carpetes i arxius del NAS sense perill: el NAS respon a la xarxa de casa i el
    Synology Drive no està donant errors de connexió ara mateix. Si no se sap l'adreça del NAS, True (com abans)."""
    import socket
    if time.time() - _nas['t'] < cache:
        return _nas['ok']
    ok, motiu = True, ''
    a = adreca_nas()
    if a:
        try:
            socket.create_connection(a, timeout=4).close()
        except OSError:
            ok, motiu = False, f'el NAS ({a[0]}) no respon'
    elif not _nas['avis']:
        _nas['avis'] = True
        log('  NAS: no sé l\'adreça del NAS per comprovar si hi és (es pot posar «nas_adreca» al config.ini)')
    ui = os.path.join(SYNO, 'log', 'ui.log')
    try:
        recent = time.time() - os.path.getmtime(ui) < 600
    except OSError:
        recent = False
    if ok and recent and any(_ERR_SYNO.search(l) for l in _cua(ui, 8192)[-15:]):
        ok, motiu = False, 'el Synology Drive té errors de connexió'
    if not ok and _nas['ok']:
        log(f'  NAS: {motiu}; no es canvia cap nom de carpeta ni d\'arxiu fins que torni la connexió')
    _nas.update(t=time.time(), ok=ok)
    return ok


def N(s):
    """Normalitza noms per comparar: sense accents, articles ni signes."""
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'\s*\(\d+\)$', '', s)          # "Tool (2)" de Discogs
    s = re.sub(r',\s*the$', '', s)
    s = re.sub(r'\b(the|a|an)\b', '', s)
    return re.sub(r'[^a-z0-9]', '', s)


NUMS = {'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6', 'seven': '7', 'eight': '8',
        'nine': '9', 'ten': '10', 'eleven': '11', 'twelve': '12', 'thirteen': '13', 'fourteen': '14', 'fifteen': '15',
        'sixteen': '16', 'seventeen': '17', 'eighteen': '18', 'nineteen': '19', 'twenty': '20',
        'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6', 'vii': '7', 'viii': '8', 'ix': '9', 'x': '10'}


# notes d'edició o de format que porten els noms de les carpetes baixades i que no són del títol del disc
SOROLL = r'remaster|reissue|re-issue|deluxe|edition|expanded|anniversary|bonus|explicit|kbps|\b320\b|\b256\b|\b192\b|flac|mp3|web|rip|vinyl|lossless'


def titol_net(t):
    """«Dag With Shawn (2010)» -> («Dag With Shawn», «2010»); «Can I Say (Reissue)» -> («Can I Say», '').
    Treu l'any entre parèntesis o claudàtors del final i les notes d'edició o de format."""
    t, any_ = str(t or '').strip(), ''
    while True:
        m = re.search(r'\s*[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]\s*$', t)
        if m and m.start() > 0:
            any_ = any_ or m.group(1)
            t = t[:m.start()].rstrip(' -–—')
            continue
        m = re.search(r'\s*[\(\[][^\(\)\[\]]*(?:' + SOROLL + r')[^\(\)\[\]]*[\)\]]\s*$', t, re.I)
        if m and m.start() > 0:
            t = t[:m.start()].rstrip(' -–—')
            continue
        return t.strip(), any_


def NT(s):
    """Com N() però «Fifteen» = «15» i «IV» = «4», per comparar títols (sense l'any ni les notes d'edició del final)."""
    s = titol_net(s)[0] or str(s or '')
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = s.replace('&', ' and ')                 # «Hips & Makers» = «Hips And Makers»
    s = re.sub(r'[\(\[][^\)\]]*(remaster|reissue|deluxe|edition|expanded|anniversary|bonus)[^\)\]]*[\)\]]', '', s)
    s = re.sub(r'[\(\[]\s*(19|20)\d{2}\s*[\)\]]\s*$', '', s)       # «Dag With Shawn (2010)»
    s = ' '.join(NUMS.get(w, w) for w in re.findall(r'[a-z0-9]+', s))
    return N(s)


def marca_reanomena(abans, d):
    """L'Ignasi ha canviat a mà el títol o l'artista: la carpeta del NAS i els arxius de dins s'han de dir igual."""
    if abans and d.get('carpeta') and (str(abans.get('titol') or '').strip() != str(d.get('titol') or '').strip()
                                       or str(abans.get('artista') or '') != str(d.get('artista') or '')):
        d['reanomena_nas'] = True
        return True
    return False


def marca_reanomena_artista(discs, id_art):
    """S'ha corregit el nom d'un artista: totes les seves carpetes del NAS es reanomenen. Torna quantes."""
    n = 0
    for d in discs:
        if str(d.get('artista')) == str(id_art) and d.get('carpeta'):
            d['reanomena_nas'] = True
            n += 1
    return n


def aplica_canvis_mobil():
    """Incorpora al catàleg els canvis fets des del mòbil (dades\\mobil\\*.json) i després els esborra."""
    carpeta = os.path.join(DADES, 'mobil')
    if not os.path.isdir(carpeta):
        return 0
    fitxers = sorted(f for f in os.listdir(carpeta) if f.endswith('.json'))
    if not fitxers:
        return 0
    with BLOC:
        discs = llegeix('discs.json', [])
        arts = llegeix('artistes.json', {})
        ig = llegeix('ignorats.json', {'artistes': [], 'discos': []})
        fets = []
        for f in fitxers:
            try:
                with open(os.path.join(carpeta, f), encoding='utf-8') as fh:
                    c = json.load(fh)
            except Exception:
                continue          # encara s'està sincronitzant: ja ho farem la propera vegada
            t = c.get('tipus')
            if t == 'artista':
                if str(c['id']) in arts and arts[str(c['id'])] != c['nom']:
                    marca_reanomena_artista(discs, c['id'])
                arts[c['id']] = c['nom']
            elif t == 'esborra':
                for d in discs:
                    if str(d.get('id')) == str(c['id']) and d.get('carpeta'):
                        L = ig.setdefault('carpetes', [])      # que el NAS no la torni a afegir
                        if d['carpeta'] not in L:
                            L.append(d['carpeta'])
                discs = [d for d in discs if str(d.get('id')) != str(c['id'])]
            elif t == 'ignora':
                L = ig.setdefault(c.get('llista', 'artistes'), [])
                if c.get('clau') and c['clau'] not in L:
                    L.append(c['clau'])
            elif t == 'disc':
                d = next((x for x in discs if str(x.get('id')) == str(c['id'])), None)
                if d is None:
                    d = {'id': c['id']}
                    discs.append(d)
                abans = dict(d)
                for k, v in (c.get('patch') or {}).items():
                    if v is None:
                        d.pop(k, None)
                    else:
                        d[k] = v
                if {'titol', 'artista'} & set(c.get('patch') or {}):
                    marca_reanomena(abans, d)
            fets.append(f)
        if fets:
            desa('artistes.json', arts)
            desa('ignorats.json', ig)
            desa('discs.json', discs)
            for f in fets:
                try:
                    os.remove(os.path.join(carpeta, f))
                except OSError:
                    pass
            log(f'Incorporats {len(fets)} canvis fets des del mòbil')
        return len(fets)


def suports(d):
    return [x for x in re.split(r'[\s,;/+]+', str(d.get('suport') or '').lower()) if x]


def afegeix_suport(d, nou):
    L = suports(d)
    if nou not in L:
        L.append(nou)
        d['suport'] = ', '.join(L)
        return True
    return False
