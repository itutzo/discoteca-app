# -*- coding: utf-8 -*-
"""Prova de la norma «l'estil que diuen més fonts» (21/11/2026) en una còpia de les dades (no toca dades/ ni el NAS):
per a una mostra de discos (Postcards From A Young Man i uns quants de cada estil de la discoteca) diu quin estil hi
posaria el programa i amb quines fonts (AllMusic/Access, Discogs, MusicBrainz, Wikipedia, Last.fm). No desa res.
Ús:  python prova_estil_consens.py <carpeta del codi> <sortida.json> [discos per estil, 6 per defecte] [màxim, 150]"""
import sys, os, json, shutil, tempfile, copy, collections

CODI, SORTIDA = sys.argv[1], sys.argv[2]
PER_ESTIL = int(sys.argv[3]) if len(sys.argv) > 3 else 6
MAXIM = int(sys.argv[4]) if len(sys.argv) > 4 else 150
REAL = r'C:\Users\Usuario\Dropbox\Personal\Discoteca\dades'
tmp = tempfile.mkdtemp(prefix='prova_estils_')
for f in ('discs.json', 'artistes.json', 'ignorats.json', 'migracions.json', 'lastfm.json'):
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
amb_fonts = [d for d in discs if d.get('discogs_release') or (d.get('fonts') or {}).get('MusicBrainz')]
mostra = [d for d in amb_fonts if d.get('id') == 2203]
per_estil = collections.defaultdict(list)
for d in amb_fonts:
    per_estil[d.get('estil') or ''].append(d)
for e, xs in sorted(per_estil.items(), key=lambda kv: -len(kv[1])):
    pas = max(1, len(xs) // PER_ESTIL)
    mostra += [x for x in xs[::pas] if x not in mostra][:PER_ESTIL]
mostra = mostra[:MAXIM]
E, meus = C.estils_vocabulari(discs), C.estils_de_la_discoteca(discs)
out, canvis = {}, collections.Counter()
for i, d in enumerate(mostra):
    nom = f"{artistes.get(str(d.get('artista')), '?')} - {d.get('titol')} ({d['id']})"
    print(f'{i + 1}/{len(mostra)} {nom}', flush=True)
    try:
        vots = C.fonts_estil(copy.deepcopy(d), artistes.get(str(d.get('artista')), ''))
        nou, detall = C.decideix_estil(d, vots, E, meus)
        out[str(d['id'])] = {'nom': nom, 'estil': d.get('estil'), 'nou': nou, 'fonts': detall, 'vots': vots}
        if nou:
            canvis[(d.get('estil'), nou)] += 1
    except Exception as e:
        out[str(d['id'])] = {'nom': nom, 'error': repr(e)}
json.dump(out, open(SORTIDA, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
n_canvi = sum(1 for v in out.values() if v.get('nou'))
print(f"\n{len(out)} discos mirats · {n_canvi} canviarien d'estil · {sum(1 for v in out.values() if v.get('error'))} errors")
print('\nCanvis (estil d\'ara -> estil nou: discos):')
for (a, b), n in canvis.most_common():
    print(f'  {a} -> {b}: {n}')
print('\nExemples:')
for v in out.values():
    if v.get('nou'):
        print(f"  {v['nom']}: {v['estil']} -> {v['nou']}   {v['fonts']}")
shutil.rmtree(tmp, ignore_errors=True)
