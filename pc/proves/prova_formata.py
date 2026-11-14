# -*- coding: utf-8 -*-
"""Simulació de formata_tots() amb les dades d'ara: res es reanomena ni es mou (tot queda anotat).
Ús: python prova_formata.py <carpeta del codi>"""
import sys, os, shutil, tempfile, collections
sys.path.insert(0, sys.argv[1])
import comu
REAL = r'C:\Users\Usuario\Dropbox\Personal\Discoteca\dades'
tmp = tempfile.mkdtemp(prefix='formata_')
for f in ('discs.json', 'artistes.json', 'ignorats.json', 'migracions.json'):
    shutil.copy2(os.path.join(REAL, f), os.path.join(tmp, f))
comu.DADES, comu.CARATULES, comu.COPIES, comu.REGISTRE = tmp, tmp, os.path.join(tmp, 'c'), os.path.join(tmp, 'r.txt')
os.makedirs(comu.COPIES)
comu.nas_connectat = lambda *a, **k: True
fets = []
_mk = os.makedirs
mapa = {}
def _ren(a, b):
    fets.append(('rename', a, b))
    if os.path.dirname(a).endswith('Mi Musica'):
        mapa[os.path.normcase(b)] = a      # la carpeta segueix amb el nom vell: es tradueix
os.rename = _ren
def tr(p):
    p = str(p)
    for nou, vell in mapa.items():
        if os.path.normcase(p).startswith(nou):
            return vell + p[len(nou):]
    return p
_stat, _walk, _isdir, _exists = os.stat, os.walk, os.path.isdir, os.path.exists
os.stat = lambda p, *a, **k: _stat(tr(p), *a, **k)
os.walk = lambda p, *a, **k: _walk(tr(p), *a, **k)
os.path.isdir = lambda p: _isdir(tr(p))
os.path.exists = lambda p: _exists(tr(p)) if os.path.normcase(str(p)) in mapa else _exists(p)
shutil.move = lambda a, b, *k, **kw: fets.append(('move', a, b))
os.makedirs = lambda p, *a, **k: None if 'Mi Musica' in p else _mk(p, *a, **k)
import completar as C
C.formata_tots()
carpetes = [x for x in fets if x[0] == 'rename' and os.path.dirname(x[1]).endswith('Mi Musica')]
arxius = [x for x in fets if x[0] == 'rename' and x not in carpetes]
moguts = [x for x in fets if x[0] == 'move']
per = collections.Counter(os.path.basename(os.path.dirname(x[1])) for x in arxius)
print(f'carpetes reanomenades: {len(carpetes)} · arxius reanomenats: {len(arxius)} en {len(per)} carpetes · moguts a la paperera: {len(moguts)}')
for x in carpetes:
    print('  C', os.path.basename(x[1]), '->', os.path.basename(x[2]))
for x in moguts[:10]:
    print('  P', x[1])
vist = set()
for x in arxius:
    k = os.path.dirname(x[1])
    if k not in vist and len(vist) < 12:
        vist.add(k); print('  A', os.path.basename(x[1]), '->', os.path.basename(x[2]))

import re, json
alt = []
for x in arxius:
    a, b = os.path.basename(x[1]), os.path.basename(x[2])
    a2 = re.sub(r'^(.+?), The - ', lambda m: 'The ' + m.group(1) + ' - ', a, flags=re.I)
    if a2 != b:
        alt.append((os.path.basename(os.path.dirname(x[1])), a, b))
[print('  X', *x) for x in alt[:40]]
print('reanomenaments que no són només «The»:', len(alt), 'en', len({x[0] for x in alt}), 'carpetes')
