# -*- coding: utf-8 -*-
"""Simulació, en una còpia de les dades, del que faria el programa als noms dels arxius del NAS després de posar els
números de disc doble («101» -> CD1), triar l'edició de Discogs pels temes i corregir els temes com els de Discogs
(norma del 21/11/2026, «Postcards From A Young Man»), i llavors formata_tots(). No reanomena ni mou res (tot queda
anotat), no toca dades/ i només llegeix els noms de les carpetes del NAS (no obre cap arxiu).
Ús: python prova_formata_edicio.py <carpeta del codi> [n de la mostra, 80 per defecte]
Surt amb error (1) si hi ha alguna «ANOMALIA»: un arxiu que canviaria de CD, o que agafaria el nom d'un tema que a la
fitxa és d'un altre CD (el que passava amb el disc i les maquetes de «Postcards From A Young Man»)."""
import sys, os, re, shutil, tempfile, collections
CODI = sys.argv[1]
N_MOSTRA = int(sys.argv[2]) if len(sys.argv) > 2 else 80
sys.path.insert(0, CODI)
import comu
REAL = r'C:\Users\Usuario\Dropbox\Personal\Discoteca\dades'
tmp = tempfile.mkdtemp(prefix='formata_edicio_')
for f in ('discs.json', 'artistes.json', 'ignorats.json', 'migracions.json'):
    if os.path.exists(os.path.join(REAL, f)):
        shutil.copy2(os.path.join(REAL, f), os.path.join(tmp, f))
comu.DADES, comu.CARATULES, comu.COPIES, comu.REGISTRE = tmp, tmp, os.path.join(tmp, 'c'), os.path.join(tmp, 'r.txt')
os.makedirs(comu.COPIES)
comu.nas_connectat = lambda *a, **k: True
fets, mapa = [], {}
_mk = os.makedirs


def _ren(a, b):
    fets.append(('rename', a, b))
    if os.path.dirname(a).endswith('Mi Musica'):
        mapa[os.path.normcase(b)] = a      # la carpeta segueix amb el nom vell: es tradueix


def tr(p):
    p = str(p)
    for nou, vell in mapa.items():
        if os.path.normcase(p).startswith(nou):
            return vell + p[len(nou):]
    return p


os.rename = _ren
_stat, _walk, _isdir, _exists = os.stat, os.walk, os.path.isdir, os.path.exists
os.stat = lambda p, *a, **k: _stat(tr(p), *a, **k)
os.walk = lambda p, *a, **k: _walk(tr(p), *a, **k)
os.path.isdir = lambda p: _isdir(tr(p))
os.path.exists = lambda p: _exists(tr(p)) if os.path.normcase(str(p)) in mapa else _exists(p)
shutil.move = lambda a, b, *k, **kw: fets.append(('move', a, b))
os.makedirs = lambda p, *a, **k: None if 'Mi Musica' in str(p) else _mk(p, *a, **k)
import completar as C

C.normalitza_numeros_tots()
discs = C.llegeix('discs.json', [])
artistes = C.llegeix('artistes.json', {})
es_cd = lambda t: len(t) > 3 and re.match(r'^CD\d+$', str(t[3]))
amb_dg = [d for d in discs if d.get('discogs_release') and d.get('temes') and d.get('carpeta')]
mostra = [d for d in amb_dg if d.get('id') == 2203]
mostra += [d for d in amb_dg if d not in mostra and any(es_cd(t) for t in d['temes'])][:N_MOSTRA]   # discos dobles
pas = max(1, len(amb_dg) // N_MOSTRA)
mostra += [d for d in amb_dg[::pas] if d not in mostra][:N_MOSTRA]
corregits = 0
for i, d in enumerate(mostra):
    print(f"{i + 1}/{len(mostra)} {artistes.get(str(d.get('artista')), '?')} - {d.get('titol')} ({d['id']})", flush=True)
    try:
        rel = C.DG.release(d['discogs_release'])
        if rel:
            rel = C.millor_edicio([t[1] for t in d['temes'] if len(t) > 1], rel)
        corregits += bool(C.corregeix_temes(d, (rel or {}).get('temes')))
    except Exception as e:
        print('   error', repr(e))
C.desa('discs.json', discs)
C.formata_tots()

arxius = [x for x in fets if x[0] == 'rename' and not os.path.dirname(x[1]).endswith('Mi Musica')]
carpetes = [x for x in fets if x[0] == 'rename' and x not in arxius]
moguts = [x for x in fets if x[0] == 'move']
per_carpeta = {d['carpeta']: d for d in mostra}
cd_de = lambda nom: (lambda m: int(m.group(1)) if m else 0)(re.search(r'(?:^|[\s\-_(\[/\\])(?:CD|Disc|Disco|Disk)\s*(\d{1,2})\b', nom, re.I))
anomalies, exemples = [], collections.defaultdict(list)
for _, a, b in arxius:
    rel_a = os.path.relpath(a, C.CFG.get('carpeta_musica', r'C:\SynologyMusic\Mi Musica'))
    carpeta = rel_a.split(os.sep)[0]
    exemples[carpeta].append((rel_a, os.path.basename(b)))
    d = per_carpeta.get(carpeta)
    if not d:
        continue
    cd_vell, cd_nou = cd_de(rel_a), cd_de(os.path.basename(b))
    if cd_vell and cd_nou and cd_vell != cd_nou:
        anomalies.append(f'canvia de CD: {rel_a} -> {os.path.basename(b)}')
    m = re.search(r' - \d{2,3} - (.+)\.[^.]+$', os.path.basename(b))
    if m and cd_nou:
        cds = {int(str(t[3])[2:]) for t in d['temes'] if es_cd(t) and C.N(t[1]) == C.N(m.group(1))}
        if cds and cd_nou not in cds:
            anomalies.append(f'nom d\'un tema del CD {sorted(cds)}: {rel_a} -> {os.path.basename(b)}')

print(f'\nMostra: {len(mostra)} discos, {corregits} amb temes corregits')
print(f'Carpetes reanomenades: {len(carpetes)} · arxius reanomenats: {len(arxius)} en {len(exemples)} carpetes · '
      f'moguts a la paperera: {len(moguts)}')
for x in carpetes:
    print('  C', os.path.basename(x[1]), '->', os.path.basename(x[2]))
for x in moguts[:10]:
    print('  P', x[1])
for carpeta, ll in exemples.items():
    d = per_carpeta.get(carpeta)
    tots = d is not None and d.get('id') == 2203
    print(f'\n  [{carpeta}] {len(ll)} arxius' + ('' if d else ' (fora de la mostra: ja estava pendent de formatar)'))
    for a, b in (ll if tots else ll[:3]):
        print('    ', a, '->', b)
print(f'\nANOMALIES: {len(anomalies)}')
for x in anomalies:
    print('  ANOMALIA', x)
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if anomalies else 0)
