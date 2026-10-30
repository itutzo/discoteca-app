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


def log(text):
    linia = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}  {text}"
    try:
        print(linia, flush=True)
    except Exception:
        pass
    with open(REGISTRE, 'a', encoding='utf-8') as f:
        f.write(linia + '\n')


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


def NT(s):
    """Com N() però «Fifteen» = «15» i «IV» = «4», per comparar títols."""
    s = unicodedata.normalize('NFD', str(s or '')).encode('ascii', 'ignore').decode().lower()
    s = re.sub(r'[\(\[][^\)\]]*(remaster|deluxe|edition|expanded|anniversary|bonus)[^\)\]]*[\)\]]', '', s)
    s = ' '.join(NUMS.get(w, w) for w in re.findall(r'[a-z0-9]+', s))
    return N(s)


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
                for k, v in (c.get('patch') or {}).items():
                    if v is None:
                        d.pop(k, None)
                    else:
                        d[k] = v
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
