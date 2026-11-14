# -*- coding: utf-8 -*-
"""Funcions comunes de la Discoteca: rutes, lectura i escriptura segura de dades."""
from difflib import SequenceMatcher
import functools, json, os, re, shutil, threading, time, unicodedata, configparser, datetime

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


# Norma de l'Ignasi (14/11/2026): un grup que ja tens es reconeix encara que estigui escrit diferent, i el nom bo és
# el de la portada del disc, que és el que ell ja hi té («Million $ Reload», no «Million Dollar Reload»). Els símbols
# es llegeixen com a paraules, les abreviatures es despleguen, els números en lletres valen com a xifres, i no compten
# «The», la inicial del mig amb punt ni les lletres doblades. Cap altra falta: «Ryan Adams» no és «Bryan Adams».
# És la mateixa regla que la funció claus() de la pàgina (index.html), que fa servir «Per a tu».
_SIMBOL = {'$': ('dollar', 's', ''), '@': ('at', 'a'), '%': ('percent', ''), '#': ('number', ''), '!': ('', 'i'),
           '€': ('euro', 'e'), '£': ('pound', 'l')}
_PARAULA = {'dr': 'doctor', 'st': 'saint', 'mt': 'mount', 'mr': 'mister', 'mrs': 'missus', 'jr': 'junior',
            'sr': 'senior', 'bros': 'brothers', 'vs': 'versus', 'n': 'and', 'y': 'and', 'et': 'and',
            **{w: str(i) for i, w in enumerate('zero one two three four five six seven eight nine ten eleven twelve '
                                               'thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split())},
            'hundred': '100', 'thousand': '1000', 'million': '1000000'}


@functools.lru_cache(maxsize=None)
def claus_nom(nom):
    """Totes les maneres equivalents d'escriure un nom d'artista, per comparar-lo amb els que ja tens: n'hi ha prou que
    en coincideixi una. Inclou sempre N(nom)."""
    s = ''.join(c for c in unicodedata.normalize('NFD', str(nom or '').lower()) if not unicodedata.combining(c))
    s = re.sub(r"[’‘`´]", "'", s)
    s = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', ' ', s)
    s = re.sub(r'\s*[&+]\s*', ' and ', s)
    v = [s]
    for c, op in _SIMBOL.items():
        if c in s:
            v = [x.replace(c, f' {o} ' if o else '') for x in v for o in op]
    K = set()
    for x in v[:8]:
        x = unicodedata.normalize('NFD', x).encode('ascii', 'ignore').decode()
        w = [p for p in re.sub(r'[^a-z0-9]+', ' ', re.sub(r',\s*the\s*$', '', x)).split() if p != 'the']
        K.add(''.join(_PARAULA.get(p, p) for p in w))
        K.add(''.join(w))
        K.add(''.join(re.sub(r'([a-z])\1+', r'\1', _PARAULA.get(p, p)) for p in w))
    m = re.sub(r'(\b[a-z]{2,}\s+)[a-z]\.\s+(?=\S)', r'\1', s)
    if m != s:
        K.add(N(m))
    K.add(N(nom))
    K.discard('')
    return frozenset(K)


def mateix_artista(a, b):
    """Dos noms d'artista són el mateix grup escrit diferent (vegeu claus_nom)."""
    return N(a) == N(b) or bool(claus_nom(a) & claus_nom(b))


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


# ------------------------------------------------------------------ identificació robusta (13/11/2026)
# Norma de l'Ignasi: un disc s'ha de reconèixer pel títol, l'any i els noms dels temes encara que la carpeta o els
# arxius estiguin escrits de qualsevol manera (espais, signes, majúscules, accents, claudàtors, «FLAC», «320»...).
# Aquestes funcions només serveixen per COMPARAR i BUSCAR: no canvien res del que es mostra a la fitxa.
_FORMAT = r'flac|mp3|aac|m4a|ogg|wav|ape|alac|lossless|hi-?res|web(?:-?rip)?|cd-?rip|vinyl-?rip|rip|vbr|cbr|v0|v2|' \
          r'\d{2,4}\s*kbps|kbps|24\s*bits?|16\s*bits?|320|256|224|192|160|128'
_FORMAT_FINAL = re.compile(r'(?:[\s\-–—_.]+|^)(?:' + _FORMAT + r')\s*$', re.I)
_ANY_ENTRE = re.compile(r'\s*[\(\[]\s*((?:19|20)\d{2})\s*[\)\]]\s*')
_GRUP_SOROLL = re.compile(r'\s*[\(\[][^\(\)\[\]]*\b(?:' + _FORMAT + r'|' + SOROLL + r')\b[^\(\)\[\]]*[\)\]]\s*', re.I)


def nom_net(s, artista=False, the_davant=False):
    """Un nom d'artista o de disc tal com ve d'una carpeta, sense el soroll: guions baixos, anys entre claudàtors o
    parèntesis («[1978]», «(2020)»), etiquetes de format o de bitrate al final o entre claudàtors («FLAC», «320»,
    «[MP3 320kbps]», «(Remastered)») i espais repetits. Per a l'artista, també l'any solt al principi o al final
    («Magpie Salute 2018»); amb the_davant (només per buscar), «Magpie Salute, The» passa a «The Magpie Salute».
    Torna (net, any). Si no en queda res, torna el nom original."""
    orig = str(s or '').strip()
    t, any_ = orig.replace('_', ' '), ''
    m = _ANY_ENTRE.search(t)
    while m:
        any_ = any_ or m.group(1)
        t = (t[:m.start()] + ' ' + t[m.end():]).strip()
        m = _ANY_ENTRE.search(t)
    t = _GRUP_SOROLL.sub(' ', t)
    t = re.sub(r'\s+', ' ', t).strip(' -–—.')
    while True:
        m = _FORMAT_FINAL.search(t)
        if not m or m.start() == 0:
            break
        t = t[:m.start()].strip(' -–—.')
    if artista:
        # notes amb comes entre parèntesis («Grease Helmet (FIN,pre-Ajattara,Amorphis) [glam,hard-rock]»), 14/11/2026
        t = re.sub(r'\s+', ' ', re.sub(r'\s*[\(\[][^\(\)\[\]]*,[^\(\)\[\]]*[\)\]]', ' ', t)).strip(' -–—.') or t
        m = re.match(r'^((?:19|20)\d{2})\s+(?=\D)', t) or re.search(r'\s+((?:19|20)\d{2})$', t)
        if m and len(t) - len(m.group(0)) >= 2:
            any_ = any_ or m.group(1)
            t = (t[:m.start()] + t[m.end():]).strip(' -–—.')
        m = re.match(r'^(.+?),\s*the$', t, re.I) if the_davant else None
        if m:
            t = 'The ' + m.group(1).strip()
    t = re.sub(r'\s+', ' ', t).strip(' -–—.')
    return (t or orig), any_


# països o regions que algunes baixades enganxen al final del nom («Feel The Shake usa», «Crate Diggin USA»,
# «... (Japan)»): no formen part del títol. Només per buscar (14/11/2026), mai per canviar el que es mostra.
_PAIS_FINAL = re.compile(r'(?:\s+[-–—]?\s*|\s*[\(\[]\s*)(?:usa|us|uk|eu|euro|europe|jap|japan|jpn|jp|ger|germany|'
                         r'fra|france|ita|italy|spain|esp|can|canada|aus|australia|import|promo)\s*[\)\]]?\s*$', re.I)


def sense_pais(s):
    """«Feel The Shake usa» -> «Feel The Shake»; «Born In The USA» es queda igual si no hi queden almenys 2 paraules."""
    s = str(s or '').strip()
    m = _PAIS_FINAL.search(s)
    if m and m.start() > 0:
        resta = s[:m.start()].strip(' -–—.,')
        if len(re.findall(r'\w+', resta)) >= 2 and not re.search(r'\b(in|the|of)\s*$', resta, re.I):
            return resta
    return s


def sense_parentesi(s):
    """«You, We See You Crawling (Live, 1990)» -> («You, We See You Crawling», «1990»): treu el que va entre
    parèntesis o claudàtors al final (i en torna l'any, si n'hi ha). Només per buscar."""
    s, any_ = str(s or '').strip(), ''
    while True:
        m = re.search(r'\s*[\(\[]([^\(\)\[\]]*)[\)\]]\s*$', s)
        if not m or m.start() == 0:
            return s, any_
        a = re.search(r'\b((?:19|20)\d{2})\b', m.group(1))
        any_ = any_ or (a.group(1) if a else '')
        s = s[:m.start()].strip(' -–—.,')


_NUM_INICI = re.compile(r'^[\(\[]?\d{1,3}(?:[-.]\d{1,3})?[\)\]]?(?:\s*[-–—.]\s*|\s+)(?=\S)')
_PREFIXOS = (('claudators', re.compile(r'^\[([^\]]+)\]\s*(\S.*)$')),
             ('guio', re.compile(r'^(.+?)\s+[-–—]\s+(\S.*)$')),
             ('guio_junt', re.compile(r'^([^-–—]+?)\s*[-–—]\s*(\S.*)$')))


def temes_nets(temes, titol=''):
    """Els títols dels temes trets dels noms dels arxius, nets per buscar-los i comparar-los: sense el número de pista
    que no s'havia pogut separar («(01) ...», «01-01 ...», «1-07 - ...»), sense guions baixos i sense el nom del grup
    o del disc que porten davant tots els arxius («Dozer - Rising», «[California Breed] The Way»,
    «the_magpie_salute-sooner_or_later»). Només es treu el que es repeteix a la majoria de temes (60 %), perquè un
    tema que comença amb un número («99 Problems») o amb un guió es quedi igual.
    Torna (temes, artista): l'artista és el nom repetit davant dels temes, si n'hi ha i no és el títol del disc."""
    ts = [re.sub(r'\s+', ' ', str(t or '').replace('_', ' ')).strip() for t in temes or []]
    ts = [t for t in ts if t]
    n = len(ts)
    if n == 0:
        return [], ''
    minim = max(2, int(0.6 * n + 0.999)) if n > 1 else 2
    if sum(1 for t in ts if _NUM_INICI.match(t)) >= minim:
        ts = [_NUM_INICI.sub('', t, count=1) if _NUM_INICI.match(t) else t for t in ts]
    elif n == 1 and re.match(r'^[\(\[]?\d{1,3}(?:[-.]\d{1,3})?[\)\]]?\s+[-–—]\s+\S', ts[0]):
        ts = [_NUM_INICI.sub('', ts[0], count=1)]       # un sol arxiu: «07 - Night Of The Thumpasorus Peoples»
    artista = ''
    for _ in range(2):          # «[Grup] Disc - Tema»: pot haver-hi dos prefixos seguits
        millor = None
        for tipus, rx in _PREFIXOS:
            comptes = {}
            for t in ts:
                m = rx.match(t)
                if m and N(m.group(1)):
                    comptes.setdefault(N(m.group(1)), [m.group(1).strip(), 0])[1] += 1
            for k, (nom, c) in comptes.items():
                if c >= minim and (millor is None or c > millor[2]):
                    millor = (rx, k, c, nom)
        if not millor:
            break
        rx, k, _, nom = millor
        ts = [rx.match(t).group(2).strip() if rx.match(t) and N(rx.match(t).group(1)) == k else t for t in ts]
        if not artista and k != N(titol) and not re.match(r'^\d+$', k):
            artista = nom
    return ts, artista


_HASH_FINAL = re.compile(r'[\s\-_]+[\(\[]?(?=[0-9a-f]*\d)[0-9a-f]{8}[\)\]]?$', re.I)


def art_carpeta(nom):
    """Norma de l'Ignasi (14/11/2026): a la CARPETA, els grups que comencen amb «The» van amb «, The» al final
    («The Fumes» -> «Fumes, The - 2006 - Guns Of Gold»)."""
    nom = str(nom or '').strip()
    m = re.match(r'^the\s+(.+)$', nom, re.I)
    if m and N(m.group(1)) and not re.search(r',\s*the$', nom, re.I):
        return f'{m.group(1).strip()}, The'
    return nom


def art_arxius(nom):
    """... i als ARXIUS de dins, amb «The» davant («Fumes, The» -> «The Fumes - Guns Of Gold - 01 - ...»)."""
    nom = str(nom or '').strip()
    m = re.match(r'^(.+?),\s*the$', nom, re.I)
    return f'The {m.group(1).strip()}' if m else nom


def neteja_titols_temes(temes, artista='', titol='', numeros=True):
    """Els títols dels temes tal com s'han de veure a la fitxa i als noms dels arxius, sense el soroll que porten els
    arxius baixats (norma del 13/11/2026, disc de Dozer): el nom del grup o del disc davant de cada tema («Dozer -
    Rising», «[California Breed] The Way», «the_magpie_salute-sooner_or_later»), el número de pista sense separar
    («(01) …», «01 …»), guions baixos i un codi de descàrrega al final («…-490a0c8c»). Cada neteja només es fa si es
    repeteix a la majoria de temes (60 %, i com a mínim 2), i el prefix només es treu si és l'artista o el títol del
    disc: un recopilatori amb un artista diferent a cada tema («Brad Vs. Satchel») i el tema que es diu com el grup
    («Bad Company» de Bad Company) es queden igual. Torna la llista amb el mateix ordre i llargada."""
    ts = [str(t or '') for t in temes or []]
    plens = [i for i, t in enumerate(ts) if t.strip()]
    n = len(plens)
    if n < 2:
        return ts
    minim = max(2, int(0.6 * n + 0.999))
    out = list(ts)
    baixos = sum(1 for i in plens if '_' in ts[i] and ' ' not in ts[i].strip()) >= minim
    if baixos:
        out = [re.sub(r'\s+', ' ', t.replace('_', ' ')).strip() if t.strip() else t for t in out]
    # (als noms dels arxius no: si després del número de pista en queda un altre, és del títol, «1 Ghosts I» de NIN)
    if numeros and sum(1 for i in plens if _NUM_INICI.match(out[i].strip())) >= minim:
        out = [_NUM_INICI.sub('', t.strip(), count=1) if t.strip() and _NUM_INICI.match(t.strip()) else t for t in out]
    valids = {N(artista), N(nom_net(artista, artista=True, the_davant=True)[0]), N(titol), N(nom_net(titol)[0])} - {''}
    for _ in range(2):          # «[Grup] Disc - Tema»: pot haver-hi dos prefixos seguits
        fet = False
        for _tipus, rx in _PREFIXOS:
            casa = [i for i in plens if (lambda m: m and N(m.group(1)) in valids)(rx.match(out[i].strip()))]
            if len(casa) >= minim:
                for i in casa:
                    out[i] = rx.match(out[i].strip()).group(2).strip()
                fet = True
                break
        if not fet:
            break
    if sum(1 for i in plens if _HASH_FINAL.search(out[i])) >= minim:
        out = [_HASH_FINAL.sub('', t) if t.strip() else t for t in out]
    if baixos:
        out = [' '.join(w[:1].upper() + w[1:] for w in t.split(' ')) if t.strip() else t for t in out]
    out = [o if o.strip() else t for o, t in zip(out, ts)]       # mai deixar un tema sense nom
    return out


def TT(s):
    """Clau d'un tema per comparar: com NT() però sense res del que va entre parèntesis o claudàtors
    («Killing Time (Original Demo Version)» = «Killing Time», «Last Bandit (Live Electric)» = «Last Bandit»)."""
    sense = re.sub(r'[\(\[][^\(\)\[\]]*[\)\]]', ' ', str(s or ''))
    # la data o la durada que algunes edicions posen al costat del tema («Music Critics - 1/24/81», «Dead Solger 11/15/82»,
    # «Gone 4:31»): no és del títol (14/11/2026, The Fartz)
    sense = re.sub(r'(?:\s*[-–—]?\s*(?:\d{1,2}[/.]\d{1,2}[/.]\d{2,4}|\d{1,2}:\d{2}))+\s*$', '', sense)
    return NT(sense) or NT(s)


def tema_igual(a, b):
    """Dos títols de tema són el mateix tema: iguals o molt semblants (85 %), també sense el que va entre parèntesis."""
    na, nb = NT(a), NT(b)
    if not na or not nb:
        return False
    if na == nb or SequenceMatcher(None, na, nb).ratio() >= 0.85:
        return True
    ta, tb = TT(a), TT(b)
    return len(ta) >= 3 and len(tb) >= 3 and (ta == tb or SequenceMatcher(None, ta, tb).ratio() >= 0.9)


def temes_coincidents(meus, seus):
    """Quants temes de `meus` són a `seus` (títols tal com vénen, sense normalitzar)."""
    seus = [u for u in seus or [] if NT(u)]
    return sum(1 for t in meus or [] if NT(t) and any(tema_igual(t, u) for u in seus))


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


# ---------------------------------------------------------------------------------------------------------------------
# Norma de l'Ignasi (14/11/2026): cada estil (i cada gènere) surt un sol cop, encara que s'hagi escrit de maneres
# diferents. Regla general, sense llistes per estil:
#  - no compten majúscules, accents, espais, guions, barres ni «&»/«and»/«n'» («Pop Rock» = «Pop-Rock» = «Pop/Rock»
#    = «PopRock»; «Rock & Roll» = «Rock n' Roll»); un «7» entre lletres és la barra mal picada («Pop7Rock»);
#  - les faltes es corregeixen paraula per paraula contra el vocabulari de les etiquetes de Last.fm desades a
#    lastfm.json (milers d'artistes): una paraula que no hi surt passa a la paraula que hi surt i que només té una
#    lletra de diferència (dues, si és llarga), si és clarament la més usada («Rcok», «Southen», «Alternarive»,
#    «Experiemntal», «Contemporany»); i un estil sencer que no surt a les fonts s'ajunta amb un de la discoteca que hi
#    sigui a una lletra («Blue Rock» → «Blues Rock»), però mai dos estils que existeixen tots dos («Punk Rock» /
#    «Funk Rock»);
#  - unes poques paraules en castellà o català passen a l'anglès de les fonts (ESTIL_TRAD);
#  - el nom que es queda és el més usat a les fonts (Last.fm: «Blues Rock» i no «Blues-Rock») i, si les fonts no en
#    diuen res, el més usat a la discoteca (que ve d'AllMusic, Discogs o MusicBrainz).
ESTIL_TRAD = {'alternativa': 'alternative', 'gotico': 'gothic', 'goticos': 'gothic', 'sureno': 'southern',
              'directo': 'live', 'psicodelia': 'psychedelia', 'psicodelico': 'psychedelic', 'psicodelica': 'psychedelic',
              'electronico': 'electronic', 'electronica': 'electronica', 'experimentale': 'experimental'}
# un estil sencer que és el mateix que un altre amb una altra paraula
# (els cinc darrers, aprovats per l'Ignasi el 14/11/2026, amb el nom que fan servir les fonts)
ESTIL_SIN = {'psychedelia': 'psychedelic', 'trash': 'thrash', 'southern': 'southern rock',
             'songsinger': 'singer-songwriter', 'songwriter': 'singer-songwriter', 'classicalrock': 'classic rock',
             'stoner': 'stoner rock'}
_PSICO = re.compile(r'^ps[iy]ch?[oe]deli(c|ch|co|ca)$')        # Psicodelic, Psicodelich, Psycodelich…
_PSICO_A = re.compile(r'^ps[iy]ch?[oe]delia$')                 # Psychodelia, Psycodelia


def _sense_accents(s):
    return unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode()


def _dist(a, b, maxim=2):
    """Distància d'edició amb transposicions (Damerau). Para quan passa del màxim."""
    if abs(len(a) - len(b)) > maxim:
        return maxim + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            c = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + c)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > maxim:
            return maxim + 1
        prev2, prev = prev, cur
    return prev[-1]


def _peces_estil(s):
    """Divideix un estil en paraules i separadors, mantenint com estava escrit."""
    s = str(s or '').strip()
    linies = [x.strip() for x in s.splitlines() if x.strip()]
    s = linies[0] if linies and all(N(x) == N(linies[0]) for x in linies) else ' '.join(linies)  # «X\nX» → «X»
    s = re.sub(r'(?<=[A-Za-z])7(?=[A-Za-z])', '/', s)                                            # «Pop7Rock»
    s = re.sub(r'(?<=[a-z])(?=[A-Z][a-z])', ' ', s)                                              # «PopRock»
    return [p for p in re.split(r"([A-Za-z0-9À-ÿ']+)", s) if p != '']


class Estils:
    """Vocabulari de les fonts (etiquetes de Last.fm desades) per corregir i triar el nom dels estils."""

    def __init__(self, lastfm=None, meus=None):
        # meus: {paraula: nombre de discos de la discoteca que la fan servir}. Una paraula que l'Ignasi fa servir en
        # molts discos («Trad», d'«American Trad Rock», d'AllMusic) no és cap falta encara que Last.fm no la tingui.
        self.meus = meus or {}
        self.tag = {}       # etiqueta exacta (minúscules) → nombre d'artistes
        self.par = {}       # paraula → nombre d'artistes
        for v in (lastfm or {}).values():
            if not isinstance(v, dict):
                continue
            for t in v.get('t') or []:
                if not t or not isinstance(t[0], str):
                    continue
                e = _sense_accents(t[0]).lower().strip()
                self.tag[e] = self.tag.get(e, 0) + 1
                for w in re.findall(r"[a-z0-9]+", e):
                    self.par[w] = self.par.get(w, 0) + 1
        self.claus_tag = {}
        for e, n in self.tag.items():
            k = self.clau_simple(e)
            if n > self.claus_tag.get(k, 0):
                self.claus_tag[k] = n
        self._cache = {}

    @staticmethod
    def clau_simple(s):
        s = _sense_accents(s).lower().replace('&', ' and ').replace('+', ' and ')
        s = re.sub(r"\bn'|'n'|\bn\b", ' and ', s)
        return re.sub(r'[^a-z0-9]', '', s)

    def paraula(self, w):
        """Corregeix una paraula (minúscules, sense accents)."""
        if w in self._cache:
            return self._cache[w]
        r = w
        if w.isdigit() or w in ('n', 'and'):
            pass
        elif _PSICO.match(w) and w != 'psychedelic':
            r = 'psychedelic'
        elif _PSICO_A.match(w) and w != 'psychedelia':
            r = 'psychedelia'
        elif w in ESTIL_TRAD:
            r = ESTIL_TRAD[w]
        elif self.par.get(w, 0) < 3 and len(w) >= 3 and self.par:
            maxim = 2 if len(w) >= 9 else 1
            cands = sorted(((n, x) for x, n in self.par.items() if n >= 20 and abs(len(x) - len(w)) <= maxim
                            and len(x) >= 3 and _dist(w, x, maxim) <= maxim), reverse=True)
            for t in ESTIL_TRAD:                       # «Aternativa» → «alternativa» → «alternative»
                if _dist(w, t, 1) <= 1 and len(w) >= 6:
                    cands.insert(0, (10 ** 9, ESTIL_TRAD[t]))
            if cands and (len(cands) == 1 or cands[0][0] >= 3 * cands[1][0]):
                n_meu = self.meus.get(w, 0)
                if n_meu < 5 or self.meus.get(cands[0][1], 0) >= 20 * n_meu:
                    r = cands[0][1]
        self._cache[w] = r
        return r

    def corregeix(self, s):
        """Torna l'estil amb les paraules corregides, mantenint els separadors i les majúscules d'origen."""
        out = []
        for p in _peces_estil(s):
            if re.fullmatch(r"[A-Za-z0-9À-ÿ']+", p) and not p.startswith("'") and p.lower() not in ("n'",):
                w = _sense_accents(p).lower().strip("'")
                c = self.paraula(w)
                if c == w and _sense_accents(p) != p:
                    out.append(_sense_accents(p))
                elif c == w:
                    out.append(p)
                else:
                    out.append(c.upper() if p.isupper() and len(p) > 1 else c.capitalize() if p[:1].isupper() else c)
            else:
                out.append(p)
        r = re.sub(r'\s+', ' ', ''.join(out)).strip()
        r = re.sub(r'\s*/\s*', '/', r)
        r = re.sub(r'\s*-\s*', '-', r)
        k = self.clau_simple(r)
        if k in ESTIL_SIN:
            r = ESTIL_SIN[k].title()
        return r

    def fonts(self, s):
        """Quantes vegades surt aquest estil, escrit exactament així, a les fonts."""
        return self.tag.get(_sense_accents(s).lower().strip(), 0)


def _titol_estil(s):
    """Majúscula a cada paraula; les sigles («EBM», «R&B») i «n'» es queden com són."""
    def f(m):
        w = m.group(0)
        if w.isupper() and len(w) <= 4 or w.lower() in ("n'", 'n', 'and') and m.start() > 0:
            return w if w.isupper() else w.lower()
        return w[:1].upper() + w[1:].lower() if not (len(w) > 1 and w[1:].isupper() and w[:1].isupper()) else w
    return re.sub(r"[A-Za-z0-9À-ÿ']+", f, s)


def unifica_estils_llista(valors, lastfm=None, comptats=None):
    """Rep tots els estils (o gèneres) de la discoteca i torna {valor original: nom bo}.
    `comptats`: {valor: nombre de discos}. Els grups i el nom bo es decideixen amb la regla de dalt."""
    comptats = comptats or {v: 1 for v in valors}
    if isinstance(lastfm, Estils):
        E = lastfm
    else:
        meus = {}
        for v, n in comptats.items():
            for w in set(re.findall(r'[a-z0-9]+', _sense_accents(v).lower())):
                meus[w] = meus.get(w, 0) + n
        E = Estils(lastfm, meus)
    corr = {v: E.corregeix(v) for v in comptats}
    grups = {}
    for v, c in corr.items():
        grups.setdefault(E.clau_simple(c), []).append(v)
    # un estil sencer que no surt a les fonts s'ajunta amb un altre de la discoteca a una lletra que sí que hi surt,
    # o que és molt més usat («Blue Rock» → «Blues Rock», «op/Rock» → «Pop/Rock»)
    pes = {k: sum(comptats[v] for v in vs) for k, vs in grups.items()}
    for k in sorted(grups, key=lambda k: pes[k]):
        if k not in grups or E.claus_tag.get(k, 0) >= 3 or len(k) < 6:
            continue
        maxim = 1
        cands = [(E.claus_tag.get(k2, 0), pes[k2], k2) for k2 in grups if k2 != k and _dist(k, k2, maxim) <= maxim
                 and (E.claus_tag.get(k2, 0) >= 3 or pes[k2] >= 5 * pes[k])]
        cands.sort(reverse=True)
        if cands and (len(cands) == 1 or cands[0][:2] != cands[1][:2]):
            k2 = cands[0][2]
            grups[k2] += grups.pop(k)
            pes[k2] += pes.pop(k)
    res = {}
    for k, vs in grups.items():
        formes = {}
        for v in vs:
            formes[corr[v]] = formes.get(corr[v], 0) + comptats[v]
        # forma: la que més surt a les fonts; si no, la de més discos (sense comptar majúscules)
        per_min = {}
        for f, n in formes.items():
            per_min.setdefault(f.lower(), []).append((n, f))
        millor = max(per_min, key=lambda m: (E.fonts(m), sum(n for n, _ in per_min[m]), m))
        bo = _titol_estil(max(per_min[millor])[1])
        for v in vs:
            res[v] = bo
    return res


def clau_estil(s, E=None):
    """Clau per comparar estils escrits diferent (sense vocabulari, només forma i paraules en castellà)."""
    E = E or _ESTILS_BUIT
    return E.clau_simple(E.corregeix(s))


_ESTILS_BUIT = Estils({})
