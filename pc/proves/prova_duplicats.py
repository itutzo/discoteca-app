# -*- coding: utf-8 -*-
"""Prova tancada (còpia de dades i NAS fals amb arxius buits; no toca res de veritat):
 1. quan l'Ignasi reanomena una carpeta a mà, la lectura del NAS no ha de crear una fitxa repetida;
 2. amb les dades d'ara, elimina_duplicats() no ha d'ajuntar discos diferents que es diuen igual (The Spits).
Ús: python prova_duplicats.py <carpeta del codi>"""
import sys, os, json, shutil, tempfile, time
CODI = sys.argv[1]
REAL = r'C:\Users\Usuario\Dropbox\Personal\Discoteca\dades'
NAS = r'C:\SynologyMusic\Mi Musica'
tmp = tempfile.mkdtemp(prefix='dup_')
fals = os.path.join(tmp, 'nas')
sys.path.insert(0, CODI)
import comu
comu.DADES, comu.CARATULES, comu.COPIES, comu.REGISTRE = tmp, tmp, os.path.join(tmp, 'c'), os.path.join(tmp, 'r.txt')
os.makedirs(comu.COPIES)
comu.nas_connectat = lambda *a, **k: False
os.rename = lambda a, b: None
import completar as C
C.CFG['carpeta_musica'] = fals

# (nom de carpeta d'abans, com es deia l'artista a la fitxa vella, títol de la fitxa vella, paraules per trobar la carpeta d'ara)
CASOS = [('[1978] Rose Tattoo - Rose Tattoo', '[1978] Rose Tattoo', 'Rose Tattoo', ('Rose Tattoo', '1978', '')),
         ('High Water II', 'High Water II', 'High Water II', ('Magpie Salute', 'High Water II', '')),
         ("The Roots Of Guns N' Roses", 'Hollywood Rose, Axl Rose, Izzy Stradlin', "The Roots Of Guns N' Roses", ('Hollywood Rose', 'Roots Of Guns', '')),
         ('2000 - Lift Your Skinny Fists Like Antennas To Heaven', '2000', 'Lift Your Skinny Fists Like Antennas To Heaven', ('Godspeed', 'Lift Your Skinny', '')),
         ('Magpie Salute 2018 - High Water I    320', 'Magpie Salute 2018', 'High Water I    320', ('Magpie Salute', '2018', 'High Water I'))]


def carpeta_ara(paraules):
    cs = [c for c in os.listdir(NAS) if all(C.N(p) in C.N(c) for p in paraules if p)]
    return min(cs, key=len)


def copia_buida(src, dst):
    os.makedirs(dst)
    for f in os.listdir(src):
        if os.path.isfile(os.path.join(src, f)):
            open(os.path.join(dst, f), 'wb').close()


artistes, sel = {}, []
for i, (vell, art, tit, paraules) in enumerate(CASOS):
    ara = carpeta_ara(paraules)
    copia_buida(os.path.join(NAS, ara), os.path.join(fals, ara))       # la carpeta amb el nom nou; la vella ja no hi és
    temes = C.temes_de_noms(C.arxius_de(os.path.join(fals, ara)))
    artistes[f'a{i}'] = art
    sel.append({'id': f'nasvell{i}', 'artista': f'a{i}', 'titol': tit, 'suport': 'mp3', 'estat': 'pendent', 'carpeta': vell,
                'temes': temes, 'interprets': [], 'auto': ['titol', 'suport', 'temes', 'data'], 'fonts': {}})
# control: una carpeta nova d'un disc que no té fitxa sí que n'ha de crear una
nou_de_debo = carpeta_ara(('Rose Tattoo', 'Scarred For Life'))
copia_buida(os.path.join(NAS, nou_de_debo), os.path.join(fals, nou_de_debo))
json.dump(sel, open(os.path.join(tmp, 'discs.json'), 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(artistes, open(os.path.join(tmp, 'artistes.json'), 'w', encoding='utf-8'), ensure_ascii=False)
C.llegeix_nas()
despres = C.llegeix('discs.json', [])
esperat = len(sel) + 1
print(f"1. Carpetes reanomenades: {len(sel)} fitxes abans, {len(despres)} després (n'han de ser {esperat}): "
      + ('OK' if len(despres) == esperat else 'FALLA'))

# 2. amb les dades d'ara
for f in ('discs.json', 'artistes.json', 'ignorats.json', 'migracions.json'):
    shutil.copy2(os.path.join(REAL, f), os.path.join(tmp, f))
C.CFG['carpeta_musica'] = NAS
n0 = len(C.llegeix('discs.json', []))
t0 = time.time()
n = C.elimina_duplicats()
p = os.path.join(tmp, 'duplicats_informe.txt')
print(f"2. Dades d'ara ({n0} fitxes): elimina_duplicats() n'ajuntaria {n} en {time.time() - t0:.0f} s")
if n and os.path.exists(p):
    print(open(p, encoding='utf-8').read())
    print('   REVISAR: cada grup ha de ser de veritat el mateix disc (mai dos discos amb carpeta pròpia i temes diferents)')
