# -*- coding: utf-8 -*-
"""Servidor local de la Discoteca: http://localhost:8800
Només escolta el mateix PC (127.0.0.1): cap altre aparell de la xarxa ni d'internet hi pot entrar.
El mòbil i la tauleta fan servir la versió web (itutzo.github.io/discoteca), que llegeix del Dropbox.
A més, només accepta peticions fetes des de la mateixa Discoteca: una altra pàgina web oberta
al navegador no pot esborrar ni canviar res."""
import json, os, sys, shutil, subprocess, threading, time, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comu
from comu import llegeix, desa, BLOC, log

PORT = 8800
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
ESTAT = os.path.join(comu.DADES, 'estat.json')
proces = {'p': None}
SERVIDOR = {'srv': None}
TIPUS = {'.png': 'image/png', '.json': 'application/manifest+json', '.ico': 'image/x-icon'}
NO_AUTORITZAT = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Discoteca</title><body style="font:16px system-ui;padding:32px;max-width:520px;margin:auto;color:#1d1a19;background:#f3f1ef">
<h1 style="color:#8a1c1c">Discoteca</h1><p>Des del mòbil o la tauleta, fes servir <b>itutzo.github.io/discoteca</b>.</p></body>"""


def importar_caratules_inicials():
    """El primer cop copia les caràtules convertides des d'Access (Documents\\Discos_export\\jpg)."""
    origen = os.path.join(os.path.expanduser('~'), 'Documents', 'Discos_export', 'jpg')
    if not os.path.isdir(origen):
        return
    ja = set(os.listdir(comu.CARATULES))
    nous = [f for f in os.listdir(origen) if f.lower().endswith('.jpg') and f not in ja]
    if not nous:
        return
    log(f'Copiant {len(nous)} caràtules inicials des de {origen}')
    for f in nous:
        shutil.copy2(os.path.join(origen, f), os.path.join(comu.CARATULES, f))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(b)

    def _file(self, path, ctype):
        if not os.path.isfile(path):
            self.send_error(404)
            return
        with open(path, 'rb') as f:
            b = f.read()
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(b)

    def _local(self):
        return self.client_address[0] in ('127.0.0.1', '::1', '::ffff:127.0.0.1')

    def _permes(self, q):
        if not self._local():
            return False
        # contra «DNS rebinding»: el navegador ha de dir que parla amb localhost
        host = (self.headers.get('Host') or '').lower()
        if host not in (f'localhost:{PORT}', f'127.0.0.1:{PORT}', 'localhost', '127.0.0.1'):
            return False
        # contra pàgines web estranyes que intentin fer canvis: l'origen ha de ser la mateixa Discoteca
        origen = self.headers.get('Origin')
        if origen and origen.lower() not in (f'http://localhost:{PORT}', f'http://127.0.0.1:{PORT}'):
            return False
        if self.command == 'POST' and (self.headers.get('Sec-Fetch-Site') or 'same-origin') not in ('same-origin', 'none'):
            return False
        return True

    def _denega(self):
        b = NO_AUTORITZAT.encode('utf-8')
        self.send_response(403)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get('Content-Length') or 0)
        return self.rfile.read(n) if n else b''

    # ---------- GET ----------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p = urllib.parse.unquote(u.path)
        q = urllib.parse.parse_qs(u.query)
        if p in ('/favicon.png', '/icona-180.png', '/icona-512.png', '/manifest.json', '/favicon.ico'):
            nom = 'favicon.png' if p == '/favicon.ico' else p[1:]
            return self._file(os.path.join(WEB, nom), TIPUS[os.path.splitext(nom)[1]])
        if not self._permes(q):
            return self._denega()
        if p in ('/', '/index.html'):
            return self._file(os.path.join(WEB, 'index.html'), 'text/html; charset=utf-8')
        if p == '/api/dades':
            try:
                comu.aplica_canvis_mobil()
            except Exception as e:
                log(f'Error incorporant canvis del mòbil: {e!r}')
            with BLOC:
                return self._json({'artistes': llegeix('artistes.json', {}), 'discs': llegeix('discs.json', [])})
        if p == '/api/lastfm':
            return self._json(llegeix('lastfm.json', {}))
        if p == '/api/recs-tots':
            return self._json(llegeix('recs.json', {}))
        if p.startswith('/api/recs/'):
            recs = llegeix('recs.json', {})
            return self._json(recs.get(p.rsplit('/', 1)[1]) or {})
        if p == '/api/ignorats':
            return self._json(llegeix('ignorats.json', {'artistes': [], 'discos': []}))
        if p == '/api/estat':
            st = llegeix('estat.json', {})
            st['en_marxa'] = bool(proces['p'] and proces['p'].poll() is None)
            return self._json(st)
        if p.startswith('/caratules/'):
            nom = os.path.basename(p)
            return self._file(os.path.join(comu.CARATULES, nom), 'image/jpeg')
        self.send_error(404)

    # ---------- POST ----------
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        p = urllib.parse.unquote(u.path)
        q = urllib.parse.parse_qs(u.query)
        if not self._permes(q):
            return self._denega()
        try:
            if p == '/api/atura' and self._local():
                self._json({'ok': True})
                threading.Thread(target=SERVIDOR['srv'].shutdown, daemon=True).start()
                return
            if p == '/api/disc':
                rec = json.loads(self._body())
                with BLOC:
                    discs = llegeix('discs.json', [])
                    k = str(rec.get('id'))
                    for i, d in enumerate(discs):
                        if str(d.get('id')) == k:
                            discs[i] = rec
                            break
                    else:
                        discs.append(rec)
                    desa('discs.json', discs)
                return self._json({'ok': True, 'id': rec.get('id')})
            if p == '/api/esborra':
                k = str(json.loads(self._body()).get('id'))
                with BLOC:
                    discs = llegeix('discs.json', [])
                    for d in discs:
                        if str(d.get('id')) == k and d.get('carpeta'):
                            # que la lectura del NAS no la torni a afegir com a pendent
                            ig = llegeix('ignorats.json', {'artistes': [], 'discos': []})
                            if d['carpeta'] not in ig.setdefault('carpetes', []):
                                ig['carpetes'].append(d['carpeta'])
                                desa('ignorats.json', ig)
                    desa('discs.json', [d for d in discs if str(d.get('id')) != k])
                return self._json({'ok': True})
            if p == '/api/artista':
                x = json.loads(self._body())
                nom = str(x.get('nom', '')).strip()
                if not nom:
                    return self._json({'ok': False}, 400)
                with BLOC:
                    arts = llegeix('artistes.json', {})
                    if x.get('id') and str(x['id']) in arts:
                        # corregir el nom d'un artista (s'aplica a tots els seus discos)
                        arts[str(x['id'])] = nom
                        desa('artistes.json', arts)
                        return self._json({'ok': True, 'id': str(x['id'])})
                    for k, v in arts.items():
                        if comu.N(v) == comu.N(nom):
                            return self._json({'ok': True, 'id': k})
                    k = 'a' + str(int(time.time() * 1000))
                    arts[k] = nom
                    desa('artistes.json', arts)
                return self._json({'ok': True, 'id': k})
            if p == '/api/ignora':
                x = json.loads(self._body())
                with BLOC:
                    ig = llegeix('ignorats.json', {'artistes': [], 'discos': []})
                    llista = ig.setdefault(x.get('tipus', 'artistes'), [])
                    if x.get('clau') and x['clau'] not in llista:
                        llista.append(x['clau'])
                    desa('ignorats.json', ig)
                return self._json({'ok': True})
            if p == '/api/caratula':
                k = os.path.basename(q.get('id', [''])[0])
                if not k:
                    return self._json({'ok': False}, 400)
                with open(os.path.join(comu.CARATULES, k + '.jpg'), 'wb') as f:
                    f.write(self._body())
                return self._json({'ok': True})
            if p == '/api/completa':
                if proces['p'] and proces['p'].poll() is None:
                    return self._json({'ok': False, 'motiu': 'Ja està treballant'})
                args = [sys.executable, os.path.join(os.path.dirname(__file__), 'completar.py')]
                mode = q.get('mode', ['tot'])[0]
                args += ['--mode', mode]
                if q.get('n'):
                    args += ['--n', q['n'][0]]
                if q.get('id'):
                    args += ['--id', q['id'][0]]
                flags = 0x08000000 if os.name == 'nt' else 0   # sense finestra
                proces['p'] = subprocess.Popen(args, creationflags=flags)
                return self._json({'ok': True})
        except Exception as e:
            log(f'Error al servidor: {e!r}')
            return self._json({'ok': False, 'motiu': str(e)}, 500)
        self.send_error(404)


def reprograma_tasca():
    """Torna a registrar la tasca diària amb la ruta actual de la carpeta (per si s'ha mogut)."""
    try:
        import eines, contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            eines.programar('14:30')
    except Exception as e:
        log(f'No s\'ha pogut reprogramar la tasca diària: {e!r}')


def main():
    importar_caratules_inicials()
    threading.Thread(target=reprograma_tasca, daemon=True).start()
    try:
        srv = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
        SERVIDOR['srv'] = srv
    except OSError:
        # ja està obert: només obrim el navegador
        comu.obre_navegador(f'http://localhost:{PORT}/')
        return
    print(f'Discoteca oberta a http://localhost:{PORT}/  (tanca aquesta finestra per aturar-la)')
    threading.Timer(0.8, lambda: comu.obre_navegador(f'http://localhost:{PORT}/')).start()
    srv.serve_forever()


if __name__ == '__main__':
    main()
