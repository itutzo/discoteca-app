"""Prova de «Per a tu»: que no es recomanin grups que ja tens encara que estiguin escrits diferent (norma 14/11/2026).

Ús:  python pc/proves/prova_recomanacions.py <index.html> [<carpeta dades> [<index.html antic>]]

1) Casos de control amb una col·lecció inventada: els que ja tens no es poden recomanar i els que són d'un altre
   grup (encara que s'hi assemblin) sí.
2) Amb la carpeta de dades i l'index.html antic: compara les recomanacions reals amb les dues versions. Cap grup que
   l'antic ja amagava pot tornar a sortir (no fer passes enrere) i es llisten els que ara s'amaguen de nou, amb el
   nom que tens a la discoteca, per revisar-los a mà.
Només llegeix: obre Chrome sense finestra i no toca res de dades\.
"""
import html, json, os, re, subprocess, sys, tempfile

CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
TINC = ["Million $ Reload", "Puddle Of Mud", "Gregg Alexander", "Travis T. Warren", "Guns N' Roses", "Ke$ha",
        "3 Doors Down", "Dr. Feelgood", "Hootie & The Blowfish", "Dear Hunter, The", "Architects", "Dirty Looks",
        "Ryan Adams", "D Generation", "Nebula", "Stevie Ray Vaughan & Double Trouble", "Earth, Wind & Fire",
        "Iron And Wine", "Beatles, The", "Mötley Crüe", "AC/DC", "R.E.M.", "Built To Spilt", "Omar Rodriguez-Lopez"]
DISCS = [("Built To Spilt", "Keep It Like A Secret")]
SI = ["Million Dollar Reload", "Million$ Reload", "MILLION DOLLAR RELOAD", "The Million Dollar Reload", "Puddle of Mudd",
      "Greg Alexander", "Travis Warren", "Guns And Roses", "Guns 'n' Roses", "Kesha", "Three Doors Down",
      "Doctor Feelgood", "Hootie and the Blowfish", "The Dear Hunter", "The Beatles", "Motley Crue", "ACDC", "REM",
      "Stevie Ray Vaughan", "Omar A. Rodriguez-Lopez"]
NO = ["Deerhunter", "Architect", "Dirty Loops", "Bryan Adams", "Generation X", "Nebula-H", "Earth", "Iron", "Wind",
      "Million Reloaders", "Beat"]


def bloc(index):
    L = open(index, encoding='utf8').read().replace('\r', '').split('\n')
    i = next(n for n, l in enumerate(L) if l.startswith('// «Ja el tinc?»'))
    j = next(n for n, l in enumerate(L) if l.startswith('  return tincCache = '))
    return '\n'.join(L[i:j + 2])


def executa(js):
    tmp = tempfile.mkdtemp(prefix='recs_')
    p = os.path.join(tmp, 'p.html')
    open(p, 'w', encoding='utf8').write('<html><body><pre id="o"></pre><script>\n' + js +
                                         '\ndocument.getElementById("o").textContent = JSON.stringify(OUT);</script></body></html>')
    r = subprocess.run([CHROME, '--headless=new', '--disable-gpu', '--user-data-dir=' + os.path.join(tmp, 'c'),
                        '--dump-dom', 'file:///' + p.replace('\\', '/')], capture_output=True, text=True,
                       encoding='utf8', timeout=600)
    return json.loads(html.unescape(re.search(r'<pre id="o">(.*?)</pre>', r.stdout, re.S).group(1)))


BASE = r"""const norm = s => String(s ?? '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
const tok2 = s => norm(s).replace(/^the\s+|,\s*the$/,'').replace(/[^a-z0-9]/g,'');
let artistes = %s, newArtists = {}, discs = %s;
const artName = id => newArtists[id] ?? artistes[id] ?? '';
"""


def main():
    nou = bloc(sys.argv[1])
    art = {str(i): n for i, n in enumerate(TINC)}
    ds = [{'artista': str(TINC.index(a)), 'titol': t} for a, t in DISCS]
    out = executa(BASE % (json.dumps(art), json.dumps(ds)) + nou + """
const J = jaTinc();
const OUT = {si: %s.map(x => [x, J.artista(x)]), no: %s.map(x => [x, J.artista(x)]), disc: J.disc('Built to Spill', 'Keep It Like a Secret')};
""" % (json.dumps(SI), json.dumps(NO)))
    mal = 0
    for x, r in out['si']:
        print(('OK    ' if r else 'MIRAR ') + f'ja el tens, no es recomana: {x}'); mal += not r
    for x, r in out['no']:
        print(('OK    ' if not r else 'MIRAR ') + f'és un altre grup, es pot recomanar: {x}'); mal += r
    print(('OK    ' if out['disc'] else 'MIRAR ') + 'disc «Keep It Like a Secret» de Built to Spill (tens «Built To Spilt»)'); mal += not out['disc']

    if len(sys.argv) > 3:
        D = sys.argv[2]
        art = json.load(open(os.path.join(D, 'artistes.json'), encoding='utf8'))
        ds = [{'artista': x.get('artista'), 'titol': x.get('titol')} for x in json.load(open(os.path.join(D, 'discs.json'), encoding='utf8'))]
        recs = json.load(open(os.path.join(D, 'recs.json'), encoding='utf8'))
        run = """function run(J){ const tinc = new Set(Object.values(artistes).map(tok2)), A = new Set(), Dd = new Set();
  Object.values(R).forEach(r => (r?.discos||[]).forEach(x => J.disc(x.artista, x.titol)));
  for(const r of Object.values(R)){ (r?.artistes||[]).forEach(x => { if(!tinc.has(tok2(x.nom)) && J.artista(x.nom)) A.add(x.nom); });
    (r?.discos||[]).forEach(x => { if(!tinc.has(tok2(x.artista)) && J.disc(x.artista, x.titol)) Dd.add(x.artista + ' | ' + x.titol); }); }
  return {A: [...A], D: [...Dd]}; }
"""
        js = BASE % (json.dumps(art), json.dumps(ds)) + 'const R = ' + json.dumps(recs) + ';\n' + run
        js += 'const VELL = run((function(){ ' + bloc(sys.argv[3]) + '\nreturn jaTinc; })()());\n'
        js += 'const NOU = run((function(){ ' + nou + '\nreturn jaTinc; })()());\n'
        js += 'const OUT = {VELL, NOU};'
        o = executa(js)
        perduts = sorted(set(o['VELL']['A'] + o['VELL']['D']) - set(o['NOU']['A'] + o['NOU']['D']))
        nous = sorted(set(o['NOU']['A']) - set(o['VELL']['A']))
        print(f"\nDades reals: l'antic amagava {len(o['VELL']['A'])} artistes i {len(o['VELL']['D'])} discos; el nou {len(o['NOU']['A'])} i {len(o['NOU']['D'])}.")
        for x in perduts:
            print('MIRAR tornaria a sortir: ' + x); mal += 1
        for x in nous:
            print('NOU   ara s\'amaga: ' + x)
    print('\nTOT BÉ' if not mal else f'\n{mal} CASOS PER MIRAR')
    sys.exit(1 if mal else 0)


main()
