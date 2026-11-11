# -*- coding: utf-8 -*-
"""Completador de la Discoteca. Funciona sol, sense Claude.

  python completar.py --mode nit         NAS + Discogs + una tanda de discos (el que fa la tasca nocturna)
  python completar.py --mode pendents    només els discos marcats com a pendents
  python completar.py --mode tot         pendents i després la resta de la col·lecció (una tanda)
  python completar.py --mode disc --id X un disc concret
  python completar.py --mode discogs     sincronitza CD i vinils amb la teva col·lecció de Discogs
  python completar.py --mode nas         busca discos nous a la carpeta de música
  python completar.py --mode so          escolta una tanda de discos (mostres d'Apple Music) per als similars

Regles: només omple camps buits, mai no toca la classificació personal ni les notes,
i marca tot el que afegeix com a «automàtic» perquè ho puguis revisar.
"""
import argparse, datetime, json, os, re, shutil, sys, time
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comu
from comu import N, NT, log, llegeix, desa, suports, afegeix_suport
import fonts

CFG = comu.config()
DG = fonts.Discogs(CFG.get('discogs_token', '').strip())
LFM = CFG.get('lastfm_key', '').strip()
AVUI = datetime.date.today().isoformat()

GEN = {'poprock': 'Rock', 'rock': 'Rock', 'electronic': 'Electronica', 'blues': 'Blues', 'jazz': 'Jazz',
       'folk': 'Folk', 'country': 'Country', 'folkworldcountry': 'Folk', 'rb': 'R&B', 'rap': 'Rap', 'hiphop': 'Rap'}
NO_MUSICA = re.compile(r'(art direction|design|photo|engineer|assistant|master|mixing|mixed|model|illustration|liner notes|'
                       r'executive|primary artist|^composer$|written|lyrics|booking|legal|management|a&r|artwork|layout|'
                       r'cover|lacquer|copyright|recorded|coordinator|technician|tour|graphic|art$|^music by)', re.I)


def estat(text):
    desa('estat.json', {'text': text, 'quan': datetime.datetime.now().isoformat(timespec='seconds')})


_RES = object()


class Desador:
    """Guarda els discos completats de mica en mica (no a cada disc: discs.json és gran i Dropbox el torna a pujar
    sencer cada vegada). Només s'hi escriuen els camps que ha tocat el completador, i sobre la versió més nova de
    l'arxiu: si mentrestant has editat un camp o has esborrat el disc des de la pàgina o el mòbil, es respecta."""
    CADA_DISCOS, CADA_SEGONS = 15, 120

    def __init__(self):
        self.cua, self.ultim = [], time.time()

    def afegeix(self, abans, d):
        camps = {k for k in set(abans) | set(d) if abans.get(k, _RES) != d.get(k, _RES)}
        if camps:
            self.cua.append((str(d.get('id')), abans, d, camps))
        if len(self.cua) >= self.CADA_DISCOS or time.time() - self.ultim > self.CADA_SEGONS:
            self.desa()

    def desa(self):
        self.ultim = time.time()
        if not self.cua:
            return
        with comu.BLOC:
            try:
                comu.aplica_canvis_mobil()      # primer, el que hagis canviat des del mòbil
            except Exception as e:
                log(f'Error incorporant canvis del mòbil: {e!r}')
            discs = llegeix('discs.json', [])
            per_id = {str(x.get('id')): x for x in discs}
            for id_, abans, d, camps in self.cua:
                ara = per_id.get(id_)
                if ara is None:
                    continue                    # l'has esborrat mentre es completava
                for k in camps:
                    if ara.get(k, _RES) != abans.get(k, _RES):
                        continue                # l'has canviat tu mentrestant: mana el teu
                    if k in d:
                        ara[k] = d[k]
                    else:
                        ara.pop(k, None)
            desa('discs.json', discs)
        self.cua = []


def id_artista(nom, artistes):
    for k, v in artistes.items():
        if N(v) == N(nom):
            return k
    t = int(time.time() * 1000)
    while 'a' + str(t) in artistes:      # dos artistes nous en el mateix mil·lisegon
        t += 1
    k = 'a' + str(t)
    artistes[k] = nom
    desa('artistes.json', artistes)
    return k


def sim(a, b):
    return SequenceMatcher(None, N(a), N(b)).ratio()


# ------------------------------------------------------------------ títols mal escrits
CARPETA = re.compile(r'^(.+?)\s*[-–—]\s*(\d{4})\s*[-–—]\s*(.+)$')


def nom_carpeta(t):
    """Treu els caràcters que Windows no admet als noms de carpeta."""
    t = re.sub(r'\s*[:/\\|]\s*', ' - ', str(t))
    t = re.sub(r'[<>"?*]', '', t)
    return re.sub(r'\s+', ' ', t).strip().rstrip('. ')


def corregeix_titol(d, nou, nom_art):
    """El títol era mal escrit (els temes i un títol molt semblant coincideixen amb Discogs): es corregeix
    a la fitxa i a la carpeta del NAS. El títol antic es guarda a «titol_abans» i a dades/titols_corregits.txt."""
    vell = d.get('titol', '')
    if not nou or N(nou) == N(vell):
        return
    nou = majuscules(nou)
    d.setdefault('titol_abans', vell)
    d['titol'] = nou
    log(f'  Títol mal escrit: «{nom_art} - {vell}» ara és «{nou}»')
    reanomena_carpeta(d, vell)
    try:
        with open(os.path.join(comu.DADES, 'titols_corregits.txt'), 'a', encoding='utf-8') as f:
            f.write(f"{AVUI}\t{nom_art}\t{vell}\t{nou}\t{d.get('carpeta', '')}\n")
    except OSError:
        pass


def majuscules(t):
    """Cada paraula comença amb majúscula, com els noms de les carpetes i dels arxius («Live At The BBC»)."""
    return ' '.join(w[:1].upper() + w[1:] for w in str(t).split(' '))


def reanomena_carpeta(d, titol_vell=None, artistes=None):
    """«Artista - Any - Títol mal escrit» -> «Artista - Any - Títol Bo», i a dins els arxius
    «Artista - Títol mal escrit - 03 - Cançó.mp3» -> «Artista - Títol Bo - 03 - Cançó.mp3».
    Només si la carpeta té aquest format i el seu títol és el que estava mal escrit, o bé si l'Ignasi ha canviat
    a mà el títol o l'artista («reanomena_nas»): llavors també canvia el nom de l'artista de la carpeta i dels
    arxius. Si Windows no deixa (un arxiu obert, el NAS no hi és), es torna a provar la nit següent."""
    c = d.get('carpeta')
    arrel = CFG.get('carpeta_musica', r'C:\SynologyMusic\Mi Musica')
    m = CARPETA.match(c or '')
    if not m or not os.path.isdir(os.path.join(arrel, c)):
        for k in ('carpeta_nova', 'arxius_pendents', 'reanomena_nas'):
            d.pop(k, None)
        return
    if not comu.nas_connectat():
        # sense connexió amb el NAS no es canvia cap nom (el Synology Drive els doblaria): s'hi torna a provar després
        if not d.get('reanomena_nas'):
            d['carpeta_nova'] = d.get('carpeta_nova') or True
        return
    a_ma = d.get('reanomena_nas')
    art_vell = art_nou = m.group(1).strip()
    if a_ma:
        # el títol vell és el que porta ara la carpeta (o el que portava, si ja es va reanomenar)
        vell = a_ma if isinstance(a_ma, str) else m.group(3)
        d['reanomena_nas'] = vell
        nom_art = nom_carpeta((artistes or {}).get(str(d.get('artista')), ''))
        if nom_art and N(nom_art) != N(art_vell):
            art_nou = nom_art       # l'artista ha canviat («Greg Howe» -> «Howe II»)
    else:
        vell = titol_vell or d.get('titol_abans') or ''
    nou_t = majuscules(nom_carpeta(d['titol']))
    nou = f'{art_nou} - {m.group(2)} - {nou_t}'
    if nou != c:
        if not a_ma and N(m.group(3)) != N(vell):
            d.pop('carpeta_nova', None)
            return          # el nom de la carpeta no és el mal escrit: no es toca
        # Windows no distingeix majúscules: «Hips and Makers» -> «Hips And Makers» és la mateixa carpeta
        if nou.lower() != c.lower() and os.path.exists(os.path.join(arrel, nou)):
            log(f'  NAS: no reanomeno «{c}»: ja hi ha una carpeta «{nou}»')
            for k in ('carpeta_nova', 'reanomena_nas'):
                d.pop(k, None)
            return
        try:
            os.rename(os.path.join(arrel, c), os.path.join(arrel, nou))
        except OSError as e:
            d['carpeta_nova'] = nou
            log(f'  NAS: ara no puc reanomenar «{c}» ({e}); s\'hi tornarà a provar')
            return
        d['carpeta'] = nou
        log(f'  NAS: carpeta «{c}» reanomenada a «{nou}»')
    d.pop('carpeta_nova', None)
    if reanomena_arxius(os.path.join(arrel, nou), vell, nou_t, art_vell, art_nou):
        d['arxius_pendents'] = True
    else:
        d.pop('arxius_pendents', None)
        d.pop('reanomena_nas', None)


def reanomena_arxius(ruta, vell, nou_t, art_vell=None, art_nou=None):
    """Canvia la part del títol del disc als noms dels arxius («Artista - Títol - 03 - Cançó.mp3») i, si l'artista
    ha canviat, també la de l'artista. No obre ni descarrega res: només canvia el nom.
    Torna quants no s'han pogut canviar."""
    if not N(vell):
        return 0
    canviats, errors = 0, 0
    for root, _, files in os.walk(ruta):
        for f in files:
            base, ext = os.path.splitext(f)
            m = re.match(r'^(.+?)\s*[-–—]\s*(.+?)\s*[-–—]\s*(\d{1,3}\s*[-–—]\s*.+)$', base)
            if not m or N(m.group(2)) != N(vell) or ext.lower() not in EXT:
                continue
            art = m.group(1).strip()
            if art_nou and art_vell and N(art) == N(art_vell):
                art = art_nou
            nou = f'{art} - {nou_t} - {m.group(3).strip()}{ext}'
            if nou == f or (nou.lower() != f.lower() and os.path.exists(os.path.join(root, nou))):
                continue
            try:
                os.rename(os.path.join(root, f), os.path.join(root, nou))
                canviats += 1
            except OSError as e:
                errors += 1
                log(f'  NAS: ara no puc reanomenar «{f}» ({e}); s\'hi tornarà a provar')
    if canviats:
        log(f'  NAS: {canviats} arxius reanomenats a «{os.path.basename(ruta)}»')
    return errors


def reanomena_pendents():
    """Carpetes i arxius que no es van poder reanomenar (un arxiu obert, el NAS no hi era), i els discos als quals
    l'Ignasi ha canviat a mà el títol o l'artista: un altre intent."""
    with comu.BLOC:
        discs = llegeix('discs.json', [])
        artistes = llegeix('artistes.json', {})
        pend = [d for d in discs if d.get('carpeta_nova') or d.get('arxius_pendents') or d.get('reanomena_nas')]
        for d in pend:
            reanomena_carpeta(d, artistes=artistes)
        if pend:
            desa('discs.json', discs)


# format dels arxius: «Artista - Títol del disc - 03 - Cançó.mp3», cada paraula amb majúscula, i als discos dobles
# «Artista - Títol del disc - Disc 2 - 03 - Cançó.mp3»
FORMAT = re.compile(r'^(.+?)\s+[-–—]\s+(.+)\s+[-–—]\s+(\d{1,3})\s+[-–—]\s+(\S.*)$')
FORMAT_CD = re.compile(r'^(.+?)\s+[-–—]\s+(.+)\s+[-–—]\s+(?:CD|Disc|Disco|Disk)\s*(\d{1,2})\s+[-–—]\s+(\d{1,3})\s+[-–—]\s+(\S.*)$', re.I)
MARCA_CD = re.compile(r'(?:^|(?<=[\s\-_(\[]))(?:CD|Disc|Disco|Disk)\s*(\d{1,2})\b\s*[)\]]?\s*[-–—.]?\s*', re.I)


def nom_arxiu(art, tit, base, cd_carpeta=None, discs=None):
    """El nom que ha de dur un arxiu («01 Evangeline» -> «Die Spitz - The Revenge Of Evangeline - 01 - Evangeline»;
    en un disc doble, «CD2 - 03 Cançó» o «2-03 Cançó» -> «Artista - Títol - Disc 2 - 03 - Cançó»).
    cd_carpeta és el número de CD si l'arxiu és dins d'una subcarpeta «CD2» o «Disc 2», i discs {títol: CD} el que
    diu la fitxa (de Discogs o MusicBrainz) quan els arxius no ho diuen.
    Torna ((cd, número), nom), o None si no se n'entén el número de pista (llavors no es toca)."""
    cd = cd_carpeta
    m = FORMAT_CD.match(base)
    m1 = FORMAT.match(base)
    if m and N(m.group(1)) == N(art) and N(m.group(2)) == N(tit):
        cd, num, can = int(m.group(3)), m.group(4), m.group(5)
    elif m1 and N(m1.group(1)) == N(art) and N(m1.group(2)) == N(tit):
        num, can = m1.group(3), m1.group(4)
    else:
        mc = MARCA_CD.search(base)
        m2 = re.match(r'^(\d)\s*[-.]\s*(\d{2})\s*(?!\d)[-–—.]?\s*(\S.*)$', base)       # «2-03 Cançó»
        if mc:
            cd = int(mc.group(1))
            esq, dre = base[:mc.start()].rstrip('([ -–—'), base[mc.end():].strip(' -–—.()[]')
            base = f'{esq} - {dre}' if esq else dre
            num, can = num_titol(base)
        elif m2:
            cd, num, can = int(m2.group(1)), m2.group(2), m2.group(3)
        else:
            num, can = num_titol(base)
        if not num or re.match(r'^\d{1,3}\s', can):
            return None     # no és clar quin és el número de pista
    can = majuscules(re.sub(r'\s+', ' ', can).strip(' -–—'))
    if not can:
        return None
    if not cd and discs:
        cd = discs.get(N(can))
    if cd:
        return (cd, int(num)), f'{art} - {tit} - Disc {cd} - {int(num):02d} - {can}'
    return (0, int(num)), f'{art} - {tit} - {int(num):02d} - {can}'


def formata_arxius(d, arrel):
    """Posa el format «Artista - Títol - 01 - Cançó» (o «Artista - Títol - Disc 2 - 01 - Cançó» als discos dobles)
    als arxius de la carpeta del disc. L'artista i el títol són els de la carpeta. No obre ni descarrega res:
    només canvia el nom. Torna quants n'ha canviat."""
    c = d.get('carpeta')
    m = CARPETA.match(c or '')
    ruta = os.path.join(arrel, c or '')
    if not m or not os.path.isdir(ruta):
        return 0
    art, tit = m.group(1).strip(), m.group(3).strip()
    discs = {N(t[1]): int(t[3][2:]) for t in d.get('temes') or []
             if len(t) > 3 and re.match(r'^CD\d+$', str(t[3])) and N(t[1])}
    canviats = errors = 0
    for root, _, files in os.walk(ruta):
        sub = os.path.relpath(root, ruta)
        mc = re.search(r'(?:CD|Disc|Disco|Disk)\s*(\d{1,2})\b', sub, re.I) if sub != '.' else None
        musica = [f for f in files if os.path.splitext(f)[1].lower() in EXT]
        nous = {f: nom_arxiu(art, tit, os.path.splitext(f)[0], int(mc.group(1)) if mc else None, discs) for f in musica}
        # el mateix tema en dos formats («01 - Try.flac» i «01 - Try.mp3», Thelonious Monster) no és cap conflicte
        claus = [(x[0], os.path.splitext(f)[1].lower()) for f, x in nous.items() if x]
        # dos arxius del mateix format amb el mateix CD i número (no se sap de quin CD és cadascun): no es toca res
        if len(claus) != len(set(claus)):
            continue
        for f, x in nous.items():
            if not x:
                continue
            nou = x[1] + os.path.splitext(f)[1]
            if nou == f or (nou.lower() != f.lower() and os.path.exists(os.path.join(root, nou))):
                continue
            try:
                os.rename(os.path.join(root, f), os.path.join(root, nou))
                canviats += 1
            except OSError as e:
                errors += 1
                log(f'  NAS: ara no puc reanomenar «{f}» ({e}); s\'hi tornarà a provar')
    if canviats:
        log(f'  NAS: {canviats} arxius de «{c}» amb el format «Artista - Disc - 01 - Cançó»')
    return -1 if errors else canviats


SENSE_ANY = re.compile(r'^(.+?)\s+[-–—]\s+(.+)$')


def neteja_titol_nou(d):
    """Disc nou encara sense fonts amb el títol tal com venia a la carpeta («Dag With Shawn (2010)», «Can I Say
    (Reissue)»): el títol queda net, l'any va a la fitxa i es torna a buscar. Només si el títol el va posar el
    programa (no l'Ignasi). Torna True si l'ha canviat."""
    if d.get('fonts') or 'titol' not in (d.get('auto') or []):
        return False
    net, any_ = comu.titol_net(d.get('titol'))
    if not net or net == d.get('titol'):
        return False
    log(f"  Títol de la carpeta netejat: «{d.get('titol')}» ara és «{net}»" + (f' ({any_})' if any_ else ''))
    d['titol'] = net
    if any_ and not d.get('any'):
        d['any'] = any_
        d['auto'] = sorted(set(d.get('auto', [])) | {'any'})
    for k in ('no_trobat', 'proc'):
        d.pop(k, None)
    d['reintenta'] = True
    return True


def posa_any_carpeta(d, arrel):
    """Un disc nou copiat tal com venia («'77 - High Decibels», sense l'any): quan la fitxa ja té l'any, la carpeta
    passa a «Artista - Any - Títol» («'77 - 2011 - High Decibels»). L'artista i el títol són els de la carpeta.
    Torna True si l'ha reanomenada."""
    c = d.get('carpeta') or ''
    any_ = str(d.get('any') or '').strip()
    m = SENSE_ANY.match(c)
    if CARPETA.match(c) or not m or not re.match(r'^\d{4}$', any_) or re.match(r'^\d{4}$', m.group(1).strip()):
        return False
    # «Dag With Shawn (2010)» -> «Dag With Shawn» si l'any és el del disc; «MCMLXXXV (1985)» (Rufio, 2003) es queda
    net, any_p = comu.titol_net(m.group(2))
    tit = net if net and (not any_p or any_p == any_) else m.group(2)
    art, tit = nom_carpeta(m.group(1)), majuscules(nom_carpeta(tit))
    nou = f'{art} - {any_} - {tit}'
    if not art or not tit or not os.path.isdir(os.path.join(arrel, c)):
        return False
    if nou.lower() != c.lower() and os.path.exists(os.path.join(arrel, nou)):
        log(f'  NAS: no reanomeno «{c}»: ja hi ha una carpeta «{nou}»')
        return False
    try:
        os.rename(os.path.join(arrel, c), os.path.join(arrel, nou))
    except OSError as e:
        log(f'  NAS: ara no puc reanomenar «{c}» ({e}); s\'hi tornarà a provar')
        return False
    d['carpeta'] = nou
    d.pop('fmt_m', None)
    log(f'  NAS: carpeta «{c}» reanomenada a «{nou}» (hi faltava l\'any)')
    return True


def _text_id3(b):
    """Text d'un marc ID3v2 (el primer octet diu la codificació)."""
    if not b:
        return ''
    enc, b = b[0], b[1:]
    try:
        t = b.decode({0: 'latin-1', 1: 'utf-16', 2: 'utf-16-be', 3: 'utf-8'}.get(enc, 'latin-1'), 'replace')
    except (LookupError, UnicodeError):
        return ''
    return t.split('\x00')[0].strip()


def etiqueta_mp3(ruta):
    """L'artista, el disc i l'any que porta l'etiqueta ID3 d'un MP3 que ja és al PC. Només es llegeix l'etiqueta
    (uns pocs kB al principi o els 128 octets del final; la caràtula se salta): mai l'àudio, i res si l'arxiu és
    «a demanda». Torna {'artista', 'disc', 'any'} (els que hi hagi)."""
    st = os.stat(ruta)
    if getattr(st, 'st_file_attributes', 0) & NO_LOCAL:
        return {}
    out = {}
    with open(ruta, 'rb') as f:
        cap = f.read(10)
        if cap[:3] == b'ID3' and len(cap) == 10:
            ver = cap[3]
            fi = 10 + (cap[6] << 21 | cap[7] << 14 | cap[8] << 7 | cap[9])
            llarg_id, llarg_cap = (3, 6) if ver == 2 else (4, 10)
            noms = {'TP1': 'artista', 'TP2': 'artista2', 'TAL': 'disc', 'TYE': 'any'} if ver == 2 else \
                {'TPE1': 'artista', 'TPE2': 'artista2', 'TALB': 'disc', 'TYER': 'any', 'TDRC': 'any'}
            pos = 10
            while pos + llarg_cap <= fi and len(out) < 4:
                f.seek(pos)
                h = f.read(llarg_cap)
                if len(h) < llarg_cap or not h[:llarg_id].strip(b'\x00'):
                    break
                fid = h[:llarg_id].decode('latin-1')
                n = int.from_bytes(h[llarg_id:llarg_id + (3 if ver == 2 else 4)], 'big')
                if ver == 4:
                    n = h[4] << 21 | h[5] << 14 | h[6] << 7 | h[7]
                if n <= 0 or pos + llarg_cap + n > fi:
                    break
                if fid in noms and n < 4096:
                    t = _text_id3(f.read(n))
                    if t:
                        out.setdefault(noms[fid], t)
                pos += llarg_cap + n                    # els marcs grossos (la caràtula) no es llegeixen
        if not out.get('artista') and not out.get('artista2') and st.st_size > 128:
            f.seek(-128, 2)
            v1 = f.read(128)
            if v1[:3] == b'TAG':
                txt = lambda b: b.split(b'\x00')[0].decode('latin-1').strip()
                out = {'disc': txt(v1[63:93]), 'artista': txt(v1[33:63]), 'any': txt(v1[93:97])}
    art = out.get('artista2') or out.get('artista') or ''
    if '/' in art or ';' in art:
        art = out.get('artista2') or re.split(r'\s*[/;]\s*', art)[0]
    res = {'artista': art.strip(), 'disc': out.get('disc', '').strip()}
    m = re.match(r'^(\d{4})', out.get('any', '').strip())
    if m:
        res['any'] = m.group(1)
    return {k: v for k, v in res.items() if v}


def sense_artista(c):
    """La carpeta no porta l'artista: «2009 - Cycle of Pain» o «In the Red». Torna (any, títol) o None."""
    m = SENSE_ANY.match(c or '')
    if m and re.match(r'^\d{4}$', m.group(1).strip()):
        return m.group(1).strip(), m.group(2).strip()
    if not m and not CARPETA.match(c or ''):
        return '', (c or '').strip()
    return None


def artista_de_etiquetes(d, arrel, artistes):
    """Disc nou amb una carpeta sense l'artista: l'artista es treu de l'etiqueta dels MP3 (si ja són al PC), es
    torna a completar amb l'artista bo i la carpeta passarà a «Artista - Any - Títol». Torna True si l'ha canviat."""
    c = d.get('carpeta') or ''
    sa = sense_artista(c)
    nom = artistes.get(str(d.get('artista')), '')
    # només si l'artista de la fitxa és el que es va treure del nom de la carpeta (l'any o la carpeta sencera) i
    # encara no s'ha trobat a cap font d'internet (els recopilatoris «Varios» ja tenen fonts i no es toquen)
    if not sa or d.get('art_id3') or d.get('fonts') or N(nom) not in (N(sa[0]), N(c)):
        return False
    ruta = os.path.join(arrel, c)
    try:
        mp3 = sorted(os.path.join(r, f) for r, _, fs in os.walk(ruta) for f in fs if f.lower().endswith('.mp3'))
        et = {}
        for a in mp3[:3]:
            et = etiqueta_mp3(a)
            if et.get('artista'):
                break
    except OSError:
        return False
    art = majuscules(nom_carpeta(et.get('artista', '')))
    if not art or N(art) in (N(nom), N(sa[0])) or re.match(r'^\d{4}$', art):
        return False
    vell = d.get('artista')
    d['artista'] = id_artista(art, artistes)
    d['art_id3'] = True
    if sa[0] and not d.get('any'):
        d['any'] = sa[0]
    elif et.get('any') and not d.get('any'):
        d['any'] = et['any']
        d['auto'] = sorted(set(d.get('auto', [])) | {'any'})
    if not sa[0] and et.get('disc') and N(d.get('titol')) == N(c):
        d['titol'] = majuscules(et['disc'])
    for k in ('no_trobat', 'proc'):
        d.pop(k, None)
    d['reintenta'] = True
    log(f'  NAS: la carpeta «{c}» no porta l\'artista; segons els arxius és «{art}»')
    return vell


def posa_artista_carpeta(d, arrel, artistes):
    """Carpeta sense l'artista, amb l'artista ja tret dels arxius i l'any a la fitxa: «Artista - Any - Títol»."""
    c = d.get('carpeta') or ''
    sa = sense_artista(c)
    any_ = str(d.get('any') or '').strip()
    art = nom_carpeta(artistes.get(str(d.get('artista')), ''))
    if not sa or not d.get('art_id3') or not art or not re.match(r'^\d{4}$', any_):
        return False
    nou = f"{art} - {any_} - {majuscules(nom_carpeta(sa[1] if sa[0] else d.get('titol') or sa[1]))}"
    if nou.lower() != c.lower() and os.path.exists(os.path.join(arrel, nou)):
        log(f'  NAS: no reanomeno «{c}»: ja hi ha una carpeta «{nou}»')
        return False
    try:
        os.rename(os.path.join(arrel, c), os.path.join(arrel, nou))
    except OSError as e:
        log(f'  NAS: ara no puc reanomenar «{c}» ({e}); s\'hi tornarà a provar')
        return False
    d['carpeta'] = nou
    d.pop('fmt_m', None)
    log(f'  NAS: carpeta «{c}» reanomenada a «{nou}» (hi faltava l\'artista)')
    return True


CONFLICTE = re.compile(r'_(?:Case)?Conflict|\(Conflict', re.I)


def copies_arxius(d, arrel):
    """Arxius repetits dins de la carpeta d'un disc: el mateix tema dues vegades amb noms diferents
    («The Mighty Short Bus - Rogue Nation - 01 - Fire.mp3» i «Mighty Short Bus, The - Rogue Nation - 01 - Fire.mp3»).
    Passa quan el Synology Drive torna a crear l'arxiu amb el nom d'abans d'un canvi de nom (05/11/2026), o en fa
    una còpia de conflicte («..._CaseConflict.mp3»). Només són còpies si tenen la mateixa mida i el mateix número
    de pista, i la mateixa data (o una és còpia de conflicte); es queda el que ja té el format bo. No s'obre cap
    arxiu. Torna [(ruta de la còpia, ruta de la que es queda)]."""
    c = d.get('carpeta')
    m = CARPETA.match(c or '')
    ruta = os.path.join(arrel, c or '')
    if not m or not os.path.isdir(ruta):
        return []
    art, tit = m.group(1).strip(), m.group(3).strip()
    discs = {N(t[1]): int(t[3][2:]) for t in d.get('temes') or []
             if len(t) > 3 and re.match(r'^CD\d+$', str(t[3])) and N(t[1])}
    out = []
    for root, _, files in os.walk(ruta):
        sub = os.path.relpath(root, ruta)
        mc = re.search(r'(?:CD|Disc|Disco|Disk)\s*(\d{1,2})\b', sub, re.I) if sub != '.' else None
        grups = {}
        for f in files:
            if os.path.splitext(f)[1].lower() not in EXT:
                continue
            try:
                st = os.stat(os.path.join(root, f))
            except OSError:
                continue
            if st.st_size:
                grups.setdefault((st.st_size, os.path.splitext(f)[1].lower()), []).append((f, st.st_mtime))
        for (_, ext), fs in grups.items():
            if len(fs) < 2:
                continue
            noms = {f: nom_arxiu(art, tit, os.path.splitext(f)[0], int(mc.group(1)) if mc else None, discs) for f, _ in fs}
            if any(not x for x in noms.values()) or len({x[0] for x in noms.values()}) != 1:
                continue        # no és clar que siguin el mateix tema: no es toca
            bons = [f for f, _ in fs if f == noms[f][1] + os.path.splitext(f)[1]]
            if len(bons) != 1:
                bons = [f for f, _ in fs if not CONFLICTE.search(f)]
            if len(bons) != 1:
                continue
            bo = bons[0]
            mt = dict(fs)[bo]
            for f, t in fs:
                if f != bo and (abs(t - mt) <= 2 or CONFLICTE.search(f)):
                    out.append((os.path.join(root, f), os.path.join(root, bo)))
    return out


def treu_copies_arxius(discs, arrel, mtimes):
    """Norma de l'Ignasi (05/11/2026): tot el que està repetit al NAS es mou a «Mi Musica\\.Paperera duplicats <data>»
    (no s'esborra; ell la revisa abans d'esborrar-la), amb un registre a dades/duplicats_moguts_<data>.txt.
    Només les carpetes que han canviat des de l'última vegada (camp dup_m). Cal que el NAS estigui connectat."""
    paperera = os.path.join(arrel, f'.Paperera duplicats {AVUI}')
    moguts = canvi = 0
    for d in discs:
        c = d.get('carpeta')
        if c not in mtimes or d.get('dup_m') == mtimes[c] or not CARPETA.match(c):
            continue
        n = 0
        for f, bo in copies_arxius(d, arrel):
            desti = os.path.join(paperera, os.path.relpath(f, arrel))
            try:
                os.makedirs(os.path.dirname(desti), exist_ok=True)
                if os.path.exists(desti):
                    b, e = os.path.splitext(desti)
                    desti = f'{b} ({int(time.time())}){e}'
                os.rename(f, desti)
            except OSError as e:
                log(f'  NAS: ara no puc moure la còpia «{os.path.relpath(f, arrel)}» ({e}); s\'hi tornarà a provar')
                n = -1
                break
            n += 1
            try:
                with open(os.path.join(comu.DADES, f'duplicats_moguts_{AVUI}.txt'), 'a', encoding='utf-8') as r:
                    r.write(f'{datetime.datetime.now():%H:%M:%S}\tarxiu repetit\t{os.path.relpath(f, arrel)}'
                            f'\t-> {os.path.relpath(desti, arrel)}\t(es queda «{os.path.basename(bo)}»)\n')
            except OSError:
                pass
        if n > 0:
            log(f'  NAS: {n} arxius repetits de «{c}» moguts a «.Paperera duplicats {AVUI}»')
            mtimes[c] = os.stat(os.path.join(arrel, c)).st_mtime
            moguts += n
        if n >= 0:
            d['dup_m'] = mtimes[c]
            canvi += 1
    if moguts:
        log(f'NAS: {moguts} arxius repetits moguts a «Mi Musica\\.Paperera duplicats {AVUI}»')
    return canvi


def formata_tots():
    """Cada vegada: les carpetes sense l'any passen a «Artista - Any - Títol» (si la fitxa ja té l'any), i els
    arxius de les carpetes noves o canviades, al format «Artista - Disc - 01 - Cançó».
    Si els temes de la fitxa són els que es van treure dels noms dels arxius, es tornen a llegir."""
    arrel = CFG.get('carpeta_musica', r'C:\SynologyMusic\Mi Musica')
    if not os.path.isdir(arrel) or not comu.nas_connectat():
        return          # sense connexió amb el NAS, els noms es canvien la propera vegada
    with comu.BLOC:
        discs = llegeix('discs.json', [])
        mtimes = {e.name: e.stat().st_mtime for e in os.scandir(arrel) if e.is_dir()}
        canvi = total = 0
        # primer, els arxius repetits (el mateix tema amb dos noms): si no, la carpeta no es pot formatar
        try:
            canvi += treu_copies_arxius(discs, arrel, mtimes)
        except Exception as e:
            log(f'  NAS: error buscant arxius repetits {e!r}')
        artistes = llegeix('artistes.json', {})
        vells = set()
        for d in discs:
            c = d.get('carpeta')
            if c not in mtimes or CARPETA.match(c):
                continue
            try:
                v = artista_de_etiquetes(d, arrel, artistes)
            except Exception as e:
                v = False
                log(f'  NAS: no puc llegir l\'etiqueta dels arxius de «{c}» ({e!r})')
            if v:
                vells.add(str(v))
                canvi += 1
            if neteja_titol_nou(d):
                canvi += 1
            if posa_artista_carpeta(d, arrel, artistes) or posa_any_carpeta(d, arrel):
                mtimes[d['carpeta']] = mtimes.pop(c)
                canvi += 1
        # l'artista equivocat («2009») sense cap altre disc: fora
        orfes = vells - {str(d.get('artista')) for d in discs}
        if orfes:
            for k in orfes:
                artistes.pop(k, None)
        if vells:
            desa('artistes.json', artistes)
        for d in discs:
            c = d.get('carpeta')
            # fmt_v 2: també els discos dobles («Disc 2»); les carpetes ja repassades es tornen a mirar un cop
            if c not in mtimes or (d.get('fmt_m') == mtimes[c] and d.get('fmt_v') == 2) or not CARPETA.match(c):
                continue
            n = formata_arxius(d, arrel)
            ruta = os.path.join(arrel, c)
            mt = os.stat(ruta).st_mtime
            if n >= 0:
                d['fmt_m'], d['fmt_v'] = mt, 2         # si un arxiu no s'ha pogut canviar, es torna a provar la propera vegada
            if n > 0:
                total += n
                if 'temes' in d.get('auto', []) and d.get('nas_t') == firma_temes(d.get('temes', [])):
                    relleeix_temes(d, ruta, mt)
                elif d.get('nas_m'):
                    d['nas_m'] = mt
            canvi += 1
        if canvi:
            desa('discs.json', discs)
    if total:
        log(f'NAS: {total} arxius amb el format «Artista - Disc - 01 - Cançó»')


def corregeix_artista(d, nou, vell, artistes):
    """El disc és d'un artista relacionat (el cantant en solitari, o el grup): la fitxa passa a l'artista bo.
    L'anterior es guarda a «artista_abans» i a dades/titols_corregits.txt. La carpeta del NAS no es toca."""
    d.setdefault('artista_abans', vell)
    d['artista'] = id_artista(nou, artistes)
    log(f'  Artista: «{vell} - {d.get("titol", "")}» és de «{nou}» segons Discogs')
    try:
        with open(os.path.join(comu.DADES, 'titols_corregits.txt'), 'a', encoding='utf-8') as f:
            f.write(f"{AVUI}\tartista\t{vell}\t{nou}\t{d.get('titol', '')}\n")
    except OSError:
        pass
    return nou


def revisa_titols(n=100):
    """Entrades antigues que Discogs no ha trobat mai: es tornen a buscar (també amb el títol mal escrit),
    unes quantes cada nit. Si es troben, el disc es torna a completar en aquesta mateixa tanda."""
    discs = llegeix('discs.json', [])
    artistes = llegeix('artistes.json', {})
    cua = [d for d in discs if 'Discogs' not in (d.get('fonts') or {}) and not d.get('tit_rev')
           and artistes.get(str(d.get('artista'))) and d.get('titol')][:n]
    if not cua:
        return
    estat('Revisant títols a Discogs…')
    desador, trobats, corregits = Desador(), 0, 0
    try:
        for d in cua:
            abans = json.loads(json.dumps(d))
            nom_art = artistes.get(str(d['artista']), '')
            temes = [t[1] for t in d.get('temes') or [] if len(t) > 1]
            try:
                temes = temes or temes_carpeta(d)
                dg = DG.cerca(nom_art, d['titol'], d.get('any', ''), temes) or DG.cerca_aprox(nom_art, d['titol'], temes, d.get('any', '')) \
                    or DG.cerca_relacionat(nom_art, d['titol'], d.get('any', ''))
            except Exception as e:
                log(f"  Discogs: error {e!r}")
                break
            d['tit_rev'] = AVUI
            if dg:
                trobats += 1
                d['reintenta'] = True
                if dg.get('relacionat'):
                    nom_art = corregeix_artista(d, dg['artista'], nom_art, artistes)
                    d['auto'] = sorted(set(d.get('auto', [])) | {'artista'})
                    corregits += 1
                if dg.get('aprox'):
                    corregeix_titol(d, dg['titol'], nom_art)
                    d['auto'] = sorted(set(d.get('auto', [])) | {'titol'})
                    corregits += 1
            desador.afegeix(abans, d)
    finally:
        desador.desa()
    log(f'Títols: {len(cua)} discos antics buscats a Discogs, {trobats} trobats, {corregits} títols o artistes corregits')


# ------------------------------------------------------------------ completar un disc
def mb_encaixa(mb, d, dg, temes_d):
    """MusicBrainz només busca per artista i títol, i hi ha artistes que es diuen igual (el «Borracho» de la maqueta
    de 1994 i el grup d'stoner de Washington). El disc trobat només es fa servir si s'hi assembla: almenys la meitat
    dels temes iguals o, si no hi ha temes per comparar, el mateix any que la fitxa o que Discogs."""
    meus = {NT(t) for t in temes_d or [] if NT(t)}
    seus = {NT(t.get('titol')) for t in mb.get('temes') or [] if NT(t.get('titol'))}
    if meus and seus:
        return len(meus & seus) >= max(1, min(len(meus), len(seus)) // 2)
    anys = {str(d.get('any') or '')[:4], str((dg or {}).get('any') or '')[:4]} - {''}
    if anys and mb.get('any'):
        return mb['any'] in anys
    return True


def treu_dades_mb(d, mb, dg, auto, fonts_d, estils_meus):
    """Si abans s'havia agafat aquest disc de MusicBrainz per error, se'n treuen l'enllaç i l'estil que havia posat el
    programa (només si és a «auto» i no ve de Discogs: els camps de l'Ignasi no es toquen mai)."""
    if fonts_d.get('MusicBrainz') == mb.get('url'):
        fonts_d.pop('MusicBrainz', None)
    gens = mb.get('generes') or []
    seus = {N(estils_meus.get(N(x), x)) for x in gens} | {N(x) for x in gens}
    de_dg = {N(x) for x in (dg or {}).get('estils', [])}
    if 'estil' in auto and d.get('estil') and N(d['estil']) in seus and N(d['estil']) not in de_dg:
        log(f"  Estil «{d['estil']}» tret: venia del disc equivocat de MusicBrainz")
        d.pop('estil', None)
        auto.discard('estil')


def completa(d, artistes, estils_meus):
    nom_art = artistes.get(str(d['artista']), '')
    titol = d.get('titol', '')
    auto = set(d.get('auto', []))
    fonts_d = dict(d.get('fonts', {}))
    canvis = []

    def omple(k, v):
        if v and not d.get(k):
            d[k] = v
            auto.add(k)
            canvis.append(k)

    # 1. Discogs: per codi de barres o número de catàleg si en tenim; si no, per artista i títol
    dg = None
    temes_d = []
    try:
        if d.get('barcode') or d.get('catno'):
            dg = DG.per_codi(d.get('barcode'), None if d.get('barcode') else d.get('catno'))
        if not dg and nom_art and titol:
            temes_d = [t[1] for t in d.get('temes', []) if len(t) > 1] or temes_carpeta(d)
            dg = DG.cerca(nom_art, titol, d.get('any', ''), temes_d) or DG.cerca_aprox(nom_art, titol, temes_d, d.get('any', '')) \
                or DG.cerca_relacionat(nom_art, titol, d.get('any', ''))
    except Exception as e:
        log(f'  Discogs: error {e!r}')
    if dg and dg.get('relacionat'):
        nom_art = corregeix_artista(d, dg['artista'], nom_art, artistes)
        auto.add('artista')
        canvis.append('artista')
    if dg and dg.get('aprox'):
        corregeix_titol(d, dg['titol'], nom_art)
        auto.add('titol')
        canvis.append('titol')
    if dg:
        if not nom_art and dg.get('artista'):
            d['artista'] = id_artista(dg['artista'], artistes)
            nom_art = dg['artista']
        omple('titol', dg.get('titol'))
        titol = d.get('titol', titol)
        fonts_d['Discogs'] = dg.get('url') or ''
        d['discogs_release'] = dg['id']
        omple('segell', dg.get('segell'))
        omple('edicio', ' '.join(x for x in [dg.get('pais'), dg.get('any')] if x))
        if any(s in suports(d) for s in ('cd', 'lp')):     # números d'edició només per als físics
            omple('catno', dg.get('catno'))
            omple('barcode', dg.get('barcode'))

    # 2. AllMusic: ja no es consulta (bloqueja l'accés automàtic des del 28/10/2026; decisió de l'Ignasi, 10/11/2026)
    am = None
    d.pop('am_error', None)
    # 2b. MusicBrainz (API oberta, permet l'accés automàtic)
    mb = None
    if not am and nom_art and titol:
        try:
            mb = fonts.musicbrainz(nom_art, titol)
        except Exception as e:
            log(f'  MusicBrainz: error {e!r}')
    if mb and not mb_encaixa(mb, d, dg, temes_d or [t[1] for t in d.get('temes', []) if len(t) > 1]):
        # un altre artista amb el mateix nom («Borracho»): ni l'enllaç ni les seves dades
        log(f"  MusicBrainz: el disc que hi ha ({mb['url']}) no és aquest (temes o any diferents), no es fa servir")
        treu_dades_mb(d, mb, dg, auto, fonts_d, estils_meus)
        mb = None
    if mb:
        fonts_d['MusicBrainz'] = mb['url']
    if am:
        fonts_d['AllMusic'] = am['url']
        omple('any', am.get('any') or str(((dg or {}).get('master') or {}).get('year') or ''))
        omple('genere', GEN.get(N(am.get('genere', '').split(',')[0]), am.get('genere', '').split(',')[0]))
        est = next((estils_meus[N(x)] for x in am.get('estils', []) if N(x) in estils_meus), (am.get('estils') or [None])[0])
        omple('estil', est)
        omple('clasamg', am.get('amg'))
    elif dg or mb:
        dg_, mb_ = dg or {}, mb or {}
        omple('any', str((dg_.get('master') or {}).get('year') or mb_.get('any') or dg_.get('any') or ''))
        # gènere ampli: el de Discogs; si no n'hi ha, el primer de MusicBrainz que encaixi amb els teus (Rock, Jazz...)
        omple('genere', GEN.get(N((dg_.get('generes') or [''])[0]), (dg_.get('generes') or [None])[0])
              or next((GEN[N(x)] for x in mb_.get('generes', []) if N(x) in GEN), None))
        # estil: primer un dels que ja fas servir, després el de Discogs i, si no, el de MusicBrainz
        cands = dg_.get('estils', []) + mb_.get('generes', [])
        est = next((estils_meus[N(x)] for x in cands if N(x) in estils_meus), None) or \
            (dg_.get('estils') or [None])[0] or ' '.join(w.capitalize() for w in (mb_.get('generes') or [''])[0].split()) or None
        omple('estil', est)

    # 3. Temes: conservem els teus noms i hi afegim el compositor
    ref = (am or {}).get('temes') or (dg or {}).get('temes') or (mb or {}).get('temes') or []
    ref_dg = (dg or {}).get('temes') or []
    ref_mb = (mb or {}).get('temes') or []
    temes = [list(x) + [''] * (6 - len(x)) for x in d.get('temes', [])]
    if not temes and ref:
        temes = [[t['n'], t['titol'], '', '', 0, 0] for t in ref]
        auto.add('temes'); canvis.append('temes')
    posat = False
    for t in temes:
        if t[2]:
            continue
        for llista in (ref, ref_dg, ref_mb):
            m = max(llista, key=lambda r: sim(r['titol'], t[1]), default=None)
            if m and sim(m['titol'], t[1]) > 0.75 and m['compositors']:
                t[2] = ' / '.join(m['compositors'])
                posat = True
                break
    if posat:
        auto.add('compositors'); canvis.append('compositors')
    firma_abans = firma_temes(temes)
    if posa_discs(temes, ref_dg + ref_mb):
        canvis.append('discs')
        if d.get('nas_t') == firma_abans:
            d['nas_t'] = firma_temes(temes)     # l'ordre nou no vol dir que hagis canviat els temes
        d.pop('fmt_m', None)                    # els arxius es tornaran a anomenar amb el seu disc
    d['temes'] = temes

    # 4. Intèrprets
    if not d.get('interprets'):
        P, vist = [], {}
        credits = list((am or {}).get('credits', [])) + list((dg or {}).get('credits', [])) + list((mb or {}).get('credits', []))
        for n, rol in credits:
            if not n or N(n) == N(nom_art):
                continue
            rols = [x.strip() for x in re.split(r',(?![^\[]*\])', rol) if x.strip()]
            conv = any(re.search(r'guest|featuring|played with', x, re.I) for x in rols)
            interpreta = any(re.match(r'performer', x, re.I) for x in rols)
            mus = [re.sub(r'\s*\[.*?\]', '', x).strip() for x in rols
                   if not NO_MUSICA.search(x) and not re.search(r'guest artist|^performer', x, re.I)]
            mus = [x for x in mus if x]
            if not mus and not conv and not interpreta:
                continue
            k = N(n)
            if k in vist:
                p = P[vist[k]]
                p[1] = ', '.join(dict.fromkeys([x for x in p[1].split(', ') if x] + [x for x in mus if x]))
                p[2] = p[2] or (1 if conv else 0)
            else:
                vist[k] = len(P)
                P.append([n, ', '.join(x for x in mus if x), 1 if conv else 0])
        if dg and len(P) < 3:
            try:
                for m in DG.membres(dg.get('artista_id')):
                    if N(m) not in vist:
                        P.append([m, '', 0])
            except Exception:
                pass
        if P:
            d['interprets'] = P
            auto.add('interprets'); canvis.append('interprets')

    # 4b. Bitrate: de la capçalera dels MP3 que ja són al PC; si no, mida de l'arxiu / durada dels temes
    variable = d.get('bitrate') == 'VBR'        # sabem que és variable però encara no en tenim la mitjana
    if (not d.get('bitrate') or variable) and d.get('carpeta'):
        d['br'] = 3          # ja s'ha provat amb el mètode nou
        try:
            br = bitrate_estimat(d, (am or {}).get('temes') or [], (dg or {}).get('temes') or [], variable, ref_mb,
                                 lambda: fonts.lastfm_temes(nom_art, titol, LFM) if nom_art and titol else [])
            if br:
                d['bitrate'] = br
                auto.add('bitrate'); canvis.append('bitrate')
        except Exception as e:
            log(f'  Bitrate: error {e!r}')

    # 5. Caràtula
    if not d.get('caratula'):
        for url in [(am or {}).get('caratula'), (dg or {}).get('caratula'), (mb or {}).get('caratula')]:
            if not url:
                continue
            b = fonts.descarrega(url)
            if b and b[:3] == b'\xff\xd8\xff':
                with open(os.path.join(comu.CARATULES, f"{d['id']}.jpg"), 'wb') as f:
                    f.write(b)
                d['caratula'] = True
                d['cv'] = int(time.time())
                auto.add('caratula'); canvis.append('caratula')
                break

    # 6. Recomanacions de l'artista (com a màxim un cop cada 6 mesos)
    try:
        recomana(d, nom_art, am, dg)
    except Exception as e:
        log(f'  Recomanacions: error {e!r}')

    d['fonts'] = fonts_d
    d['auto'] = sorted(auto)
    d['proc'] = AVUI
    if canvis:
        d['revisar'] = True
    if d.get('estat') == 'pendent' and (am or dg or mb):
        d.pop('estat')
    return canvis, bool(am), bool(dg), bool(mb)


def disc_de(r):
    """Número de CD d'un tema de Discogs («1-05», «CD2-03») o de MusicBrainz (camp «disc»); 0 si no en té."""
    if r.get('disc'):
        return int(r['disc'])
    m = re.match(r'^(?:CD|Disc)?\s*(\d{1,2})\s*[-.]\s*\d+$', str(r.get('n') or ''), re.I)
    return int(m.group(1)) if m else 0


def posa_discs(temes, refs):
    """Disc doble amb els números de pista repetits (dos «1», dos «2»...) i sense dir de quin CD és cada tema
    (els arxius no ho diuen): es mira a la llista de Discogs o MusicBrainz i s'endrecen per CD i número.
    Només si es troben tots els temes; si no, no es toca res."""
    nums_ = [str(t[0]).strip() for t in temes if str(t[0]).strip()]
    if not temes or any(str(t[3]).strip() for t in temes) or len(nums_) == len(set(nums_)):
        return False
    discs = {}
    for r in refs:
        k = disc_de(r)
        if k and N(r.get('titol')):
            discs.setdefault(N(r['titol']), k)
    if len(set(discs.values())) < 2:
        return False
    trobats = []
    for t in temes:
        k = discs.get(N(t[1])) or next((v for kk, v in discs.items() if SequenceMatcher(None, kk, N(t[1])).ratio() > 0.85), None)
        if not k:
            return False
        trobats.append(k)
    for t, k in zip(temes, trobats):
        t[3] = f'CD{k}'
    num = lambda t: int(re.sub(r'\D', '', str(t[0])) or 10 ** 4)
    temes.sort(key=lambda t: (int(t[3][2:]), num(t)))
    return True


def segons(t):
    p = [int(x) for x in re.findall(r'\d+', str(t or ''))]
    if len(p) == 2:
        return p[0] * 60 + p[1]
    if len(p) == 3:
        return p[0] * 3600 + p[1] * 60 + p[2]
    return 0


ESTANDARD = [96, 112, 128, 160, 192, 224, 256, 320]


# MP3 (MPEG-1 i 2/2.5, capa III): kbps per índex i freqüències de mostreig
KBPS = {1: (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),
        2: (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)}
HZ = {3: (44100, 48000, 32000), 2: (22050, 24000, 16000), 0: (11025, 12000, 8000)}
# Windows: arxius «a demanda» (Synology Drive, OneDrive...) que encara no s'han baixat al PC
NO_LOCAL = 0x1000 | 0x40000 | 0x400000        # OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS


def _trama(b, i):
    """Capçalera de trama MP3 a la posició i: (kbps, Hz, mostres per trama, llargada, versió, mono) o None."""
    if i + 4 > len(b) or b[i] != 0xFF or b[i + 1] & 0xE0 != 0xE0:
        return None
    ver, capa = b[i + 1] >> 3 & 3, b[i + 1] >> 1 & 3
    ib, ihz = b[i + 2] >> 4, b[i + 2] >> 2 & 3
    if ver == 1 or capa != 1 or ib in (0, 15) or ihz == 3:
        return None
    m1 = ver == 3
    kbps, hz = KBPS[1 if m1 else 2][ib], HZ[ver][ihz]
    mostres = 1152 if m1 else 576
    llarg = (144 if m1 else 72) * kbps * 1000 // hz + (b[i + 2] >> 1 & 1)
    return kbps, hz, mostres, llarg, m1, b[i + 3] >> 6 == 3


def capcalera_mp3(ruta, mida):
    """Qualitat real d'un MP3 que ja és al PC, llegint només la capçalera (uns pocs kB, mai l'àudio sencer).
    Torna (kbps, segons, fix) o None si no s'entén."""
    with open(ruta, 'rb') as f:
        cap = f.read(10)
        inici = 0
        if cap[:3] == b'ID3' and len(cap) == 10:          # etiqueta ID3v2 (pot dur la caràtula): se salta
            inici = 10 + (cap[6] << 21 | cap[7] << 14 | cap[8] << 7 | cap[9]) + (10 if cap[5] & 0x10 else 0)
        f.seek(inici)
        b = f.read(16384)
    for i in range(min(len(b) - 4, 8192)):
        t = _trama(b, i)
        if not t:
            continue
        kbps, hz, mostres, llarg, m1, mono = t
        seg = _trama(b, i + llarg)
        if not seg or seg[1] != hz:              # una sincronia falsa: cal que la trama següent també encaixi
            continue
        o = i + 4 + ((17 if mono else 32) if m1 else (9 if mono else 17))
        etiq = b[o:o + 4]
        if etiq in (b'Xing', b'Info') and len(b) >= o + 16:
            flags = int.from_bytes(b[o + 4:o + 8], 'big')
            trames = int.from_bytes(b[o + 8:o + 12], 'big') if flags & 1 else 0
            octets = int.from_bytes(b[o + 12:o + 16], 'big') if flags & 1 and flags & 2 else 0
            if trames:
                s = trames * mostres / hz
                octets = octets or (mida - inici - i)
                if etiq == b'Info':                   # LAME en mode fix: la trama d'informació du el bitrate
                    return kbps, s, True
                return octets * 8 / s / 1000, s, False
        if b[i + 36:i + 40] == b'VBRI' and len(b) >= i + 58:          # capçalera de Fraunhofer
            octets = int.from_bytes(b[i + 46:i + 50], 'big')
            trames = int.from_bytes(b[i + 50:i + 54], 'big')
            if trames:
                s = trames * mostres / hz
                return octets * 8 / s / 1000, s, False
        # sense capçalera VBR: fix si les trames següents tenen el mateix bitrate
        j, vistos = i, set()
        for _ in range(6):
            t2 = _trama(b, j)
            if not t2:
                break
            vistos.add(t2[0])
            j += t2[3]
        if len(vistos) == 1:
            return kbps, (mida - inici - i) * 8 / (kbps * 1000), True
        return None
    return None


def bitrate_capcaleres(mp3, variable=False):
    """Bitrate del disc a partir de la capçalera dels MP3 que ja són al PC (no en descarrega cap)."""
    llegits = []
    for ruta, mida, local in mp3:
        if not local:
            continue
        try:
            r = capcalera_mp3(ruta, mida)
        except OSError:
            r = None
        if r:
            llegits.append(r)
    if not llegits or len(llegits) < min(3, len(mp3)):
        return None
    fixos = {round(k) for k, _, fix in llegits if fix}
    if not variable and len(fixos) == 1 and all(fix for *_, fix in llegits):
        return str(fixos.pop())
    kbps = sum(k * s for k, s, _ in llegits) / sum(s for _, s, _ in llegits)
    return f'VBR ~{round(kbps)}'


def bitrate_estimat(d, temes_am, temes_dg, variable=False, temes_mb=(), temes_extra=None):
    """Bitrate dels MP3 del NAS. Primer, la capçalera dels arxius que ja són al PC (exacte, només uns kB);
    si són «a demanda» i no s'han baixat, no s'obren: mida de l'arxiu / durada del tema.
    Cada arxiu s'aparella amb el seu tema pel número o pel nom, així funciona encara que hi hagi
    temes extra o en faltin. temes_extra és una funció que dona més durades (Last.fm) si cal."""
    carpeta = os.path.join(CFG.get('carpeta_musica', r'C:\SynologyMusic\Mi Musica'), d['carpeta'])
    if not os.path.isdir(carpeta):
        return None
    mp3, flac = [], False
    for root, _, files in os.walk(carpeta):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext == '.flac':
                flac = True
            if ext == '.mp3':
                st = os.stat(os.path.join(root, f))
                local = not getattr(st, 'st_file_attributes', 0) & NO_LOCAL
                mp3.append((f, st.st_size, os.path.join(root, f), local))
    if flac and not mp3:
        return 'Flac'
    if not mp3:
        return None
    br = bitrate_capcaleres([(r, m, l) for _, m, r, l in mp3], variable)
    if br:
        return br
    mp3 = [(f, mida) for f, mida, _, _ in mp3]
    refs = [temes_am, temes_dg, temes_mb]
    if temes_extra:
        refs.append(temes_extra)
    for ref in refs:
        if callable(ref):
            try:
                ref = ref() or []
            except Exception as e:
                log(f'  Last.fm (durades): error {e!r}')
                ref = []
        temes = [(str(t.get('titol') or ''), segons(t.get('durada'))) for t in ref]
        temes = [x for x in temes if x[1] > 0]
        if not temes:
            continue
        # 1) mateix nombre d'arxius i de temes: tots en ordre
        if len(temes) == len(mp3):
            parells = [(m[1], t[1]) for m, t in zip(sorted(mp3), temes)]
        else:
            # 2) aparellar pel nom del tema dins del nom de l'arxiu
            parells, usats = [], set()
            for f, mida in mp3:
                nom = N(re.sub(r'^[\d\s._-]+', '', os.path.splitext(f)[0]))
                millor, s = None, 0
                for k, (tt, dur) in enumerate(temes):
                    if k in usats or not N(tt):
                        continue
                    q = 1.0 if N(tt) in nom else SequenceMatcher(None, N(tt), nom[-len(N(tt)) - 2:]).ratio()
                    if q > s:
                        millor, s = k, q
                if millor is not None and s >= 0.8:
                    usats.add(millor)
                    parells.append((mida, temes[millor][1]))
            if len(parells) < max(3, len(mp3) * 0.6):
                continue
        kbps = sum(m for m, _ in parells) * 8 / sum(s for _, s in parells) / 1000
        prop = min(ESTANDARD, key=lambda x: abs(x - kbps))
        # valor fix (192, 320...) o variable amb la mitjana real del disc: «VBR ~208»
        if variable or abs(prop - kbps) / prop >= 0.06:
            return f'VBR ~{round(kbps)}'
        return str(prop)
    return None


RECS_V = 2      # 2: amb l'enllaç de cada font i discos dels artistes similars de Last.fm


def recomana(d, nom_art, am, dg):
    recs = llegeix('recs.json', {})
    k = str(d['artista'])
    vell = recs.get(k)
    if vell and vell.get('updatedAt', '') > (datetime.date.today() - datetime.timedelta(days=180)).isoformat() \
            and len(vell.get('fonts', [])) >= 3 and (not am or 'AllMusic' in vell.get('fonts', [])) \
            and vell.get('v', 1) >= RECS_V and (not LFM or 'Last.fm' in vell.get('fonts', [])):
        return
    me = N(nom_art)
    A, D = {}, {}

    def addA(nom, font, pos, url=''):
        n = N(nom)
        if not n or n == me:
            return
        e = A.setdefault(n, {'nom': re.sub(r'\s*\(\d+\)$', '', nom), 'fonts': [], 'pos': 0, 'urls': {}})
        if font not in e['fonts']:
            e['fonts'].append(font); e['pos'] += pos
        if url and font not in e['urls']:
            e['urls'][font] = url

    def addD(titol, artista, font, pos, any_='', url=''):
        # sense artista = un altre disc del mateix artista (Apple Music no repeteix el nom): no és una descoberta
        if not titol or not str(artista or '').strip() or N(artista) == me:
            return
        t = re.sub(r'\s*[\(\[](deluxe|remaster|expanded|\d+th anniversary|anniversary)[^\)\]]*[\)\]]', '', titol, flags=re.I).replace(' - EP', '').strip()
        key = N(artista) + '|' + N(t)
        e = D.setdefault(key, {'artista': re.sub(r'\s*\(\d+\)$', '', artista), 'titol': t, 'any': any_, 'fonts': [], 'pos': 0, 'urls': {}})
        if font not in e['fonts']:
            e['fonts'].append(font); e['pos'] += pos
        if url and font not in e['urls']:
            e['urls'][font] = url
        if any_ and not e['any']:
            e['any'] = any_

    usades = []
    if am:
        usades.append('AllMusic')
        for p, x in enumerate(am.get('artistes_similars', [])): addA(x, 'AllMusic', p)
        for p, x in enumerate(am.get('similars', [])): addD(x['titol'], x['artista'], 'AllMusic', p, x.get('any', ''))
    tinc = {N(v) for v in llegeix('artistes.json', {}).values()}
    if LFM:
        try:
            L = fonts.lastfm_similars(nom_cerca(nom_art), LFM)
            if L:
                usades.append('Last.fm')
            for p, x in enumerate(L): addA(x['nom'], 'Last.fm', p, x['url'])
            # discos: els més escoltats dels primers artistes similars que encara no tens
            for p, x in enumerate([x for x in L if N(x['nom']) not in tinc][:8]):
                for q, al in enumerate(fonts.lastfm_discos(x['nom'], LFM)):
                    addD(al['titol'], al['artista'], 'Last.fm', p + q, url=al['url'])
        except Exception as e:
            log(f'  Last.fm: error {e!r}')
    try:
        ap = fonts.apple(nom_cerca(nom_art), d.get('titol', ''))
        if ap['artistes'] or ap['discos']:
            usades.append('Apple Music')
        for p, x in enumerate(ap['artistes']): addA(x['nom'], 'Apple Music', p, x['url'])
        for p, x in enumerate(ap['discos']): addD(x['titol'], x['artista'], 'Apple Music', p, url=x['url'])
    except Exception as e:
        log(f'  Apple Music: error {e!r}')
    if dg:
        rr = DG.recomanacions(dg['id'])
        if rr:
            usades.append('Discogs')
        for p, x in enumerate(rr):
            addD(x['titol'], x['artista'], 'Discogs', p, url=x.get('url', ''))
            addA(x['artista'], 'Discogs', p)
    for e in D.values():
        a = A.get(N(e['artista']))
        if a:
            for f in e['fonts']:
                if f not in a['fonts']:
                    a['fonts'].append(f)
    for e in A.values():
        e['score'] = len(e['fonts'])
    for e in D.values():
        e['score'] = 2 * len(e['fonts']) + A.get(N(e['artista']), {}).get('score', 0)
    srt = lambda L: sorted(L, key=lambda e: (-e['score'], e['pos'] / max(1, len(e['fonts']))))
    if not A and not D:
        return
    recs = llegeix('recs.json', {})
    recs[k] = {'artista': nom_art, 'fonts': usades, 'updatedAt': AVUI, 'v': RECS_V,
               'artistes': [{x: e[x] for x in ('nom', 'fonts', 'score', 'urls')} for e in srt(A.values())][:40],
               'discos': [{x: e[x] for x in ('artista', 'titol', 'any', 'fonts', 'score', 'urls')} for e in srt(D.values())][:40]}
    desa('recs.json', recs)


CLAUS = ('any', 'genere', 'estil', 'clasamg', 'segell', 'bitrate', 'caratula', 'temes', 'interprets')


def incomplet(d):
    if any(not d.get(k) for k in CLAUS):
        return True
    return any(len(t) > 2 and not t[2] for t in d.get('temes', []))   # temes sense compositor


def resum():
    discs = llegeix('discs.json', [])
    fets = sum(1 for d in discs if d.get('proc'))
    complets = sum(1 for d in discs if not incomplet(d))
    return f'{fets}/{len(discs)} repassats · {complets} complets del tot'


def clau_rec(s):
    """La mateixa clau que fa servir la pàgina per comparar noms (tok2)."""
    import unicodedata
    s = unicodedata.normalize('NFD', str(s or '').lower())
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r'^the\s+|,\s*the$', '', s)
    return re.sub(r'[^a-z0-9]', '', s)


def nom_cerca(nom):
    """«Afghan Whigs, The» -> «The Afghan Whigs» per buscar-lo a Last.fm."""
    m = re.match(r'^(.*),\s*(the|los|las|el|la|les)$', str(nom or '').strip(), re.I)
    return f'{m.group(2)} {m.group(1)}' if m else str(nom or '').strip()


def perfil_lastfm(maxim=600):
    """Etiquetes d'estil i oients de Last.fm: primer dels teus artistes (per fer el teu perfil musical)
    i després dels artistes recomanats (per saber quant s'hi assemblen i si són molt coneguts)."""
    if not LFM:
        log('Perfil musical: falta la clau de Last.fm')
        return 0
    lf = llegeix('lastfm.json', {})
    fa1any = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    meus = llegeix('artistes.json', {})
    amb_discs = {str(d.get('artista')) for d in llegeix('discs.json', [])}
    noms = {}
    for k, v in meus.items():
        if k in amb_discs:
            noms.setdefault(clau_rec(v), v)
    for r in llegeix('recs.json', {}).values():
        for x in (r or {}).get('artistes', []):
            noms.setdefault(clau_rec(x.get('nom')), x.get('nom'))
        for x in (r or {}).get('discos', []):
            noms.setdefault(clau_rec(x.get('artista')), x.get('artista'))
    falten = [(k, v) for k, v in noms.items() if k and (k not in lf or lf[k].get('d', '') < fa1any)][:maxim]
    if falten:
        log(f'Perfil musical: consultant {len(falten)} artistes a Last.fm')
    fets = 0
    for k, nom in falten:
        try:
            x = fonts.lastfm_info(nom_cerca(nom), LFM)
        except Exception:
            x = None
        lf[k] = dict(x or {'o': None, 't': []}, d=AVUI)
        fets += 1
        if fets % 100 == 0:
            desa('lastfm.json', lf)
    if fets:
        desa('lastfm.json', lf)
        log(f'Perfil musical: {fets} artistes actualitzats')
    return fets


def marca_dobles():
    """Un sol cop: els discos amb números de pista repetits i sense CD (discos dobles com «The Fragile») es tornen
    a completar, perquè Discogs o MusicBrainz diguin de quin CD és cada tema."""
    fetes = llegeix('migracions.json', {})
    if fetes.get('discs_dobles'):
        return
    with comu.BLOC:
        discs = llegeix('discs.json', [])
        n = 0
        for d in discs:
            t = d.get('temes') or []
            nums_ = [str(x[0]).strip() for x in t if x and str(x[0]).strip()]
            if len(nums_) != len(set(nums_)) and not any(len(x) > 3 and str(x[3]).strip() for x in t):
                d['reintenta'] = True
                n += 1
        if n:
            desa('discs.json', discs)
    fetes['discs_dobles'] = AVUI
    desa('migracions.json', fetes)
    log(f'Discos dobles: {n} discos es tornaran a completar per saber de quin CD és cada tema')


def deixa_allmusic():
    """Un sol cop (10/11/2026): AllMusic ja no es consulta, així que els discos que esperaven tornar-hi a provar
    (marca `am_error`) deixen d'esperar. Les dades que ja tenien d'AllMusic es queden igual."""
    fetes = llegeix('migracions.json', {})
    if fetes.get('allmusic_deixat'):
        return
    with comu.BLOC:
        discs = llegeix('discs.json', [])
        n = 0
        for d in discs:
            if d.pop('am_error', None) is not None:
                n += 1
        if n:
            desa('discs.json', discs)
    fetes['allmusic_deixat'] = AVUI
    desa('migracions.json', fetes)
    log(f"AllMusic: ja no es consulta; {n} discos deixen d'esperar-lo")


# Textos en castellà de les entrades antigues, en català. Només es canvien els valors que coincideixen
# exactament (sense distingir majúscules): la resta de textos que hagis escrit no es toquen.
QUALITAT_CA = {
    'buena': 'bona', 'bueno': 'bona', 'buen': 'bona', 'buens': 'bona', 'bunea': 'bona', 'bguena': 'bona',
    'media': 'mitjana', 'mala': 'dolenta', 'excelente': 'excel·lent', 'distorsionado': 'distorsionada',
    'saturado': 'saturada', 'ruidos': 'sorolls', 'sonido flojo': 'so fluix',
    'mal ripeado': 'mal ripejada', 'mal rippeado': 'mal ripejada',
}
NOTES_CA = {
    'directo': 'En directe', 'live': 'En directe', 'disco directo': 'Disc en directe',
    'disco en directo': 'Disc en directe', 'album en directo': 'Àlbum en directe',
    'acoustic': 'Acústic', 'unreleased': 'Inèdit',
    'bajando torrent': 'baixant torrent', 'se oye flojo': 'se sent fluix',
    'ultima se oye mal 21-7-14 hay q bajarlo de nuevo': "l'última se sent malament 21-7-14, cal tornar-lo a baixar",
    'libro 2001 discos': 'Llibre 2001 discos', 'bajando nuevo 320': 'baixant-ne un de nou a 320',
    'bajando nuevo a 320': 'baixant-ne un de nou a 320', '10 mal': 'la 10 malament',
    'falta tema 11': 'falta el tema 11', 'mal ripeado': 'mal ripejat', 'buscar mas discos': 'buscar més discos',
    'buscar mas pasar carlos': 'buscar-ne més, passar a Carlos',
    'distorsionado bajando otra version': 'distorsionat, baixant una altra versió', 'bajando nuevo': 'baixant-ne un de nou',
    'disco de rarezas solo en vinilo': 'Disc de rareses només en vinil',
    'la 4 mal ripeaada, bajando nuevo': 'la 4 mal ripejada, baixant-ne un de nou', 'bajando a 320': 'baixant a 320',
    'miembro de storyville': 'membre de Storyville', 'suena un poco flojo': 'sona una mica fluix',
    'descargando otro': 'baixant-ne un altre',
}


def tradueix_catala():
    """Passa al català la qualitat i les notes que encara són en castellà (també les que arribin del mòbil).
    El primer cop guarda una còpia de discs.json a dades\\copies\\catala-discs-abans.json."""
    with comu.BLOC:
        discs = llegeix('discs.json', [])
        n = 0
        for d in discs:
            for camp, dicc in (('qualitat', QUALITAT_CA), ('notes', NOTES_CA)):
                v = d.get(camp)
                nou = dicc.get(str(v).strip().lower()) if isinstance(v, str) else None
                if nou and nou != v:
                    d[camp] = nou
                    n += 1
        if n:
            copia = os.path.join(comu.COPIES, 'catala-discs-abans.json')
            if not os.path.exists(copia):
                shutil.copy2(os.path.join(comu.DADES, 'discs.json'), copia)
            desa('discs.json', discs)
            log(f'Català: {n} textos de les entrades traduïts')


NOTES_NUM = ('classificacio', 'clasamg')


def decimal(v):
    """«7,5» → «7.5»: les notes sempre amb punt decimal. Només toca els números escrits amb coma."""
    if isinstance(v, str) and re.fullmatch(r'\s*\d*,\d+\s*', v):
        return v.strip().replace(',', '.')
    return v


def normalitza_notes():
    """Posa el punt decimal a la meva nota i a la d'AllMusic (també a les que arribin del mòbil).
    El primer cop guarda una còpia de discs.json a dades\\copies\\notes-punt-discs-abans.json."""
    with comu.BLOC:
        discs = llegeix('discs.json', [])
        n = 0
        for d in discs:
            for camp in NOTES_NUM:
                nou = decimal(d.get(camp))
                if nou != d.get(camp):
                    d[camp] = nou
                    n += 1
        if n:
            copia = os.path.join(comu.COPIES, 'notes-punt-discs-abans.json')
            if not os.path.exists(copia):
                shutil.copy2(os.path.join(comu.DADES, 'discs.json'), copia)
            desa('discs.json', discs)
            log(f'Notes: {n} notes passades a punt decimal')


def tanda(mode, n, id_=None):
    artistes = llegeix('artistes.json', {})
    discs = llegeix('discs.json', [])
    estils_meus = {N(d['estil']): d['estil'] for d in discs if d.get('estil')}
    if mode == 'disc':
        cua = [d for d in discs if str(d.get('id')) == str(id_)]
    else:
        fa7 = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        pend = [d for d in discs if d.get('reintenta') or (d.get('estat') == 'pendent' and (not d.get('proc') or d['proc'] < fa7))]
        pend.sort(key=lambda d: d.get('proc') or '')
        if mode == 'pendents':
            cua = pend
        else:
            # 1r pendents, 2n tota la resta de la biblioteca que encara no s'ha repassat mai,
            # 3r els que es van repassar fa més de 90 dies i encara els falta alguna dada
            fa90 = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
            mai = [d for d in discs if d.get('estat') != 'pendent' and not d.get('proc') and not d.get('reintenta')]
            falten = [d for d in discs if d.get('estat') != 'pendent' and d.get('proc') and d['proc'] < fa90 and incomplet(d)]
            falten.sort(key=lambda d: d['proc'])
            # discos ja repassats que es van quedar sense bitrate: es tornen a provar un cop
            sense_br = [d for d in discs if d.get('carpeta') and (not d.get('bitrate') and d.get('proc') or d.get('bitrate') == 'VBR')
                        and (d.get('br') or 0) < 3 and d.get('estat') != 'pendent']
            ja = {id(x) for x in pend + sense_br}
            cua = pend + sense_br + mai + [d for d in falten if id(d) not in ja]
    total = min(n, len(cua))
    log(f'Tanda «{mode}»: {total} discos')
    fets, compte = 0, {'dg': 0, 'mb': 0}
    desador = Desador()
    try:
        i = 0
        for d in cua:
            if i >= total:
                break
            i += 1
            nom = f"{artistes.get(str(d['artista']), '?')} - {d.get('titol', '')}"
            estat(f'{i}/{total} · {nom}')
            abans = json.loads(json.dumps(d))
            try:
                d.pop('reintenta', None)
                canvis, am, dg, mb = completa(d, artistes, estils_meus)
                log(f"  {nom}: {', '.join(canvis) or 'res de nou'} (Discogs {'sí' if dg else 'no'}"
                    f", MusicBrainz {'sí' if mb else 'no'})")
                compte['dg'] += 1 if dg else 0
                compte['mb'] += 1 if mb else 0
                if not am and not dg and not mb:
                    d['no_trobat'] = AVUI
                elif am or dg or mb:
                    d.pop('no_trobat', None)
                fets += 1 if canvis else 0
            except Exception as e:
                log(f'  {nom}: ERROR {e!r}')
                d['proc'] = AVUI
                d['proc_error'] = str(e)[:200]
            desador.afegeix(abans, d)
    finally:
        desador.desa()
    if cua:
        log(f"Fonts en aquesta tanda: Discogs {compte['dg']} discos · MusicBrainz {compte['mb']} discos (AllMusic ja no es consulta)")
    return fets


# ------------------------------------------------------------------ Discogs: col·lecció física
ALIES = {('ledzeppelin', 'untitled'): 'ledzeppeliniv', ('ledzeppelin', 'fourlights'): 'ledzeppeliniv'}


def iguals(t1, t2):
    a, b = net_titol(t1), net_titol(t2)
    if a == b:
        return True
    # sense cap parèntesi: "Excerpts From Outside (The Nathan Adler Diaries...)"
    a2, b2 = N(re.sub(r'[\(\[].*?[\)\]]', '', str(t1 or ''))), N(re.sub(r'[\(\[].*?[\)\]]', '', str(t2 or '')))
    return bool(a2) and a2 == b2


def net_titol(t):
    t = re.sub(r'\s*[\(\[][^\)\]]*(remaster\w*|deluxe|edition|edici\w*|expanded|anniversary|bonus|reissue|version|mono\b|stereo|ep\b)[^\)\]]*[\)\]]', '', str(t or ''), flags=re.I)
    return N(t)


def sincronitza_discogs():
    usuari = CFG.get('usuari_discogs', 'itutzo')
    if not DG.h:
        log('Falta la clau de Discogs a config.ini')
        return
    estat('Llegint la col·lecció de Discogs…')
    col = DG.coleccio(usuari)
    log(f'Discogs: {len(col)} edicions a la col·lecció de {usuari}')
    artistes = llegeix('artistes.json', {})
    discs = llegeix('discs.json', [])
    per_art = {}
    for d in discs:
        per_art.setdefault(N(artistes.get(str(d['artista']), '')), []).append(d)
    nous, actualitzats, informe = 0, 0, []
    for r in col:
        b = r.get('basic_information', {})
        art = re.sub(r'\s*\(\d+\)$', '', (b.get('artists') or [{}])[0].get('name', ''))
        tit = b.get('title', '')
        fmt = ' '.join(f.get('name', '') + ' ' + ' '.join(f.get('descriptions', [])) for f in b.get('formats', [])).lower()
        sup = 'lp' if ('vinyl' in fmt or ' lp' in ' ' + fmt) else 'cd' if 'cd' in fmt else None
        if not sup:
            continue
        cands = per_art.get(N(art), [])
        if not cands:   # "Black Crowes, The" / "The Black Crowes" / "Tool (2)"
            cands = [x for k, L in per_art.items() if k and (k in N(art) or N(art) in k) and min(len(k), len(N(art))) > 3 for x in L]
        tit_cmp = ALIES.get((N(art), N(tit)), tit)
        d = next((x for x in cands if not str(x.get('id')).startswith('dg') and
                  (iguals(x.get('titol'), tit) or N(x.get('titol')) == tit_cmp)), None) or \
            next((x for x in cands if iguals(x.get('titol'), tit)), None)
        if not d and cands:
            m = max(cands, key=lambda x: SequenceMatcher(None, net_titol(x.get('titol')), net_titol(tit)).ratio())
            if SequenceMatcher(None, net_titol(m.get('titol')), net_titol(tit)).ratio() > 0.8:
                d = m
        seg = ', '.join(dict.fromkeys(re.sub(r'\s*\(\d+\)$', '', l['name']) for l in b.get('labels', [])))
        cat = ', '.join(dict.fromkeys(l.get('catno', '') for l in b.get('labels', []) if l.get('catno') and l.get('catno') != 'none'))
        dup = next((x for x in discs if str(x.get('id')) == f"dg{b.get('id')}"), None)
        if d and dup and d is not dup and dup.get('estat') == 'pendent' and not dup.get('updatedAt'):
            discs.remove(dup)           # duplicat creat abans: el fusionem amb el teu disc
            per_art.get(N(art), []).remove(dup) if dup in per_art.get(N(art), []) else None
            informe.append(f"FUSIONAT {art} - {tit}")
        if d:
            canvi = afegeix_suport(d, sup)
            if not d.get('discogs_release'):
                d['discogs_release'] = b.get('id'); canvi = True
            for k, v in (('segell', seg), ('catno', cat)):
                if v and not d.get(k):
                    d[k] = v; canvi = True
                    d['auto'] = sorted(set(d.get('auto', [])) | {k})
            if canvi:
                d['auto'] = sorted(set(d.get('auto', [])) | {'suport'})
                actualitzats += 1
                informe.append(f"MARCAT {sup.upper():3} {art} - {tit}  ->  {artistes.get(str(d['artista']))} - {d.get('titol')}")
        else:
            d = {'id': f"dg{b.get('id')}", 'artista': id_artista(art, artistes), 'titol': tit, 'suport': sup,
                 'any': str(b.get('year') or '') or None, 'discogs_release': b.get('id'), 'estat': 'pendent',
                 'data': (r.get('date_added') or AVUI)[:10], 'temes': [], 'interprets': [], 'segell': seg, 'catno': cat,
                 'auto': ['titol', 'suport', 'segell', 'catno']}
            if any(str(x.get('id')) == d['id'] for x in discs):
                continue
            d = {k: v for k, v in d.items() if v not in (None, '')}
            discs.append(d)
            per_art.setdefault(N(art), []).append(d)
            nous += 1
            informe.append(f"NOU    {sup.upper():3} {art} - {tit}  (no estava al catàleg: creat com a pendent)")
    desa('discs.json', discs)
    with open(os.path.join(comu.DADES, 'discogs_informe.txt'), 'w', encoding='utf-8') as f:
        f.write(f'Sincronització amb Discogs {datetime.datetime.now():%d/%m/%Y %H:%M}\n\n' + '\n'.join(sorted(informe)))
    log(f'Discogs: {actualitzats} discos marcats com a CD/vinil, {nous} discos nous (pendents). Detall a dades\\discogs_informe.txt')


# ------------------------------------------------------------------ NAS: només noms, no descarrega res
EXT = {'.mp3': 'mp3', '.flac': 'flac', '.m4a': 'aac', '.wma': 'wma', '.wav': 'wav', '.ogg': 'ogg', '.ape': 'ape'}


# número de pista dins del nom de l'arxiu: «Artista - Disc - 03 - Títol», «03. Títol», «12 Títol»
PISTA = (re.compile(r'.*\s[-–—]\s*(\d{1,3})\s*(?:[-–—]|\.(?!\d))\s*(\S.*)$'),
         re.compile(r'^(\d{1,3})\s*(?:[-–—]|\.(?!\d))\s*(\S.*)$'),
         re.compile(r'^(?:.*\s[-–—]\s*)?(\d{1,3})\s+(\S.*)$'))


def num_titol(nom):
    for r in PISTA:
        m = r.match(nom)
        if m:
            return m.group(1).lstrip('0') or '0', m.group(2).strip()
    return '', nom


# si un tema és a la carpeta en dos formats, el títol de la fitxa és el de l'arxiu de més qualitat
ORDRE_FORMAT = {'.flac': 0, '.ape': 1, '.wav': 2, '.m4a': 3, '.mp3': 4, '.ogg': 5, '.wma': 6}


def temes_de_noms(arxius):
    out = []
    multi = len({s for s, _ in arxius}) > 1 or any(re.search(r'- (?:CD|Disc) ?\d+ -', a) for _, a in arxius)
    for sub, a in arxius:
        nom, ext = os.path.splitext(a)
        cd = re.search(r'(?:CD|Disc)\s*(\d+)', sub + ' ' + nom, re.I)
        num, tit = num_titol(nom)
        clau = (sub, int(cd.group(1)) if cd else 0, int(num) if num else 10 ** 4, a.lower())
        out.append((clau, ext.lower(), [num, tit, '', ('CD' + cd.group(1)) if (multi and cd) else '', 0, 0]))
    # el mateix tema en dos formats («01 - Try.flac» i «01 - Try.mp3»: mateixa subcarpeta, CD i número, un arxiu de
    # cada format) és un sol tema a la fitxa, amb el títol de l'arxiu de més qualitat
    grups = {}
    for x in out:
        if x[2][0]:
            grups.setdefault(x[0][:3], []).append(x)
    fora = set()
    for g in grups.values():
        exts = [x[1] for x in g]
        if len(g) > 1 and len(set(exts)) == len(exts):
            bo = min(g, key=lambda x: ORDRE_FORMAT.get(x[1], 9))
            fora |= {id(x) for x in g if x is not bo}
    return [t for c, _, t in sorted((x for x in out if id(x) not in fora), key=lambda x: x[0])]   # per número de pista


def arxius_de(ruta):
    """Només els noms dels arxius de música (no obre ni descarrega res)."""
    arxius = []
    for root, _, files in os.walk(ruta):
        sub = os.path.relpath(root, ruta)
        arxius += [('' if sub == '.' else sub, f) for f in files if os.path.splitext(f)[1].lower() in EXT]
    return arxius


def firma_temes(temes):
    return '|'.join(f'{t[0]}.{t[1]}' for t in temes)


def relleeix_temes(d, ruta, mtime):
    """Els temes que es van treure dels noms dels arxius es tornen a llegir si has canviat els arxius.
    Si els has corregit a la Discoteca (la firma ja no coincideix), no es toquen."""
    d['nas_m'] = mtime
    nous = temes_de_noms(arxius_de(ruta))
    if not nous:
        return False
    vells = [destacat(t) for t in d.get('temes', [])]
    for t in nous:      # conserva el compositor i les marques de cada tema
        o = max(vells, key=lambda v: sim(v[1], t[1]), default=None)
        if o and sim(o[1], t[1]) <= 0.75:
            o = next((v for v in vells if v[0] and v[0] == t[0] and v[3] == t[3]), None)
        if o:
            t[2], t[4], t[5] = o[2], o[4], o[5]
            if o[6]:
                t.append(o[6])
    canvia = firma_temes(nous) != firma_temes(vells)
    d['temes'] = nous
    d['nas_t'] = firma_temes(nous)
    return canvia


def nums(t):
    return re.findall(r'\d+', NT(t))


def mateix_disc(a1, t1, a2, t2):
    """El mateix disc escrit diferent («Doyle Bramhall ll» / «Doyle Bramhall II»), però no «Use Your Illusion I» i «II»."""
    if nums(t1) != nums(t2):
        return False
    ta, tb = net_titol(t1), net_titol(t2)
    if not ta or not tb:
        # títols fets només de signes («****» dels Greenhornes): han de ser idèntics i del mateix artista
        return not ta and not tb and N(a1) == N(a2) and str(t1 or '').strip() == str(t2 or '').strip() != ''

    if N(a1) == N(a2):
        return ta == tb or (len(ta) > 6 and SequenceMatcher(None, ta, tb).ratio() > 0.92)
    return sim(a1, a2) > 0.85 and (ta == tb or SequenceMatcher(None, ta, tb).ratio() > 0.9)


def mateix_contingut(a1, d1, a2, d2):
    """El mateix disc amb un títol del tot diferent: a l'Access hi havia «Better Than Ezra» (el nom del grup) i la
    carpeta del NAS diu «Before The Robots». Mateix artista (o un nom que comença amb l'altre), mateix any, exactament els mateixos temes (5 o més)
    i només una de les dues entrades té carpeta al NAS: si totes dues en tenen, són dos discos diferents
    (encara que un tingui els temes mal copiats) i no es toquen."""
    n1, n2 = N(a1), N(a2)
    # el mateix artista, o un nom que comença amb l'altre: «Astroqueen» / «Astroqueen Vs Buffalo» (un disc compartit)
    if not n1 or not n2 or not (n1 == n2 or (min(len(n1), len(n2)) >= 4 and (n1.startswith(n2) or n2.startswith(n1)))):
        return False
    if not str(d1.get('any') or '').strip() or str(d1.get('any')).strip() != str(d2.get('any') or '').strip():
        return False
    if d1.get('carpeta') and d2.get('carpeta'):
        return False
    t1, t2 = d1.get('temes') or [], d2.get('temes') or []
    if len(t1) < 5 or len(t1) != len(t2):
        return False
    return all(len(x) > 1 and len(y) > 1 and N(x[1]) and (N(x[1]) == N(y[1]) or sim(x[1], y[1]) > 0.85)
               for x, y in zip(t1, t2))


CAMPS_MEUS = ('classificacio', 'notes', 'barcode', 'catno', 'segell', 'edicio', 'any', 'genere', 'estil', 'clasamg',
              'bitrate', 'qualitat', 'usuari', 'discogs_release', 'discogs_master', 'temes', 'interprets')


def elimina_duplicats():
    """Deixa una sola entrada per disc: la que ha trobat més fonts d'internet i té més dades.
    Res del que has escrit tu es perd: passa a l'entrada que es queda."""
    import shutil
    arrel = CFG.get('carpeta_musica', r'C:\SynologyMusic\Mi Musica')
    try:
        al_nas = {e.name for e in os.scandir(arrel) if e.is_dir()}
    except OSError:
        al_nas = set()
    with comu.BLOC:
        artistes = llegeix('artistes.json', {})
        discs = llegeix('discs.json', [])
        nom = lambda d: artistes.get(str(d.get('artista')), '')
        pare = list(range(len(discs)))
        def arrel_de(x):
            while pare[x] != x:
                pare[x] = pare[pare[x]]
                x = pare[x]
            return x
        # per anar ràpid només es comparen discos que comencen igual (títol o artista)
        blocs = {}
        for i, d in enumerate(discs):
            blocs.setdefault('t' + net_titol(d.get('titol'))[:4], []).append(i)
            blocs.setdefault('a' + N(nom(d))[:4], []).append(i)
        for L in blocs.values():
            for x in range(len(L)):
                for y in range(x + 1, len(L)):
                    a, b = discs[L[x]], discs[L[y]]
                    if arrel_de(L[x]) != arrel_de(L[y]) and (mateix_disc(nom(a), a.get('titol'), nom(b), b.get('titol'))
                                                           or mateix_contingut(nom(a), a, nom(b), b)):
                        pare[arrel_de(L[x])] = arrel_de(L[y])
        grups = {}
        for i, d in enumerate(discs):
            grups.setdefault(arrel_de(i), []).append(d)
        grups = [g for g in grups.values() if len(g) > 1]
        if not grups:
            return 0

        def punts(d):
            return (len(d.get('fonts') or {}) * 10 + sum(1 for c in CLAUS if d.get(c))
                    + (5 if d.get('carpeta') in al_nas else 0) + (3 if d.get('classificacio') else 0)
                    - (8 if d.get('no_trobat') else 0))
        fora, informe, repetides = set(), [], []
        for g in grups:
            g.sort(key=punts, reverse=True)
            w = g[0]
            noms_abans = [f"«{nom(x)} - {x.get('titol', '')}»" for x in g]
            for x in g[1:]:
                auto_w, auto_x = set(w.get('auto') or []), set(x.get('auto') or [])
                for c in CAMPS_MEUS:
                    if not x.get(c):
                        continue
                    # el que has escrit tu guanya al que s'ha omplert automàticament
                    if not w.get(c) or (c in auto_w and c not in auto_x):
                        w[c] = x[c]
                        if c in auto_x:
                            auto_w.add(c)
                        else:
                            auto_w.discard(c)
                if auto_w or 'auto' in w:
                    w['auto'] = sorted(auto_w)
                for s in suports(x):
                    afegeix_suport(w, s)
                if x.get('data') and (not w.get('data') or x['data'] < w['data']):
                    w['data'] = x['data']
                # els noms bons són els de la carpeta que existeix al NAS (la que has corregit)
                corregit = (x.get('carpeta') in al_nas and w.get('carpeta') not in al_nas) or \
                    (not al_nas and str(x.get('id', '')).startswith('nas') and x.get('carpeta') and x.get('carpeta') != w.get('carpeta')
                     and not str(w.get('id', '')).startswith('nas'))
                if corregit:
                    w['carpeta'], w['artista'], w['titol'] = x['carpeta'], x['artista'], x['titol']
                    if not w.get('fonts'):
                        w['reintenta'] = True
                if not w.get('caratula') and x.get('caratula'):
                    src = os.path.join(comu.CARATULES, f"{x['id']}.jpg")
                    if os.path.exists(src):
                        shutil.copy2(src, os.path.join(comu.CARATULES, f"{w['id']}.jpg"))
                        w['caratula'] = True
                        w['cv'] = int(time.time())
                if w.get('estat') == 'pendent' and x.get('estat') != 'pendent' and x.get('fonts'):
                    w.pop('estat', None)
                # dues carpetes al NAS per al mateix disc: la que no es queda no s'ha de tornar a afegir cada dia
                if x.get('carpeta') in al_nas and x['carpeta'] != w.get('carpeta'):
                    repetides.append(x['carpeta'])
                fora.add(id(x))
            informe.append(f"{' + '.join(noms_abans)}  →  queda «{nom(w)} - {w.get('titol', '')}»")
        discs = [d for d in discs if id(d) not in fora]
        # artistes que s'han quedat sense cap disc (noms mal escrits)
        usats = {str(d.get('artista')) for d in discs}
        for k in [k for k in artistes if k not in usats]:
            artistes.pop(k)
        desa('artistes.json', artistes)
        desa('discs.json', discs)
        if repetides:
            ig = llegeix('ignorats.json', {'artistes': [], 'discos': []})
            L = ig.setdefault('carpetes', [])
            L += [c for c in repetides if c not in L]
            desa('ignorats.json', ig)
            informe.append('Carpetes repetides al NAS que ja no s\'afegiran: ' + '; '.join(repetides))
    with open(os.path.join(comu.DADES, 'duplicats_informe.txt'), 'a', encoding='utf-8') as fh:
        fh.write(f"\n{datetime.datetime.now():%Y-%m-%d %H:%M}\n" + '\n'.join(informe) + '\n')
    log(f'Duplicats: {len(fora)} entrades ajuntades (detall a dades\\duplicats_informe.txt)')
    return len(fora)


def mateixos_temes(vells, nous):
    """Carpeta esborrada i creada de nou amb un altre nom («Hookah Brown» -> «Hookah Brown - 2013 - ...»):
    és el mateix disc si gairebé tots els temes de la fitxa antiga hi són."""
    v = {N(t[1]) for t in vells or [] if len(t) > 1 and N(t[1])}
    n = {N(t[1]) for t in nous or [] if len(t) > 1 and N(t[1])}
    return len(v) >= 3 and len(v & n) >= 0.8 * len(v)


MARCA_TITOL = re.compile(r'[\s\-–—(\[]*\b(?:CD|Disc|Disco|Disk)\s*(\d{1,2})\s*[)\]]?\s*$', re.I)


def disc_del_titol(t):
    """«Mellon Collie and the Infinite Sadness - CD2» -> («Mellon Collie and the Infinite Sadness», 2); sense marca, (t, 0)."""
    m = MARCA_TITOL.search(str(t or ''))
    return (str(t)[:m.start()].strip(), int(m.group(1))) if m else (str(t or '').strip(), 0)


def ajunta_discs_partits(discs, orfes, artistes, arrel):
    """Disc doble que tenia una fitxa per CD («... - CD1» i «... - CD2»): si has ajuntat els arxius en una sola
    carpeta, la fitxa del CD que s'ha quedat sense carpeta s'ajunta amb la que l'ha adoptat. Els temes de cada CD
    queden marcats amb el seu disc i res del que has escrit es perd (omple només els camps buits).
    Torna les fitxes que s'han ajuntat (per treure-les de la llista)."""
    fora = []
    for x in list(orfes):
        base, k = disc_del_titol(x.get('titol'))
        if not k:
            continue
        art = N(artistes.get(str(x.get('artista')), ''))
        temes_x = [destacat(t) for t in x.get('temes') or []]
        for w in discs:
            if w is x or id(w) in map(id, fora) or not w.get('carpeta') or w in orfes \
                    or N(artistes.get(str(w.get('artista')), '')) != art:
                continue
            base_w, k_w = disc_del_titol(w.get('titol'))
            if net_titol(base_w) != net_titol(base) or k_w:
                continue
            ruta = os.path.join(arrel, w['carpeta'])
            if not os.path.isdir(ruta) or not mateixos_temes(temes_x, temes_de_noms(arxius_de(ruta))):
                continue
            # la fitxa que es queda: els seus temes són d'un altre CD (el que tenia abans, o l'1)
            temes_w = [destacat(t) for t in w.get('temes') or []]
            # la columna del disc pot portar una marca antiga de l'Access («*», una cara): si no diu cap CD, mana el títol
            es_cd = lambda L: any(re.match(r'^CD\s*\d+$', str(t[3]).strip(), re.I) for t in L)
            if temes_x and not es_cd(temes_x):
                for t in temes_x:
                    t[3] = f'CD{k}'
            if temes_w and not es_cd(temes_w):
                kw = 1 if k != 1 else 2
                for t in temes_w:
                    t[3] = f'CD{kw}'
            vistos = {(str(t[3]), str(t[0]).strip(), N(t[1])) for t in temes_w}
            temes_w += [t for t in temes_x if (str(t[3]), str(t[0]).strip(), N(t[1])) not in vistos]
            num = lambda t: int(re.sub(r'\D', '', str(t[0])) or 10 ** 4)
            temes_w.sort(key=lambda t: (int(re.sub(r'\D', '', str(t[3])) or 0), num(t)))
            firma_abans = firma_temes(w.get('temes') or [])
            w['temes'] = temes_w
            if w.get('nas_t') == firma_abans:
                w['nas_t'] = firma_temes(temes_w)
            for c in CAMPS_MEUS:
                if c != 'temes' and x.get(c) and not w.get(c):
                    w[c] = x[c]
            for i in x.get('interprets') or []:
                if i not in (w.get('interprets') or []):
                    w.setdefault('interprets', []).append(i)
            for sp in suports(x):
                afegeix_suport(w, sp)
            w.pop('fmt_m', None)        # els arxius es tornaran a anomenar amb «Disc 1» / «Disc 2»
            fora.append(x)
            orfes.remove(x)
            nom = artistes.get(str(x.get('artista')), '')
            log(f"NAS: «{nom} - {x.get('titol', '')}» s'ajunta amb «{nom} - {w.get('titol', '')}» (els CD són a la mateixa carpeta)")
            try:
                with open(os.path.join(comu.DADES, 'duplicats_informe.txt'), 'a', encoding='utf-8') as fh:
                    fh.write(f"\n{datetime.datetime.now():%Y-%m-%d %H:%M}\n«{nom} - {x.get('titol', '')}» + «{nom} - {w.get('titol', '')}»"
                             f"  →  queda «{nom} - {w.get('titol', '')}» (disc doble en una sola carpeta)\n")
            except OSError:
                pass
            break
    return fora


def llegeix_nas():
    arrel = CFG.get('carpeta_musica', r'C:\SynologyMusic\Mi Musica')
    if not os.path.isdir(arrel):
        log(f'No trobo la carpeta de música: {arrel}')
        return
    estat('Llegint la carpeta de música…')
    artistes = llegeix('artistes.json', {})
    discs = llegeix('discs.json', [])
    per_carpeta = {d.get('carpeta'): d for d in discs if d.get('carpeta')}
    descartades = set(llegeix('ignorats.json', {}).get('carpetes', []))
    carpetes = {e.name for e in os.scandir(arrel) if e.is_dir()}
    # discos que apunten a una carpeta que ja no existeix (perquè l'has reanomenada)
    fiable = len(carpetes) >= 0.5 * len(per_carpeta)
    orfes = [d for d in discs if d.get('carpeta') and d['carpeta'] not in carpetes] if fiable else []
    per_art = {}
    for d in discs:
        per_art.setdefault(N(artistes.get(str(d['artista']), '')), []).append(d)
    nous = 0
    for e in os.scandir(arrel):
        if not e.is_dir() or e.name in per_carpeta or e.name.startswith('.') or e.name in descartades:
            continue
        arxius = arxius_de(e.path)          # només llista noms
        if not arxius:
            continue
        m = re.match(r'^(.+?)\s*[-–—]\s*(\d{4})\s*[-–—]\s*(.+)$', e.name) or re.match(r'^(.+?)\s*[-–—]\s*()(.+)$', e.name)
        art, any_, tit = (m.group(1).strip(), m.group(2), m.group(3).strip()) if m else (e.name, '', e.name)
        # «Dag Nasty - Dag With Shawn (2010)»: l'any va a la fitxa i el títol queda net
        net, any_p = comu.titol_net(tit)
        if net and m:
            tit, any_ = net, any_ or any_p
        sup = sorted({EXT[os.path.splitext(f)[1].lower()] for _, f in arxius})
        # carpeta reanomenada? el disc antic passa a apuntar a la nova i agafa els noms corregits
        vell = next((x for x in orfes if mateix_disc(artistes.get(str(x['artista']), ''), x.get('titol'), art, tit)), None) \
            or next((x for x in orfes if N(artistes.get(str(x['artista']), '')) == N(art)
                     and mateixos_temes(x.get('temes'), temes_de_noms(arxius))), None)
        if vell:
            orfes.remove(vell)
            antic = f"{artistes.get(str(vell['artista']), '')} - {vell.get('titol', '')}"
            vell['carpeta'] = e.name
            vell['artista'] = id_artista(art, artistes)
            vell['titol'] = tit
            if any_ and not vell.get('any'):
                vell['any'] = any_
            if not vell.get('fonts'):
                vell['reintenta'] = True
            log(f'NAS: carpeta reanomenada, «{antic}» ara és «{art} - {tit}»')
            continue
        cands = per_art.get(N(art), [])
        d = next((x for x in cands if N(x.get('titol')) == N(tit)), None) or \
            next((x for x in cands if sim(x.get('titol'), tit) > 0.85 and not x.get('carpeta')), None)
        if d:
            d['carpeta'] = e.name
            for s in sup:
                if afegeix_suport(d, s):
                    d['auto'] = sorted(set(d.get('auto', [])) | {'suport'})
            if not d.get('temes'):
                d['temes'] = temes_de_noms(arxius)
                d['auto'] = sorted(set(d.get('auto', [])) | {'temes'})
                d['nas_t'], d['nas_m'] = firma_temes(d['temes']), e.stat().st_mtime
            continue
        dates = [datetime.date.fromtimestamp(e.stat().st_mtime).isoformat()]
        d = {'id': 'nas' + str(int(time.time() * 1000)) + str(nous), 'artista': id_artista(art, artistes), 'titol': tit,
             'suport': ', '.join(sup), 'data': dates[0], 'estat': 'pendent', 'carpeta': e.name,
             'temes': temes_de_noms(arxius), 'interprets': [], 'auto': ['titol', 'suport', 'temes', 'data'] + (['any'] if any_ else [])}
        d['nas_t'], d['nas_m'] = firma_temes(d['temes']), e.stat().st_mtime
        if any_:
            d['any'] = any_
        discs.append(d)
        per_art.setdefault(N(art), []).append(d)
        nous += 1
    # disc doble amb una fitxa per CD i els arxius ajuntats en una sola carpeta: una sola fitxa
    if orfes:
        try:
            fora = {id(x) for x in ajunta_discs_partits(discs, orfes, artistes, arrel)}
            if fora:
                discs[:] = [x for x in discs if id(x) not in fora]
        except Exception as e:
            log(f'NAS: error ajuntant discos dobles {e!r}')
    # discos amb els temes trets dels noms dels arxius: si has canviat els arxius, es tornen a llegir
    mtimes = {e.name: e.stat().st_mtime for e in os.scandir(arrel) if e.is_dir()}
    relleguts = []
    for d in discs:
        c = d.get('carpeta')
        if c in mtimes and 'temes' in d.get('auto', []) and d.get('nas_t') == firma_temes(d.get('temes', [])) \
                and d.get('nas_m') != mtimes[c]:
            try:
                if relleeix_temes(d, os.path.join(arrel, c), mtimes[c]):
                    relleguts.append(f"{artistes.get(str(d['artista']), '')} - {d.get('titol', '')}")
            except OSError as e:
                log(f'NAS: no puc llegir {c} ({e})')
    desa('discs.json', discs)
    log(f'NAS: {nous} discos nous')
    if relleguts:
        log(f"NAS: temes tornats a llegir dels arxius: {'; '.join(relleguts)}")


def _temes_antics(arxius):
    """Com llegia els temes la versió anterior (per reconèixer els que encara són els noms dels arxius)."""
    out = []
    for sub, a in sorted(arxius):
        m = re.search(r'(?:^|- )(\d{1,3})\s*[-.]\s*(.+)$', os.path.splitext(a)[0])
        out.append(m.group(2).strip() if m else os.path.splitext(a)[0])
    return out


def arregla_noms_nas():
    """Un sol cop: (1) artistes creats amb l'any enganxat perquè la carpeta duia un guió llarg
    («Jan Stenfors – 1996 - Vinegar Blood»); (2) temes llegits dels noms dels arxius que van quedar sense número
    o desordenats; (3) les recomanacions dels discos nous es tornen a buscar (ara també amb els discos de Last.fm)."""
    fetes = llegeix('migracions.json', {})
    if fetes.get('noms_nas'):
        return
    arrel = CFG.get('carpeta_musica', r'C:\SynologyMusic\Mi Musica')
    if not os.path.isdir(arrel):
        return          # sense la carpeta de música, ja es farà un altre dia
    with comu.BLOC:
        artistes = llegeix('artistes.json', {})
        discs = llegeix('discs.json', [])
        log_ = []
        for k, nom in list(artistes.items()):
            m = re.match(r'^(.+?)\s*[–—]\s*(\d{4})$', nom)
            if not m:
                continue
            bo = m.group(1).strip()
            dest = next((k2 for k2, v in artistes.items() if k2 != k and N(v) == N(bo)), None)
            for d in discs:
                if str(d.get('artista')) == k:
                    if dest:
                        d['artista'] = dest
                    if not d.get('any'):
                        d['any'] = m.group(2)
                    d['reintenta'] = True
            if dest:
                del artistes[k]
            else:
                artistes[k] = bo
            log_.append(f'«{nom}» → «{bo}»')
        relleguts = 0
        for d in discs:
            c = d.get('carpeta')
            if not c or 'temes' not in d.get('auto', []) or d.get('nas_t'):
                continue
            ruta = os.path.join(arrel, c)
            if not os.path.isdir(ruta):
                continue
            try:
                arxius = arxius_de(ruta)
                temes = d.get('temes', [])
                de_noms = [t[1] for t in temes] == _temes_antics(arxius) or any(not str(t[0]).strip() for t in temes)
                if arxius and de_noms:
                    relleeix_temes(d, ruta, os.stat(ruta).st_mtime)
                    relleguts += 1
            except OSError:
                pass
        for d in discs:
            if d.get('data', '') >= '2026-10-20':
                d['reintenta'] = True
        desa('artistes.json', artistes)
        desa('discs.json', discs)
    if log_:
        log(f"NAS: artistes corregits: {'; '.join(log_)}")
    log(f'NAS: {relleguts} discos amb els temes tornats a llegir dels noms dels arxius')
    fetes['noms_nas'] = AVUI
    desa('migracions.json', fetes)


def temes_carpeta(d):
    """Els títols dels temes de la carpeta del NAS (dels noms dels arxius, sense obrir-los), per comparar amb
    Discogs quan la fitxa no en té."""
    c = d.get('carpeta')
    ruta = os.path.join(CFG.get('carpeta_musica', r'C:\SynologyMusic\Mi Musica'), c or '')
    if not c or not os.path.isdir(ruta):
        return []
    try:
        return [t[1] for t in temes_de_noms(arxius_de(ruta)) if t[1]]
    except OSError:
        return []


def destacat(t):
    """Els temes destacats (l'estrella «*» de l'Access, com els «picks» d'AllMusic) van a t[6] = 1, perquè t[3] és
    la cara o el CD del tema. Torna el tema allargat a 7 columnes."""
    t = list(t) + [''] * (6 - len(t)) + [0] * (7 - max(len(t), 6))
    if str(t[3]).strip() == '*':
        t[3], t[6] = '', 1
    return t


def migra_destacats():
    """Un sol cop: l'estrella dels temes destacats passa de la columna de la cara/CD (t[3]) a la seva (t[6])."""
    fetes = llegeix('migracions.json', {})
    if fetes.get('destacats'):
        return
    with comu.BLOC:
        discs = llegeix('discs.json', [])
        n = 0
        for d in discs:
            if any(len(t) > 3 and str(t[3]).strip() == '*' for t in d.get('temes') or []):
                d['temes'] = [destacat(t) if len(t) > 3 and str(t[3]).strip() == '*' else t for t in d['temes']]
                n += 1
        if n:
            desa('discs.json', discs)
    fetes['destacats'] = AVUI
    desa('migracions.json', fetes)
    log(f'Temes destacats: {n} discos amb l\'estrella a la seva columna')


MAX_DESTACATS = 3          # com els «picks» d'AllMusic: dos o tres temes per disc
PROP_DESTACAT = 0.4        # un tema és destacat si té com a mínim el 40 % de les escoltes del tema més escoltat del disc


def clau_tema(t):
    """«Tonight, Tonight (Remastered 2012)» -> «tonighttonight»: per comparar títols de temes."""
    return N(re.sub(r'\s*[\(\[][^\)\]]*[\)\]]|\s+-\s+.*(remaster|version|mix|live|edit).*$', '', str(t or ''), flags=re.I))


def destaca_temes(maxim=300, id_=None):
    """Els discos que no tenen cap tema destacat (★) en reben, com feia AllMusic: els temes del disc que més
    s'escolten a Last.fm (com a molt 3). Mai es toquen els discos on ja n'hi ha (les teves estrelles de l'Access o
    les que hagis posat tu). Cada disc es prova un cop (camp «dst»); es torna a provar al cap de 180 dies si no
    se n'ha trobat cap."""
    if not LFM:
        return 0
    fa180 = (datetime.date.today() - datetime.timedelta(days=180)).isoformat()
    artistes = llegeix('artistes.json', {})
    discs = llegeix('discs.json', [])
    cua = [d for d in discs if (str(d.get('id')) == str(id_) if id_ else True)
           and len(d.get('temes') or []) >= 2 and artistes.get(str(d.get('artista')))
           and not any(len(t) > 6 and t[6] for t in d['temes']) and not any(len(t) > 3 and str(t[3]).strip() == '*' for t in d['temes'])
           and (id_ or not d.get('dst') or (d.get('dst_n') == 0 and d['dst'] < fa180))]
    if not id_:
        cua = cua[:maxim]
    if not cua:
        return 0
    estat('Buscant els temes destacats a Last.fm…')
    top, marcats, desador = {}, 0, Desador()
    try:
        for d in cua:
            nom = nom_cerca(artistes.get(str(d['artista']), ''))
            if nom not in top:
                try:
                    top[nom] = {}
                    for tit, n in fonts.lastfm_top_temes(nom, LFM):
                        k = clau_tema(tit)
                        if k and n > top[nom].get(k, 0):
                            top[nom][k] = n
                except Exception as e:
                    log(f'  Last.fm: error buscant els temes de {nom} ({e!r})')
                    break
            abans = json.loads(json.dumps(d))
            temes = [destacat(t) for t in d['temes']]
            esc = [(top[nom].get(clau_tema(t[1]), 0), i) for i, t in enumerate(temes)]
            esc = sorted((x for x in esc if x[0]), reverse=True)
            tria = [i for n, i in esc[:MAX_DESTACATS] if n >= PROP_DESTACAT * esc[0][0]] if esc else []
            for i in tria:
                temes[i][6] = 1
            if tria:
                d['temes'] = temes
                d['auto'] = sorted(set(d.get('auto', [])) | {'destacats'})
                marcats += 1
            d['dst'], d['dst_n'] = AVUI, len(tria)
            desador.afegeix(abans, d)
    finally:
        desador.desa()
    log(f'Temes destacats: {len(cua)} discos mirats a Last.fm, {marcats} amb temes destacats nous')
    return marcats


def unifica_variables():
    """«sin» i «sin bitrate» (bitrate variable) passen a «VBR»; després s'hi afegeix la mitjana: «VBR ~208»."""
    with comu.BLOC:
        discs = llegeix('discs.json', [])
        n = 0
        for d in discs:
            if str(d.get('bitrate') or '').strip().lower() in ('sin', 'sin bitrate', 'variable', 'vbr'):
                if d['bitrate'] != 'VBR':
                    d['bitrate'] = 'VBR'
                    d.pop('br', None)
                    n += 1
        if n:
            desa('discs.json', discs)
            log(f'Bitrate: {n} discos «sin» passen a «VBR» (la mitjana s\'hi afegirà a poc a poc)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mode', default='nit')
    # mínim 300 discos per tanda fins que s'hagi repassat tota la col·lecció (es pot pujar a config.ini)
    ap.add_argument('--n', type=int, default=max(300, int(CFG.get('discos_per_tanda', 100) or 100)))
    ap.add_argument('--id')
    a = ap.parse_args()
    t0 = time.time()
    try:
        comu.aplica_canvis_mobil()
    except Exception as e:
        log(f'Error incorporant canvis del mòbil: {e!r}')
    if a.mode == 'reanomena':
        # l'Ignasi acaba de canviar un títol a mà: només es reanomenen la carpeta i els arxius
        try:
            reanomena_pendents()
            formata_tots()
        except Exception as e:
            log(f'NAS: error reanomenant carpetes {e!r}')
        return
    try:
        migra_destacats()
    except Exception as e:
        log(f'Temes destacats: error {e!r}')
    try:
        tradueix_catala()
    except Exception as e:
        log(f'Català: error {e!r}')
    try:
        normalitza_notes()
    except Exception as e:
        log(f'Notes: error {e!r}')
    try:
        unifica_variables()
    except Exception as e:
        log(f'Bitrate: error {e!r}')
    try:
        # cada pas va per separat: si un falla (per exemple, sense internet), els altres es fan igualment
        for modes, pas, nom in ((('nit', 'nas'), llegeix_nas, 'NAS'), (('nit', 'discogs'), sincronitza_discogs, 'Discogs'),
                                (('nit', 'nas', 'duplicats'), elimina_duplicats, 'Duplicats')):
            if a.mode in modes:
                try:
                    pas()
                except Exception as e:
                    log(f'{nom}: error {e!r}')
        try:
            reanomena_pendents()
        except Exception as e:
            log(f'NAS: error reanomenant carpetes {e!r}')
        try:
            formata_tots()
        except Exception as e:
            log(f'NAS: error posant el format als arxius {e!r}')
        if a.mode == 'nit':
            try:
                revisa_titols(int(CFG.get('titols_per_nit', 100) or 100))
            except Exception as e:
                log(f'Títols: error {e!r}')
        try:
            arregla_noms_nas()
        except Exception as e:
            log(f'NAS: error arreglant noms {e!r}')
        try:
            marca_dobles()
        except Exception as e:
            log(f'Discos dobles: error {e!r}')
        try:
            deixa_allmusic()
        except Exception as e:
            log(f'AllMusic: error {e!r}')
        fets = 0
        if a.mode in ('nit', 'tot', 'pendents', 'disc'):
            fets = tanda('tot' if a.mode == 'nit' else a.mode, a.n, a.id)
            # els discos nous ja tenen l'any: la carpeta passa a «Artista - Any - Títol» i els arxius, al format
            try:
                formata_tots()
            except Exception as e:
                log(f'NAS: error posant el format als arxius {e!r}')
        if a.mode in ('nit', 'tot', 'perfil'):
            try:
                fets += perfil_lastfm(6000 if a.mode == 'perfil' else 600)
            except Exception as e:
                log(f'Perfil musical: error {e!r}')
        if a.mode in ('nit', 'tot', 'disc', 'destacats'):
            try:
                destaca_temes(a.n, a.id if a.mode == 'disc' else None)
            except Exception as e:
                log(f'Temes destacats: error {e!r}')
        # el so dels discos (mostres de 30 s d'Apple Music): 300 discos per tanda, com a màxim 90 minuts
        if a.mode in ('nit', 'tot', 'so', 'disc'):
            try:
                import so
                if a.mode == 'disc':
                    so.analitza(id_=a.id, estat=estat)
                else:
                    so.analitza(a.n, estat=estat)
            except Exception as e:
                log(f'So: error {e!r}')
        # relació de cada disc amb el seu àlbum del Plex (per a l'enllaç «Obre al Plex» del mòbil)
        if a.mode in ('nit', 'tot', 'plex'):
            try:
                import plex
                plex.mapeja_tots()
            except Exception as e:
                log(f'Plex: error {e!r}')
        estat(f'Fet ({a.mode}): {fets} discos amb dades noves en {int((time.time() - t0) / 60)} min · {resum()} · {datetime.datetime.now():%d/%m %H:%M}')
    except Exception as e:
        log(f'ERROR general: {e!r}')
        estat(f'Error: {e}')
    finally:
        fonts._am_nav.tanca()


if __name__ == '__main__':
    main()
