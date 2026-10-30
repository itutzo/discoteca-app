# -*- coding: utf-8 -*-
"""Consultes a AllMusic, Discogs, MusicBrainz, Last.fm i Apple Music."""
import json, re, time, random, urllib.request, urllib.parse, urllib.error, gzip, subprocess, sys

try:
    from bs4 import BeautifulSoup
except ImportError:   # primer cop: s'instal·la sol
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--user', '--quiet', 'beautifulsoup4'])
    from bs4 import BeautifulSoup

from comu import N, NT, log

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
      'Chrome/130.0 Safari/537.36')
_ultim = {}
PAUSA = {'www.allmusic.com': 2.0, 'api.discogs.com': 1.2, 'www.discogs.com': 3.0,
         'ws.audioscrobbler.com': 0.25, 'music.apple.com': 2.0,
         'musicbrainz.org': 1.1, 'coverartarchive.org': 0.5}


try:
    from curl_cffi import requests as creq      # es connecta com un Chrome de veritat
except ImportError:
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--user', '--quiet', 'curl_cffi'])
        from curl_cffi import requests as creq
    except Exception:
        creq = None
_sessio = creq.Session(impersonate='chrome') if creq else None


class ErrorHTTP(Exception):
    def __init__(self, code):
        super().__init__(f'HTTP {code}')
        self.code = code


def get(url, headers=None, json_=False, binari=False, intents=3):
    host = urllib.parse.urlparse(url).netloc
    espera = PAUSA.get(host, 1.0) - (time.time() - _ultim.get(host, 0))
    if espera > 0:
        time.sleep(espera + random.random() * 0.5)
    h = {'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'}
    h.update(headers or {})
    for i in range(intents):
        try:
            _ultim[host] = time.time()
            if _sessio:
                r = _sessio.get(url, headers=h, timeout=30)
                code, b = r.status_code, r.content
            else:
                h2 = dict(h, **{'User-Agent': UA, 'Accept-Encoding': 'gzip'})
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=h2), timeout=30) as rr:
                        b = rr.read()
                        if rr.headers.get('Content-Encoding') == 'gzip':
                            b = gzip.decompress(b)
                        code = rr.status
                except urllib.error.HTTPError as e:
                    code, b = e.code, b''
            if code == 404:
                return None
            if code in (429, 503) and i < intents - 1:
                time.sleep(30 * (i + 1))
                continue
            if code >= 400:
                raise ErrorHTTP(code)
            if binari:
                return b
            t = b.decode('utf-8', 'replace')
            return json.loads(t) if json_ else t
        except ErrorHTTP:
            raise
        except Exception:
            if i < intents - 1:
                time.sleep(5 * (i + 1))
                continue
            raise


class AMBloquejat(ErrorHTTP):
    """AllMusic ha refusat diverses peticions seguides: no s'hi insisteix durant aquesta tanda."""
    def __init__(self):
        super().__init__(403)


class NavegadorAM:
    """AllMusic només deixa entrar navegadors reals: fem servir el Chrome del PC, amb un perfil a part i fora de la pantalla."""
    MAX_REFUSOS = 3

    def __init__(self):
        self.pw = self.br = self.pg = None
        self.refusos = 0
        self.bloquejat = False

    def obre(self):
        if self.pg:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '--user', '--quiet', 'playwright'])
            from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        for headless in (False,):
            try:
                args = [] if headless else ['--window-position=-32000,-32000', '--window-size=800,600']
                self.br = self.pw.chromium.launch(channel='chrome', headless=headless, args=args)
                self.pg = self.br.new_page(locale='es-ES')
                self.pg.goto(AM + '/', wait_until='domcontentloaded', timeout=60000)
                if 'allmusic' in (self.pg.title() or '').lower():
                    log(f"  AllMusic: s'utilitza Chrome ({'invisible' if headless else 'fora de pantalla'})")
                    return
            except Exception as e:
                log(f'  AllMusic amb Chrome: {e!r}')
            try:
                self.br.close()
            except Exception:
                pass
            self.pg = None

    def text(self, url):
        if self.bloquejat:
            raise AMBloquejat()
        for intent in range(2):
            self.obre()
            if not self.pg:
                raise ErrorHTTP(403)
            host = 'www.allmusic.com'
            espera = PAUSA[host] - (time.time() - _ultim.get(host, 0))
            if espera > 0:
                time.sleep(espera + random.random() * 0.5)
            _ultim[host] = time.time()
            try:
                r = self.pg.evaluate('async u => { const r = await fetch(u); return [r.status, await r.text()]; }', url)
            except Exception as e:
                # la finestra de Chrome s'ha tancat o penjat: s'obre de nou un sol cop
                if intent == 0 and re.search(r'closed|crash', repr(e), re.I):
                    self.tanca_finestra()
                    continue
                raise
            if r[0] == 404:
                return None
            if r[0] in (403, 429):
                # AllMusic no vol respostes automàtiques: després de uns quants refusos seguits ho deixem estar
                self.refusos += 1
                if self.refusos >= self.MAX_REFUSOS:
                    self.bloquejat = True
                    log(f'  AllMusic: {self.refusos} refusos seguits; no es torna a provar fins a la propera tanda')
                    raise AMBloquejat()
            if r[0] >= 400:
                raise ErrorHTTP(r[0])
            self.refusos = 0
            return r[1]

    def tanca_finestra(self):
        try:
            if self.br: self.br.close()
        except Exception:
            pass
        self.br = self.pg = None

    def tanca(self):
        try:
            if self.br: self.br.close()
            if self.pw: self.pw.stop()
        except Exception:
            pass


_am_nav = NavegadorAM()


def sopa(url):
    if url.startswith(AM):
        t = _am_nav.text(url)      # AllMusic sempre amb Chrome: sense navegador real retorna pàgines buides
    else:
        t = get(url)
    return BeautifulSoup(t, 'html.parser') if t else None


def txt(e):
    return re.sub(r'\s+', ' ', e.get_text(' ')).strip() if e else ''


# ---------------- AllMusic ----------------
AM = 'https://www.allmusic.com'


def allmusic(artista, titol):
    s = sopa(AM + '/search/albums/' + urllib.parse.quote(f'{artista} {titol}'))
    if not s:
        return None
    cands = []
    for e in s.select('.album'):
        a = e.select_one('.title a') or e.select_one('a[href*="/album/"]')
        if a:
            cands.append({'url': a['href'], 'titol': txt(e.select_one('.title')), 'artista': txt(e.select_one('.artist'))})
    best = next((c for c in cands if N(artista) in N(c['artista']) and NT(c['titol']) == NT(titol)), None) or \
        next((c for c in cands if N(artista) in N(c['artista']) and (NT(titol) in NT(c['titol']) or NT(c['titol']) in NT(titol))), None)
    if not best:
        return None
    url = re.sub(r'^https?://[^/]+', '', best['url'])
    mw = re.search(r'mw\d+', url)
    if not mw:
        return None
    mw = mw.group(0)
    d = sopa(AM + url)
    if not d:
        return None
    out = {'url': AM + url}
    dt = d.select_one('.release-date span') or d.select_one('.release-date')
    out['data'] = re.sub(r'^Release Date\s*', '', txt(dt))
    m = re.search(r'\d{4}', out['data'])
    out['any'] = m.group(0) if m else ''
    out['genere'] = ', '.join(txt(a) for a in d.select('.genre a'))
    out['estils'] = [txt(a) for a in d.select('.styles a')]
    rc = d.select_one('[class*="ratingAllmusic"]')
    m = re.search(r'ratingAllmusic(\d+)', ' '.join(rc.get('class', []))) if rc else None
    out['amg'] = (str(int(m.group(1)) / 2).replace('.0', '').replace('.', ',') if m and int(m.group(1)) else None)
    img = d.select_one('img[src*="/front/"]')
    out['caratula'] = img['src'] if img else None
    out['temes'] = [{'n': txt(t.select_one('.trackNum')), 'titol': txt(t.select_one('.title a') or t.select_one('.title')),
                     'compositors': [txt(a) for a in t.select('.composer a')], 'durada': txt(t.select_one('.duration'))} for t in d.select('.track')]
    c = sopa(AM + url + '/creditsAjax')
    out['credits'] = [(txt(r.select_one('.artist')), txt(r.select_one('.artistCredits'))) for r in (c.select('tbody tr') if c else [])]
    sm = sopa(AM + '/similar-listview/' + mw)
    out['similars'] = []
    for r in (sm.select('tbody tr') if sm else [])[:25]:
        a = r.select_one('.cover a')
        out['similars'].append({'any': txt(r.select_one('.year')), 'artista': txt(r.select_one('.similarArtist')), 'titol': a.get('title', '') if a else ''})
    out['artistes_similars'] = []
    au = d.select_one('#albumArtists a') or d.select_one('.artist a')
    if au:
        ad = sopa(re.sub(r'^https?://[^/]+', AM, au['href']) + '/related')
        box = ad.select_one('.tabContent.relatedArtists') if ad else None
        if box:
            for h in box.find_all(['h2', 'h3', 'h4']):
                if re.search('similar', h.get_text(), re.I):
                    for sib in h.find_next_siblings():
                        if sib.name in ('h2', 'h3', 'h4'):
                            break
                        out['artistes_similars'] += [txt(a) for a in sib.select('a')]
                    break
        out['artistes_similars'] = list(dict.fromkeys(x for x in out['artistes_similars'] if x))[:25]
    return out


# ---------------- Discogs ----------------
DAPI = 'https://api.discogs.com'


class Discogs:
    def __init__(self, token):
        self.h = {'Authorization': f'Discogs token={token}'} if token else {}

    def api(self, path, **q):
        url = DAPI + path + ('?' + urllib.parse.urlencode(q) if q else '')
        return get(url, headers=self.h, json_=True)

    def per_codi(self, barcode=None, catno=None):
        q = {'type': 'release'}
        if barcode:
            q['barcode'] = re.sub(r'\D', '', barcode)
        elif catno:
            q['catno'] = catno
        else:
            return None
        r = self.api('/database/search', **q) or {}
        res = r.get('results') or []
        return self.release(res[0]['id']) if res else None

    def cerca(self, artista, titol):
        art_ok = lambda nom: N(artista) in N(nom) or N(nom) in N(artista)
        # 1. versió principal (master) per artista i títol; 2. cerca lliure de masters; 3. qualsevol edició
        for q in ({'type': 'master', 'artist': artista, 'release_title': titol},
                  {'type': 'master', 'q': f'{artista} {titol}'},
                  {'type': 'release', 'q': f'{artista} {titol}'}):
            r = self.api('/database/search', **q) or {}
            for x in (r.get('results') or [])[:6]:
                # el títol de la cerca és «Artista - Títol»
                art_x, _, tit_x = (x.get('title') or '').partition(' - ')
                if not art_ok(art_x) or NT(tit_x) != NT(titol):
                    continue
                if q['type'] == 'master':
                    m = self.api(f"/masters/{x['id']}")
                    rel = self.release(m['main_release']) if m else None
                    if rel:
                        rel['master'] = m
                        return rel
                else:
                    rel = self.release(x['id'])
                    if rel:
                        return rel
        return None

    def release(self, rid):
        rel = self.api(f'/releases/{rid}')
        if not rel:
            return None
        out = {'id': rel['id'], 'url': rel.get('uri'), 'any': str(rel.get('year') or ''), 'generes': rel.get('genres', []),
               'estils': rel.get('styles', []), 'pais': rel.get('country', ''),
               'segell': ', '.join(dict.fromkeys(re.sub(r'\s*\(\d+\)$', '', l['name']) for l in rel.get('labels', []))),
               'catno': ', '.join(dict.fromkeys(l.get('catno', '') for l in rel.get('labels', []) if l.get('catno') and l.get('catno') != 'none')),
               'barcode': next((i['value'] for i in rel.get('identifiers', []) if i.get('type') == 'Barcode'), ''),
               'formats': [f.get('name') for f in rel.get('formats', [])],
               'artista': ', '.join(re.sub(r'\s*\(\d+\)$', '', a['name']) for a in rel.get('artists', [])),
               'artista_id': (rel.get('artists') or [{}])[0].get('id'),
               'titol': rel.get('title', ''),
               'caratula': next((i['uri'] for i in rel.get('images', []) if i.get('type') == 'primary'), (rel.get('images') or [{}])[0].get('uri')),
               'credits': [(re.sub(r'\s*\(\d+\)$', '', x['name']), x.get('role', '')) for x in rel.get('extraartists', [])],
               'temes': [{'n': t.get('position', ''), 'titol': t.get('title', ''), 'durada': t.get('duration', ''),
                          'compositors': [re.sub(r'\s*\(\d+\)$', '', e['name']) for e in t.get('extraartists', [])
                                          if re.search(r'Written|Composed|Songwriter|Music By|Lyrics', e.get('role', ''), re.I)]}
                         for t in rel.get('tracklist', []) if t.get('type_') == 'track']}
        return out

    def membres(self, artista_id):
        if not artista_id:
            return []
        a = self.api(f'/artists/{artista_id}') or {}
        return [re.sub(r'\s*\(\d+\)$', '', m['name']) for m in a.get('members', []) if m.get('active', True)]

    def recomanacions(self, release_id):
        """Llegeix l'apartat «Recommendations» de la pàgina web de l'edició."""
        try:
            s = sopa(f'https://www.discogs.com/release/{release_id}')
        except Exception as e:
            log(f'  Discogs no deixa llegir les recomanacions ({e})')
            return []
        out = []
        for li in (s.select('#release-recommendations li') if s else []):
            t = [txt(a) for a in li.select('a') if txt(a)]
            if t:
                out.append({'titol': t[0], 'artista': re.sub(r'\s*\(\d+\)$', '', t[1]) if len(t) > 1 else ''})
        return out

    def coleccio(self, usuari):
        pag, out = 1, []
        while True:
            r = self.api(f'/users/{usuari}/collection/folders/0/releases', per_page=100, page=pag)
            if not r:
                break
            out += r.get('releases', [])
            if pag >= r.get('pagination', {}).get('pages', 1):
                break
            pag += 1
        return out


# ---------------- MusicBrainz ----------------
# API oberta i gratuïta. Demana com a màxim una consulta per segon i un User-Agent que identifiqui l'aplicació.
MB = 'https://musicbrainz.org/ws/2'
MB_UA = {'User-Agent': 'Discoteca/1.0 ( https://github.com/itutzo/discoteca-app )', 'Accept': 'application/json'}
MB_COMPOSICIO = ('composer', 'writer', 'lyricist')
MB_MUSICS = ('instrument', 'vocal', 'performer', 'conductor')     # la resta (productor, enginyer...) no són intèrprets


def _mb(path, **q):
    q['fmt'] = 'json'
    return get(MB + path + '?' + urllib.parse.urlencode(q), headers=MB_UA, json_=True)


def _lucene(t):
    return '"' + re.sub(r'([\\"])', r'\\\1', str(t)) + '"'


def _mb_credit(rel):
    """Una relació d'artista de MusicBrainz com a crèdit (nom, rol), amb el mateix format que AllMusic i Discogs."""
    nom = (rel.get('artist') or {}).get('name') or ''
    attrs = [a.capitalize() for a in rel.get('attributes') or [] if a not in ('additional', 'guest', 'solo')]
    rol = {'vocal': 'Vocals', 'instrument': 'Instruments', 'performer': 'Performer'}.get(rel.get('type'), rel.get('type', '').title())
    rol = ', '.join(attrs) if attrs and rel.get('type') in ('instrument', 'vocal') else rol
    if 'guest' in (rel.get('attributes') or []):
        rol += ', Guest'
    return nom, rol


def musicbrainz(artista, titol):
    """Disc a MusicBrainz: any, gèneres, temes amb durada i compositors, intèrprets i caràtula (Cover Art Archive)."""
    m = re.match(r'^(.*),\s*(the|los|las|el|la|les)$', str(artista or '').strip(), re.I)
    art_cerca = f'{m.group(2)} {m.group(1)}' if m else artista             # «Cure, The» -> «The Cure»
    r = _mb('/release-group/', query=f'releasegroup:{_lucene(titol)} AND artist:{_lucene(art_cerca)}', limit=10) or {}
    art_ok = lambda rg: any(N(artista) in N(c.get('name') or (c.get('artist') or {}).get('name')) or
                            N(c.get('name') or '') in N(artista) for c in rg.get('artist-credit') or [] if c.get('name'))
    cands = [x for x in r.get('release-groups') or [] if art_ok(x)]
    cands.sort(key=lambda x: (x.get('primary-type') != 'Album', -int(x.get('score') or 0)))
    rg = next((x for x in cands if NT(x.get('title')) == NT(titol)), None) or \
        next((x for x in cands if NT(titol) in NT(x.get('title')) or NT(x.get('title')) in NT(titol)), None)
    if not rg:
        return None
    g = _mb(f"/release-group/{rg['id']}", inc='genres+releases') or {}
    out = {'url': f"https://musicbrainz.org/release-group/{rg['id']}",
           'any': (g.get('first-release-date') or rg.get('first-release-date') or '')[:4],
           'generes': [x['name'] for x in sorted(g.get('genres') or [], key=lambda x: -int(x.get('count') or 0))],
           'caratula': f"https://coverartarchive.org/release-group/{rg['id']}/front-500",
           'temes': [], 'credits': []}
    # l'edició oficial més antiga és la que té els crèdits de l'original
    rels = sorted(g.get('releases') or [], key=lambda x: (x.get('status') != 'Official', not x.get('date'), x.get('date') or ''))
    if rels:
        rel = _mb(f"/release/{rels[0]['id']}",
                  inc='recordings+artist-credits+artist-rels+recording-level-rels+work-rels+work-level-rels') or {}
        out['credits'] = [_mb_credit(x) for x in rel.get('relations') or [] if x.get('artist') and x.get('type') in MB_MUSICS]
        for med in rel.get('media') or []:
            for t in med.get('tracks') or []:
                rec = t.get('recording') or {}
                comp = []
                for x in rec.get('relations') or []:
                    if x.get('artist') and x.get('type') in MB_MUSICS:
                        out['credits'].append(_mb_credit(x))
                    for w in ((x.get('work') or {}).get('relations') or []) if x.get('type') == 'performance' else []:
                        if w.get('type') in MB_COMPOSICIO and (w.get('artist') or {}).get('name'):
                            comp.append(w['artist']['name'])
                ms = t.get('length') or rec.get('length') or 0
                out['temes'].append({'n': t.get('number') or t.get('position') or '', 'titol': t.get('title') or rec.get('title') or '',
                                     'compositors': list(dict.fromkeys(comp)),
                                     'durada': f'{ms // 60000}:{ms // 1000 % 60:02d}' if ms else ''})
    return out


# ---------------- Last.fm ----------------
def lastfm_similars(artista, key):
    if not key:
        return []
    r = get('https://ws.audioscrobbler.com/2.0/?' + urllib.parse.urlencode(
        {'method': 'artist.getsimilar', 'artist': artista, 'api_key': key, 'format': 'json', 'limit': 25, 'autocorrect': 1}), json_=True) or {}
    return [a['name'] for a in r.get('similarartists', {}).get('artist', [])]


def lastfm_info(artista, key):
    """Oients i etiquetes d'estil (amb el seu pes 0-100) d'un artista a Last.fm."""
    q = {'artist': artista, 'api_key': key, 'format': 'json', 'autocorrect': 1}
    r = get('https://ws.audioscrobbler.com/2.0/?' + urllib.parse.urlencode(dict(q, method='artist.getinfo')), json_=True) or {}
    a = r.get('artist') or {}
    try:
        oients = int(a['stats']['listeners'])
    except Exception:
        oients = None
    if oients is None:
        return None
    t = get('https://ws.audioscrobbler.com/2.0/?' + urllib.parse.urlencode(dict(q, method='artist.gettoptags')), json_=True) or {}
    tags = []
    for x in (t.get('toptags') or {}).get('tag', [])[:15]:
        try:
            n = int(x.get('count') or 0)
        except ValueError:
            n = 0
        if n >= 5:
            tags.append([x['name'].strip().lower(), n])
    return {'o': oients, 't': tags}



def lastfm_temes(artista, titol, key):
    """Temes d'un disc a Last.fm amb la durada (per calcular el bitrate quan cap altra font la dona)."""
    if not key:
        return []
    r = get('https://ws.audioscrobbler.com/2.0/?' + urllib.parse.urlencode(
        {'method': 'album.getinfo', 'artist': artista, 'album': titol, 'api_key': key, 'format': 'json',
         'autocorrect': 1}), json_=True) or {}
    t = ((r.get('album') or {}).get('tracks') or {}).get('track') or []
    if isinstance(t, dict):         # un disc d'un sol tema no ve en llista
        t = [t]
    out = []
    for x in t:
        try:
            s = int(x.get('duration') or 0)
        except (TypeError, ValueError):
            s = 0
        out.append({'n': str((x.get('@attr') or {}).get('rank') or ''), 'titol': x.get('name') or '',
                    'durada': f'{s // 60}:{s % 60:02d}' if s else ''})
    return out

# ---------------- Apple Music ----------------
AP = 'https://music.apple.com'


def _seccio(s, patro):
    h = next((x for x in s.find_all('h2') if re.search(patro, x.get_text(), re.I)), None)
    if not h:
        return None
    el = h
    for _ in range(6):
        el = el.parent
        if el is None:
            return None
        if len(el.select('a[href*="/album/"], a[href*="/artist/"]')) >= 2:
            return el
    return None


def apple(artista, titol):
    out = {'artistes': [], 'discos': []}
    s = sopa(AP + '/es/search?term=' + urllib.parse.quote(artista))
    a = next((x['href'] for x in (s.select('a[href*="/artist/"]') if s else []) if N(x.get_text()) == N(artista)), None)
    if a:
        d = sopa(urllib.parse.urljoin(AP, a))
        box = _seccio(d, 'Artistas similares|Similar Artists') if d else None
        if box:
            out['artistes'] = list(dict.fromkeys(txt(x) for x in box.select('a[href*="/artist/"]') if txt(x)))[:25]
    s = sopa(AP + '/es/search?term=' + urllib.parse.quote(f'{artista} {titol}'))
    b = next((x['href'] for x in (s.select('a[href*="/album/"]') if s else []) if N(titol) in N(x.get_text())), None)
    if b:
        d = sopa(urllib.parse.urljoin(AP, b.split('?')[0]))
        box = _seccio(d, 'También te puede gustar|You Might Also Like') if d else None
        if box:
            for li in box.select('li'):
                al = li.select_one('a[href*="/album/"]')
                if not al:
                    continue
                t = txt(al)
                ar = li.select_one('a[href*="/artist/"]')
                nom = txt(ar) if ar else txt(li).replace(t, '').strip()
                out['discos'].append({'titol': t, 'artista': nom})
    return out


def descarrega(url):
    try:
        return get(url, binari=True)
    except Exception:
        return None
