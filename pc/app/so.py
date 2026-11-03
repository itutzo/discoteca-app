# -*- coding: utf-8 -*-
"""El so dels discos, per recomanar discos que sonen semblant.

Dels MP3 del NAS no se n'obre ni se'n descarrega cap. Es fan servir les mostres oficials de 30 segons
que Apple Music publica a la seva API de cerca (iTunes Search API): de cada disc se n'escolten 3 temes
(uns 500 kB cadascun), se'n treuen unes quantes mesures del so i les mostres s'esborren de seguida.

Mesures (de cada tema, i després la mitjana del disc):
  - el «color» del so: 12 coeficients MFCC (mitjana i variació), que distingeixen guitarra distorsionada,
    acústica, piano, veu, electrònica...
  - la brillantor (centroide i caiguda espectral), el soroll (planor espectral i pas per zero),
    el repartiment entre greus, mitjos i aguts,
  - la dinàmica (com varia el volum i el factor de cresta), els atacs (flux espectral),
  - el tempo i com de marcat és el ritme.

Es desa a dades/so.json: {id del disc: {"v": [mesures], "n": temes, "d": data, "u": enllaç d'Apple Music}}.
Si Apple Music no té el disc: {"no": data}; s'hi torna a provar al cap de 120 dies.

Necessita numpy i av (PyAV, que porta el descodificador d'àudio): s'instal·len sols el primer cop.
"""
import datetime, importlib, io, os, site, subprocess, sys, time, urllib.parse, re
from difflib import SequenceMatcher

import comu
from comu import N, NT, log, llegeix, desa
import fonts

IT = 'https://itunes.apple.com/'
fonts.PAUSA.setdefault('itunes.apple.com', 3.1)          # Apple demana unes 20 consultes per minut com a màxim
fonts.PAUSA.setdefault('audio-ssl.itunes.apple.com', 0.3)
SR, NFFT, HOP = 22050, 2048, 512
TEMES_PER_DISC = 3
REPROVA_DIES = 120
VERSIO = 1

_np = _av = None


def _instal(paquet, modul):
    try:
        return importlib.import_module(modul)
    except ImportError:
        pass
    log(f'So: instal·lant {paquet} (només el primer cop)…')
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--user', '--quiet', paquet])
    p = site.getusersitepackages()
    if p not in sys.path:
        sys.path.append(p)
    importlib.invalidate_caches()
    return importlib.import_module(modul)


def llibreries():
    global _np, _av
    if _np is None:
        _np = _instal('numpy', 'numpy')
        _av = _instal('av', 'av')
    return _np, _av


# ------------------------------------------------------------------ trobar el disc a Apple Music
def _net(t):
    t = re.sub(r'\s*[\(\[][^\)\]]*(remaster\w*|deluxe|edition|expanded|anniversary|bonus|reissue|version)[^\)\]]*[\)\]]',
               '', str(t or ''), flags=re.I)
    t = re.sub(r'\s+-\s+(EP|Single)$', '', t.strip(), flags=re.I)
    return NT(t)


def _semblanca(a, b):
    a, b = _net(a), _net(b)
    if not a or not b:
        return 0
    return 1.0 if a == b else SequenceMatcher(None, a, b).ratio()


def _mateix_artista(a, b):
    a, b = N(a), N(b)
    return bool(a) and bool(b) and (a == b or SequenceMatcher(None, a, b).ratio() >= 0.9)


def busca_album(artista, titol):
    """El disc a Apple Music (mateix artista i un títol molt semblant), o None."""
    for pais in ('es', 'us'):
        q = urllib.parse.urlencode({'term': f'{artista} {titol}', 'entity': 'album', 'limit': 15, 'country': pais})
        j = fonts.get(IT + 'search?' + q, json_=True) or {}
        millor, s = None, 0
        for r in j.get('results', []):
            if not _mateix_artista(r.get('artistName'), artista):
                continue
            q2 = _semblanca(r.get('collectionName'), titol)
            if q2 > s:
                millor, s = r, q2
        if millor and s >= 0.85:
            return millor, pais
    return None, None


def mostres_album(id_album, pais):
    """Els enllaços de les mostres de 30 s de 3 temes repartits pel disc (el primer, un del mig i un del final)."""
    q = urllib.parse.urlencode({'id': id_album, 'entity': 'song', 'country': pais})
    j = fonts.get(IT + 'lookup?' + q, json_=True) or {}
    temes = [r for r in j.get('results', []) if r.get('wrapperType') == 'track' and r.get('previewUrl')]
    temes.sort(key=lambda r: (r.get('discNumber') or 1, r.get('trackNumber') or 0))
    if len(temes) > TEMES_PER_DISC:
        n = len(temes)
        temes = [temes[i] for i in sorted({0, n // 3, (2 * n) // 3})]
    return [r['previewUrl'] for r in temes]


# ------------------------------------------------------------------ escoltar
def _mel(np):
    """Banc de 40 filtres en escala mel (com l'oïda: més detall als greus)."""
    def hz2mel(f):
        return 2595 * np.log10(1 + f / 700)

    def mel2hz(m):
        return 700 * (10 ** (m / 2595) - 1)
    punts = mel2hz(np.linspace(hz2mel(30), hz2mel(SR / 2), 42))
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    M = np.zeros((40, len(f)))
    for i in range(40):
        a, b, c = punts[i], punts[i + 1], punts[i + 2]
        M[i] = np.clip(np.minimum((f - a) / (b - a), (c - f) / (c - b)), 0, None)
    return M


def _dct(np, n=40, k=13):
    i = np.arange(n)
    D = np.cos(np.pi / n * (i + 0.5)[None, :] * np.arange(k)[:, None]) * np.sqrt(2 / n)
    D[0] /= np.sqrt(2)
    return D


def descodifica(b):
    """MP3/AAC/M4A en memòria -> senyal mono a 22.050 Hz."""
    np, av = llibreries()
    parts = []
    with av.open(io.BytesIO(b)) as c:
        rs = av.AudioResampler(format='flt', layout='mono', rate=SR)
        for fr in c.decode(audio=0):
            for f2 in rs.resample(fr):
                parts.append(f2.to_ndarray().reshape(-1))
        for f2 in rs.resample(None):
            parts.append(f2.to_ndarray().reshape(-1))
    return np.concatenate(parts).astype('float64') if parts else None


def descriptors(x):
    """37 mesures del so d'un fragment (o None si és massa curt o silenci)."""
    np, _ = llibreries()
    if x is None or len(x) < SR * 5:
        return None
    x = x - x.mean()
    pic = float(np.abs(x).max())
    if pic < 1e-4:
        return None
    n = 1 + (len(x) - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    crus = x[idx]
    S = np.abs(np.fft.rfft(crus * np.hanning(NFFT), axis=1)) ** 2
    rms = np.sqrt((crus ** 2).mean(1))
    db = 20 * np.log10(rms + 1e-6)
    act = db > db.max() - 40                     # sense els silencis
    if act.sum() < 20:
        return None
    S, crus, rms, db = S[act], crus[act], rms[act], db[act]
    f = np.fft.rfftfreq(NFFT, 1 / SR)
    tot = S.sum(1) + 1e-12
    centroide = (S * f).sum(1) / tot
    cum = np.cumsum(S, 1)
    caiguda = f[np.argmax(cum >= 0.85 * cum[:, -1:], axis=1)]
    planor = np.exp(np.log(S + 1e-12).mean(1)) / (S.mean(1) + 1e-12)
    zcr = (np.abs(np.diff(np.sign(crus), axis=1)) > 0).mean(1)
    greus = S[:, f < 250].sum(1) / tot
    aguts = S[:, f >= 4000].sum(1) / tot
    lm = np.log(_mel(np) @ S.T + 1e-10)          # (40, trames)
    mfcc = _dct(np) @ lm                          # (13, trames)
    flux = np.maximum(0, np.diff(lm, axis=1)).sum(0)
    # tempo: autocorrelació dels atacs, entre 60 i 200 pulsacions per minut
    env = flux - np.convolve(flux, np.ones(16) / 16, mode='same')
    env = np.maximum(env, 0)
    ac = np.correlate(env, env, mode='full')[len(env) - 1:]
    fps = SR / HOP
    l0, l1 = int(60 * fps / 200), int(60 * fps / 60)
    tempo, claredat = 0.0, 0.0
    if ac[0] > 0 and len(ac) > l1:
        lags = np.arange(l0, l1 + 1)
        pes = np.exp(-0.5 * np.log2(60 * fps / lags / 120) ** 2)      # preferència per tempos al voltant de 120
        lag = int(lags[np.argmax(ac[l0:l1 + 1] * pes)])
        tempo, claredat = 60 * fps / lag, float(ac[lag] / ac[0])
    v = list(mfcc[1:].mean(1) / 10) + list(mfcc[1:].std(1) / 10) + [
        centroide.mean() / (SR / 2), centroide.std() / (SR / 2), caiguda.mean() / (SR / 2),
        planor.mean(), zcr.mean(), greus.mean(), 1 - greus.mean() - aguts.mean(), aguts.mean(),
        flux.mean() / 40, db.std() / 20, np.log10(pic / (rms.mean() + 1e-9)),
        tempo / 200, claredat]
    return [float(z) for z in v]


def escolta_disc(artista, titol):
    """(mesures mitjanes del disc, nombre de temes, enllaç d'Apple Music) o (None, 0, None) si no hi és."""
    np, _ = llibreries()
    album, pais = busca_album(artista, titol)
    if not album:
        return None, 0, None
    V = []
    for url in mostres_album(album['collectionId'], pais):
        try:
            b = fonts.get(url, binari=True)
            v = descriptors(descodifica(b)) if b else None
        except Exception as e:
            log(f'  So: no he pogut escoltar una mostra ({e!r})')
            v = None
        if v:
            V.append(v)
    if not V:
        return None, 0, album.get('collectionViewUrl')
    return [round(float(z), 4) for z in np.mean(np.array(V), axis=0)], len(V), album.get('collectionViewUrl')


# ------------------------------------------------------------------ una tanda
def _nota(v):
    try:
        return float(str(v).replace(',', '.'))
    except (TypeError, ValueError):
        return 0.0


def analitza(n=300, id_=None, minuts=90, estat=None):
    """Escolta els discos que encara no tenen el so analitzat (o un de sol). Torna quants n'ha fet."""
    try:
        llibreries()
    except Exception as e:
        log(f'So: no s\'han pogut instal·lar numpy i av ({e!r}); ho tornaré a provar un altre dia')
        return 0
    AVUI = datetime.date.today().isoformat()
    fa = (datetime.date.today() - datetime.timedelta(days=REPROVA_DIES)).isoformat()
    discs = llegeix('discs.json', [])
    artistes = llegeix('artistes.json', {})
    so = llegeix('so.json', {})
    if id_ is not None:
        cua = [d for d in discs if str(d.get('id')) == str(id_)]
    else:
        cua = [d for d in discs if str(d.get('id')) not in so or
               (so[str(d.get('id'))].get('no') and so[str(d.get('id'))]['no'] < fa)
               or so[str(d.get('id'))].get('ver', 1) < VERSIO]
        cua.sort(key=lambda d: -_nota(d.get('classificacio')))     # primer els que t'agraden més
    cua = [d for d in cua if artistes.get(str(d.get('artista'))) and d.get('titol')][:n]
    if not cua:
        return 0
    log(f'So: escoltant {len(cua)} discos a Apple Music (mostres de 30 s)')
    t0, fets, no, errors = time.time(), 0, 0, 0
    for i, d in enumerate(cua, 1):
        if time.time() - t0 > minuts * 60:
            log(f'So: aturat al cap de {minuts} minuts; la resta, a la propera tanda')
            break
        nom_art = artistes.get(str(d['artista']), '')
        if estat:
            estat(f'So {i}/{len(cua)} · {nom_art} - {d.get("titol", "")}')
        try:
            v, k, url = escolta_disc(nom_art, d['titol'])
            errors = 0
        except fonts.ErrorHTTP as e:
            errors += 1
            log(f'  So: Apple Music ha respost {e.code}')
            if errors >= 3:
                log('So: Apple Music no deixa consultar ara; ho deixo per a un altre dia')
                break
            time.sleep(60)
            continue
        except Exception as e:
            log(f'  So: error amb «{nom_art} - {d.get("titol", "")}» {e!r}')
            continue
        if v:
            so[str(d['id'])] = {'v': v, 'n': k, 'd': AVUI, 'u': url, 'ver': VERSIO}
            fets += 1
        else:
            so[str(d['id'])] = {'no': AVUI}
            no += 1
        if (fets + no) % 20 == 0:
            desa('so.json', so)
    desa('so.json', so)
    log(f'So: {fets} discos escoltats, {no} no són a Apple Music · {sum(1 for x in so.values() if x.get("v"))} en total')
    return fets
