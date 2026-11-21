# -*- coding: utf-8 -*-
"""Prova de la norma «edició i temes com els de Discogs» (21/11/2026, «Postcards From A Young Man»), en una còpia de
les dades (no toca dades/ ni el NAS). Per a una mostra de discos amb Discogs (Postcards, els que tenen els números
«101, 201…» i una mostra fixa de la resta) diu quina edició de Discogs es fa servir i quins temes es corregeixen.
Ús:  python prova_edicio.py <carpeta del codi> <sortida.json> [n de la mostra, 80 per defecte]
     python prova_edicio.py --compara <sortida codi antic.json> <sortida codi nou.json>
Amb --compara: cap correcció que el codi antic feia pot desaparèixer amb el nou (si n'hi ha, surt «PASSA ENRERE»)."""
import sys, os, json, shutil, tempfile, copy

if sys.argv[1] == '--compara':
    vell, nou = (json.load(open(f, encoding='utf-8')) for f in sys.argv[2:4])
    enrere = 0
    for k, n in nou.items():
        v = vell.get(k) or {}
        perduts = [c for c in v.get('corregits', []) if c not in n.get('corregits', [])
                   and not any(c[0] == x[0] for x in n.get('corregits', []))]
        if perduts:
            enrere += 1
            print(f"PASSA ENRERE  {n['nom']}: {perduts}")
        canvis = []
        if n.get('edicio') != v.get('edicio'):
            canvis.append(f"edició {v.get('edicio')} -> {n.get('edicio')} ({n.get('temes_dg')} temes a Discogs, {n.get('temes')} a la fitxa)")
        if n.get('numeros') != v.get('numeros'):
            canvis.append(f"números {v.get('numeros')} -> {n.get('numeros')}")
        nous = [c for c in n.get('corregits', []) if c not in v.get('corregits', [])]
        if nous:
            canvis.append('temes: ' + '; '.join(f'«{a}» -> «{b}»' for a, b in nous))
        if canvis:
            print(f"{n['nom']}\n    " + '\n    '.join(canvis))
    print(f"\n{len(nou)} discos comparats · {enrere} amb passes enrere")
    sys.exit(1 if enrere else 0)

CODI, SORTIDA = sys.argv[1], sys.argv[2]
N_MOSTRA = int(sys.argv[3]) if len(sys.argv) > 3 else 80
REAL = r'C:\Users\Usuario\Dropbox\Personal\Discoteca\dades'
tmp = tempfile.mkdtemp(prefix='prova_edicio_')
for f in ('discs.json', 'artistes.json', 'ignorats.json', 'migracions.json'):
    if os.path.exists(os.path.join(REAL, f)):
        shutil.copy2(os.path.join(REAL, f), os.path.join(tmp, f))
sys.path.insert(0, CODI)
import comu
comu.DADES = tmp
comu.COPIES = os.path.join(tmp, 'copies')
os.makedirs(comu.COPIES, exist_ok=True)
comu.REGISTRE = os.path.join(tmp, 'registre.txt')
comu.nas_connectat = lambda *a, **k: False
os.rename = lambda a, b: None
import completar as C

discs = C.llegeix('discs.json', [])
artistes = C.llegeix('artistes.json', {})
amb_dg = [d for d in discs if d.get('discogs_release') and d.get('temes') and d.get('carpeta')]
mostra = [d for d in amb_dg if d.get('id') == 2203]
mostra += [d for d in amb_dg if d not in mostra and all(str(t[0]).strip().isdigit() and int(t[0]) >= 101 for t in d['temes'])]
pas = max(1, len(amb_dg) // N_MOSTRA)
mostra += [d for d in amb_dg[::pas] if d not in mostra][:N_MOSTRA]
out = {}
for i, d in enumerate(mostra):
    nom = f"{artistes.get(str(d.get('artista')), '?')} - {d.get('titol')} ({d['id']})"
    print(f'{i + 1}/{len(mostra)} {nom}', flush=True)
    x = copy.deepcopy(d)
    try:
        if hasattr(C, 'normalitza_numeros'):
            C.normalitza_numeros(x['temes'])
        rel = C.DG.release(d['discogs_release'])
        if rel and hasattr(C, 'millor_edicio'):
            rel = C.millor_edicio([t[1] for t in x['temes'] if len(t) > 1], rel)
        abans = [t[1] for t in x['temes']]
        C.corregeix_temes(x, (rel or {}).get('temes'))
        out[str(d['id'])] = {'nom': nom, 'edicio': (rel or {}).get('id'), 'temes_dg': len((rel or {}).get('temes') or []),
                             'temes': len(x['temes']), 'numeros': [f"{t[3]} {t[0]}".strip() for t in x['temes']][:3],
                             'corregits': [[a, t[1]] for a, t in zip(abans, x['temes']) if a != t[1]]}
    except Exception as e:
        out[str(d['id'])] = {'nom': nom, 'error': repr(e)}
json.dump(out, open(SORTIDA, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(f'Fet: {len(out)} discos -> {SORTIDA}')
shutil.rmtree(tmp, ignore_errors=True)
