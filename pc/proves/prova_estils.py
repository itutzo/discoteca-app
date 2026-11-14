"""Prova de la unificació dels estils (norma del 14/11/2026), sense tocar res.

    python pc/proves/prova_estils.py <carpeta del codi> [<carpeta dades>]

Casos de control: tots han de dir OK. Amb la carpeta de dades, llista quins estils i gèneres s'ajuntarien."""
import collections, json, os, sys

codi = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'app')
sys.path.insert(0, os.path.abspath(codi))
import comu  # noqa: E402

dades = sys.argv[2] if len(sys.argv) > 2 else None
lf = json.load(open(os.path.join(dades, 'lastfm.json'), encoding='utf-8')) if dades else {}

IGUALS = [('Pop Rock', 'Pop-Rock'), ('Pop Rock', 'Pop/Rock'), ('Pop Rock', 'Pop7Rock'), ('Pop Rock', 'PopRock'),
          ('Rock & Roll', "Rock n' Roll"), ('Post-Grunge', 'Post Grunge'), ('Alternative', 'Alternativa'),
          ('Electro-Industrial', 'Electro-Industrial\nElectro-Industrial'), ('Psychedelic', 'Psicodelico'),
          ('Alternative/Indie Rock', 'Alternative/ Indie Rock')]
DIFERENTS = [('Punk Rock', 'Funk Rock'), ('Hard Rock', 'Hair Rock'), ('Garage', 'Garage Rock'), ('Heavy', 'Heavy Metal'),
             ('Stoner', 'Stoner Rock'), ('American Trad Rock', 'American Rock'), ('Alternative Folk', 'Alternative Rock')]
FALTES = [('Southen Rock', 'Southern Rock'), ('Alternarive Indie Rock', 'Alternative/Indie Rock'),
          ('Experiemntal Pop', 'Experimental Pop'), ('Rcok', 'Rock'), ('Blue Rock', 'Blues Rock')]

E = comu.Estils(lf)
mal = 0
for a, b in IGUALS:
    ok = comu.clau_estil(a, E) == comu.clau_estil(b, E)
    mal += not ok
    print('OK ' if ok else 'MAL', 'iguals:', repr(a), repr(b))
for a, b in DIFERENTS:
    m = comu.unifica_estils_llista([a, b], lf, {a: 10, b: 10})
    ok = m[a] != m[b]
    mal += not ok
    print('OK ' if ok else 'MAL', 'diferents:', repr(a), repr(b))
if lf:
    for a, b in FALTES:
        m = comu.unifica_estils_llista([a, b], lf, {a: 1, b: 50})
        ok = m[a] == m[b]
        mal += not ok
        print('OK ' if ok else 'MAL', 'falta:', repr(a), '→', repr(m[a]))
if dades:
    discs = json.load(open(os.path.join(dades, 'discs.json'), encoding='utf-8'))
    for camp in ('estil', 'genere'):
        c = collections.Counter(d[camp] for d in discs if isinstance(d.get(camp), str) and d[camp].strip())
        m = comu.unifica_estils_llista(list(c), lf, c)
        g = collections.defaultdict(list)
        for v, b in m.items():
            g[b].append(v)
        print(f'\n{camp}: {len(c)} → {len(g)}')
        for b in sorted(g, key=str.lower):
            if len(g[b]) > 1 or g[b][0] != b:
                print(f'  {b}  ←  ' + ', '.join(f'{v!r} ({c[v]})' for v in sorted(g[b])))
print('\nTOT OK' if not mal else f'\n{mal} CASOS MALAMENT')
