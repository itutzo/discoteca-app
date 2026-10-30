# -*- coding: utf-8 -*-
"""Completador de la Discoteca. Funciona sol, sense Claude.

  python completar.py --mode nit         NAS + Discogs + una tanda de discos (el que fa la tasca nocturna)
  python completar.py --mode pendents    només els discos marcats com a pendents
  python completar.py --mode tot         pendents i després la resta de la col·lecció (una tanda)
  python completar.py --mode disc --id X un disc concret
  python completar.py --mode discogs     sincronitza CD i vinils amb la teva col·lecció de Discogs
  python completar.py --mode nas         busca discos nous a la carpeta de música

Regles: només omple camps buits, mai no toca la classificació personal ni les notes,
i marca tot el que afegeix com a «automàtic» perquè ho puguis revisar.
"""
import argparse, datetime, json, os, re, sys, time
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
    k = 'a' + str(int(time.time() * 1000))
    artistes[k] = nom
    desa('artistes.json', artistes)
    return k


def sim(a, b):
    return SequenceMatcher(None, N(a), N(b)).ratio()


# ------------------------------------------------------------------ completar un disc
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
    try:
        if d.get('barcode') or d.get('catno'):
            dg = DG.per_codi(d.get('barcode'), None if d.get('barcode') else d.get('catno'))
        if not dg and nom_art and titol:
            dg = DG.cerca(nom_art, titol)
    except Exception as e:
        log(f'  Discogs: error {e!r}')
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

    # 2. AllMusic
    am = None
    if nom_art and titol:
        try:
            am = fonts.allmusic(nom_art, titol)
            d.pop('am_error', None)
        except fonts.AMBloquejat:
            d['am_error'] = AVUI         # es tornarà a provar quan AllMusic torni a respondre
        except Exception as e:
            d['am_error'] = AVUI
            log(f'  AllMusic: error {e!r}')
    if am:
        fonts_d['AllMusic'] = am['url']
        omple('any', am.get('any') or str(((dg or {}).get('master') or {}).get('year') or ''))
        omple('genere', GEN.get(N(am.get('genere', '').split(',')[0]), am.get('genere', '').split(',')[0]))
        est = next((estils_meus[N(x)] for x in am.get('estils', []) if N(x) in estils_meus), (am.get('estils') or [None])[0])
        omple('estil', est)
        omple('clasamg', am.get('amg'))
    elif dg:
        omple('any', str((dg.get('master') or {}).get('year') or dg.get('any') or ''))
        omple('genere', GEN.get(N((dg.get('generes') or [''])[0]), (dg.get('generes') or [None])[0]))
        est = next((estils_meus[N(x)] for x in dg.get('estils', []) if N(x) in estils_meus), (dg.get('estils') or [None])[0])
        omple('estil', est)

    # 3. Temes: conservem els teus noms i hi afegim el compositor
    ref = (am or {}).get('temes') or (dg or {}).get('temes') or []
    ref_dg = (dg or {}).get('temes') or []
    temes = [list(x) + [''] * (6 - len(x)) for x in d.get('temes', [])]
    if not temes and ref:
        temes = [[t['n'], t['titol'], '', '', 0, 0] for t in ref]
        auto.add('temes'); canvis.append('temes')
    posat = False
    for t in temes:
        if t[2]:
            continue
        for llista in (ref, ref_dg):
            m = max(llista, key=lambda r: sim(r['titol'], t[1]), default=None)
            if m and sim(m['titol'], t[1]) > 0.75 and m['compositors']:
                t[2] = ' / '.join(m['compositors'])
                posat = True
                break
    if posat:
        auto.add('compositors'); canvis.append('compositors')
    d['temes'] = temes

    # 4. Intèrprets
    if not d.get('interprets'):
        P, vist = [], {}
        credits = list((am or {}).get('credits', [])) + list((dg or {}).get('credits', []))
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

    # 4b. Bitrate estimat: mida dels MP3 del NAS (sense descarregar-los) / durada dels temes
    variable = d.get('bitrate') == 'VBR'        # sabem que és variable però encara no en tenim la mitjana
    if (not d.get('bitrate') or variable) and d.get('carpeta'):
        d['br'] = 2          # ja s'ha provat amb el mètode nou
        try:
            br = bitrate_estimat(d, (am or {}).get('temes') or [], (dg or {}).get('temes') or [], variable)
            if br:
                d['bitrate'] = br
                auto.add('bitrate'); canvis.append('bitrate')
        except Exception as e:
            log(f'  Bitrate: error {e!r}')

    # 5. Caràtula
    if not d.get('caratula'):
        for url in [(am or {}).get('caratula'), (dg or {}).get('caratula')]:
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
    if d.get('estat') == 'pendent' and (am or dg):
        d.pop('estat')
    return canvis, bool(am), bool(dg)


def segons(t):
    p = [int(x) for x in re.findall(r'\d+', str(t or ''))]
    if len(p) == 2:
        return p[0] * 60 + p[1]
    if len(p) == 3:
        return p[0] * 3600 + p[1] * 60 + p[2]
    return 0


ESTANDARD = [96, 112, 128, 160, 192, 224, 256, 320]


def bitrate_estimat(d, temes_am, temes_dg, variable=False):
    """Bitrate dels MP3 del NAS sense obrir-los: mida de l'arxiu (només es llegeix la mida) / durada del tema.
    Cada arxiu s'aparella amb el seu tema pel número o pel nom, així funciona encara que hi hagi
    temes extra o en faltin."""
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
                mp3.append((f, os.stat(os.path.join(root, f)).st_size))
    if flac and not mp3:
        return 'Flac'
    if not mp3:
        return None
    for ref in (temes_am, temes_dg):
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


def recomana(d, nom_art, am, dg):
    recs = llegeix('recs.json', {})
    k = str(d['artista'])
    vell = recs.get(k)
    if vell and vell.get('updatedAt', '') > (datetime.date.today() - datetime.timedelta(days=180)).isoformat() \
            and len(vell.get('fonts', [])) >= 3 and (not am or 'AllMusic' in vell.get('fonts', [])):
        return
    me = N(nom_art)
    A, D = {}, {}

    def addA(nom, font, pos):
        n = N(nom)
        if not n or n == me:
            return
        e = A.setdefault(n, {'nom': re.sub(r'\s*\(\d+\)$', '', nom), 'fonts': [], 'pos': 0})
        if font not in e['fonts']:
            e['fonts'].append(font); e['pos'] += pos

    def addD(titol, artista, font, pos, any_=''):
        # sense artista = un altre disc del mateix artista (Apple Music no repeteix el nom): no és una descoberta
        if not titol or not str(artista or '').strip() or N(artista) == me:
            return
        t = re.sub(r'\s*[\(\[](deluxe|remaster|expanded|\d+th anniversary|anniversary)[^\)\]]*[\)\]]', '', titol, flags=re.I).replace(' - EP', '').strip()
        key = N(artista) + '|' + N(t)
        e = D.setdefault(key, {'artista': re.sub(r'\s*\(\d+\)$', '', artista), 'titol': t, 'any': any_, 'fonts': [], 'pos': 0})
        if font not in e['fonts']:
            e['fonts'].append(font); e['pos'] += pos
        if any_ and not e['any']:
            e['any'] = any_

    usades = []
    if am:
        usades.append('AllMusic')
        for p, x in enumerate(am.get('artistes_similars', [])): addA(x, 'AllMusic', p)
        for p, x in enumerate(am.get('similars', [])): addD(x['titol'], x['artista'], 'AllMusic', p, x.get('any', ''))
    if LFM:
        try:
            L = fonts.lastfm_similars(nom_art, LFM)
            if L:
                usades.append('Last.fm')
            for p, x in enumerate(L): addA(x, 'Last.fm', p)
        except Exception as e:
            log(f'  Last.fm: error {e!r}')
    try:
        ap = fonts.apple(nom_art, d.get('titol', ''))
        if ap['artistes'] or ap['discos']:
            usades.append('Apple Music')
        for p, x in enumerate(ap['artistes']): addA(x, 'Apple Music', p)
        for p, x in enumerate(ap['discos']): addD(x['titol'], x['artista'], 'Apple Music', p)
    except Exception as e:
        log(f'  Apple Music: error {e!r}')
    if dg:
        rr = DG.recomanacions(dg['id'])
        if rr:
            usades.append('Discogs')
        for p, x in enumerate(rr):
            addD(x['titol'], x['artista'], 'Discogs', p)
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
    recs[k] = {'artista': nom_art, 'fonts': usades, 'updatedAt': AVUI,
               'artistes': [{x: e[x] for x in ('nom', 'fonts', 'score')} for e in srt(A.values())][:40],
               'discos': [{x: e[x] for x in ('artista', 'titol', 'any', 'fonts', 'score')} for e in srt(D.values())][:40]}
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


def marca_reintents_allmusic():
    """Un sol cop: els discos repassats des del 25/10/2026 sense dades d'AllMusic (AllMusic responia 403)
    queden marcats perquè s'hi torni a provar."""
    fetes = llegeix('migracions.json', {})
    if fetes.get('allmusic_403'):
        return
    with comu.BLOC:
        discs = llegeix('discs.json', [])
        n = 0
        for d in discs:
            if d.get('proc', '') >= '2026-10-25' and 'AllMusic' not in (d.get('fonts') or {}) and not d.get('am_error'):
                d['am_error'] = d['proc']
                n += 1
        if n:
            desa('discs.json', discs)
    fetes['allmusic_403'] = AVUI
    desa('migracions.json', fetes)
    log(f'AllMusic: {n} discos marcats per tornar-hi a provar')


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
                        and d.get('br') != 2 and d.get('estat') != 'pendent']
            # discos que AllMusic no va deixar consultar (403): un altre intent, com a molt un cop al dia
            am_err = [d for d in discs if d.get('am_error') and d.get('estat') != 'pendent' and d.get('proc', '') < AVUI]
            ja = {id(x) for x in pend + sense_br}
            cua = pend + sense_br + [d for d in am_err if id(d) not in ja] + mai + \
                [d for d in falten if id(d) not in ja and not d.get('am_error')]
    cua = cua[:n]
    log(f'Tanda «{mode}»: {len(cua)} discos')
    fets, saltats, compte = 0, 0, {'sí': 0, 'no': 0, 'error': 0}
    desador = Desador()
    try:
        for i, d in enumerate(cua, 1):
            # si AllMusic ens ha tancat la porta, no cal repassar ara els discos que només esperaven AllMusic
            if fonts._am_nav.bloquejat and d.get('am_error') and mode != 'disc' and d.get('estat') != 'pendent':
                saltats += 1
                continue
            nom = f"{artistes.get(str(d['artista']), '?')} - {d.get('titol', '')}"
            estat(f'{i}/{len(cua)} · {nom}')
            abans = json.loads(json.dumps(d))
            try:
                d.pop('reintenta', None)
                canvis, am, dg = completa(d, artistes, estils_meus)
                log(f"  {nom}: {', '.join(canvis) or 'res de nou'} (AllMusic {'sí' if am else 'no'}, Discogs {'sí' if dg else 'no'})")
                compte['error' if d.get('am_error') else 'sí' if am else 'no'] += 1
                if not am and not dg and not d.get('am_error'):
                    d['no_trobat'] = AVUI
                elif am or dg:
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
        log(f"AllMusic en aquesta tanda: {compte['sí']} trobats, {compte['no']} no hi són, {compte['error']} no ha deixat consultar"
            + (f" · {saltats} discos ajornats fins que AllMusic torni a respondre" if saltats else ''))
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


def temes_de_noms(arxius):
    out = []
    multi = len({s for s, _ in arxius}) > 1 or any(re.search(r'- CD\d+ -', a) for _, a in arxius)
    for sub, a in sorted(arxius):
        nom = os.path.splitext(a)[0]
        cd = re.search(r'(?:CD|Disc)\s*(\d+)', sub + ' ' + nom, re.I)
        m = re.search(r'(?:^|- )(\d{1,3})\s*[-.]\s*(.+)$', nom)
        num, tit = ((m.group(1).lstrip('0') or '0'), m.group(2).strip()) if m else ('', nom)
        out.append([num, tit, '', ('CD' + cd.group(1)) if (multi and cd) else '', 0, 0])
    return out


def nums(t):
    return re.findall(r'\d+', NT(t))


def mateix_disc(a1, t1, a2, t2):
    """El mateix disc escrit diferent («Doyle Bramhall ll» / «Doyle Bramhall II»), però no «Use Your Illusion I» i «II»."""
    if nums(t1) != nums(t2):
        return False
    ta, tb = net_titol(t1), net_titol(t2)
    if not ta or not tb:
        return False
    if N(a1) == N(a2):
        return ta == tb or (len(ta) > 6 and SequenceMatcher(None, ta, tb).ratio() > 0.92)
    return sim(a1, a2) > 0.85 and (ta == tb or SequenceMatcher(None, ta, tb).ratio() > 0.9)


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
                    if arrel_de(L[x]) != arrel_de(L[y]) and mateix_disc(nom(a), a.get('titol'), nom(b), b.get('titol')):
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
        fora, informe = set(), []
        for g in grups:
            g.sort(key=punts, reverse=True)
            w = g[0]
            noms_abans = [f"«{nom(x)} - {x.get('titol', '')}»" for x in g]
            for x in g[1:]:
                for c in CAMPS_MEUS:
                    if not w.get(c) and x.get(c):
                        w[c] = x[c]
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
                fora.add(id(x))
            informe.append(f"{' + '.join(noms_abans)}  →  queda «{nom(w)} - {w.get('titol', '')}»")
        discs = [d for d in discs if id(d) not in fora]
        # artistes que s'han quedat sense cap disc (noms mal escrits)
        usats = {str(d.get('artista')) for d in discs}
        for k in [k for k in artistes if k not in usats]:
            artistes.pop(k)
        desa('artistes.json', artistes)
        desa('discs.json', discs)
    with open(os.path.join(comu.DADES, 'duplicats_informe.txt'), 'a', encoding='utf-8') as fh:
        fh.write(f"\n{datetime.datetime.now():%Y-%m-%d %H:%M}\n" + '\n'.join(informe) + '\n')
    log(f'Duplicats: {len(fora)} entrades ajuntades (detall a dades\\duplicats_informe.txt)')
    return len(fora)


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
        arxius = []
        for root, _, files in os.walk(e.path):          # només llista noms
            sub = os.path.relpath(root, e.path)
            arxius += [('' if sub == '.' else sub, f) for f in files if os.path.splitext(f)[1].lower() in EXT]
        if not arxius:
            continue
        m = re.match(r'^(.+?)\s*-\s*(\d{4})\s*-\s*(.+)$', e.name) or re.match(r'^(.+?)\s*-\s*()(.+)$', e.name)
        art, any_, tit = (m.group(1).strip(), m.group(2), m.group(3).strip()) if m else (e.name, '', e.name)
        sup = sorted({EXT[os.path.splitext(f)[1].lower()] for _, f in arxius})
        # carpeta reanomenada? el disc antic passa a apuntar a la nova i agafa els noms corregits
        vell = next((x for x in orfes if mateix_disc(artistes.get(str(x['artista']), ''), x.get('titol'), art, tit)), None)
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
            continue
        dates = [datetime.date.fromtimestamp(e.stat().st_mtime).isoformat()]
        d = {'id': 'nas' + str(int(time.time() * 1000)) + str(nous), 'artista': id_artista(art, artistes), 'titol': tit,
             'suport': ', '.join(sup), 'data': dates[0], 'estat': 'pendent', 'carpeta': e.name,
             'temes': temes_de_noms(arxius), 'interprets': [], 'auto': ['titol', 'suport', 'temes', 'data'] + (['any'] if any_ else [])}
        if any_:
            d['any'] = any_
        discs.append(d)
        per_art.setdefault(N(art), []).append(d)
        nous += 1
    desa('discs.json', discs)
    log(f'NAS: {nous} discos nous')


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
            marca_reintents_allmusic()
        except Exception as e:
            log(f'AllMusic: error marcant reintents {e!r}')
        fets = 0
        if a.mode in ('nit', 'tot', 'pendents', 'disc'):
            fets = tanda('tot' if a.mode == 'nit' else a.mode, a.n, a.id)
        if a.mode in ('nit', 'tot', 'perfil'):
            try:
                fets += perfil_lastfm(6000 if a.mode == 'perfil' else 600)
            except Exception as e:
                log(f'Perfil musical: error {e!r}')
        estat(f'Fet ({a.mode}): {fets} discos amb dades noves en {int((time.time() - t0) / 60)} min · {resum()} · {datetime.datetime.now():%d/%m %H:%M}')
    except Exception as e:
        log(f'ERROR general: {e!r}')
        estat(f'Error: {e}')
    finally:
        fonts._am_nav.tanca()


if __name__ == '__main__':
    main()
