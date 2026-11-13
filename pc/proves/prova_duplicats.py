# -*- coding: utf-8 -*-
"""Prova tancada: quan l'Ignasi reanomena una carpeta a mà, la lectura del NAS no ha de crear una fitxa repetida.
Ús: python prova_dup.py <carpeta del codi>"""
import sys, os, json, shutil, tempfile
CODI = sys.argv[1]
SCR = os.path.dirname(os.path.abspath(__file__))
REAL = r'C:\Users\Usuario\Dropbox\Personal\Discoteca\dades'
NAS = r'C:\SynologyMusic\Mi Musica'
tmp = tempfile.mkdtemp(prefix="dup_")
fals = os.path.join(tmp, 'nas')
sys.path.insert(0, CODI)
import comu
comu.DADES, comu.CARATULES, comu.COPIES, comu.REGISTRE = tmp, tmp, os.path.join(tmp, 'c'), os.path.join(tmp, 'r.txt')
os.makedirs(comu.COPIES)
comu.nas_connectat = lambda *a, **k: False
os.rename = lambda a, b: None
import completar as C
C.CFG['carpeta_musica'] = fals

discs = json.load(open(os.path.join(REAL, 'discs.json'), encoding='utf-8'))
art = json.load(open(os.path.join(REAL, 'artistes.json'), encoding='utf-8'))
# (fitxa vella: nom de carpeta d'abans, nom nou que hi posa l'Ignasi)
CASOS = [('[1978] Rose Tattoo - Rose Tattoo', 'Rose Tattoo - 1978 - Rose Tattoo'),
         ('High Water II', 'The Magpie Salute – High Water II'),
         ("The Roots Of Guns N' Roses", "Hollywood Rose - 2004 - The Roots Of Guns N' Roses"),
         ('2000 - Lift Your Skinny Fists Like Antennas To Heaven', 'Godspeed You Black Emperor! – Lift Your Skinny Fists Like Antennas To'),
         ('Magpie Salute 2018 - High Water I    320', 'The Magpie Salute - 2018 - High Water I')]
per_c = {d.get('carpeta'): d for d in discs}
sel, artistes = [], {}
for vell, nou in CASOS:
    d = json.loads(json.dumps(per_c[vell]))
    sel.append(d)
    artistes[str(d['artista'])] = art[str(d['artista'])]
    # carpeta nova amb els arxius d'ara (buits); la vella ja no hi és
# arxius: els de la carpeta que hi ha ara al NAS per a cada disc
ARA = {'[1978] Rose Tattoo - Rose Tattoo': 'Rose Tattoo - Rose Tattoo',
       'High Water II': 'The Magpie Salute – High Water II',
       "The Roots Of Guns N' Roses": "Hollywood Rose - 2004 - The Roots Of Guns N' Roses",
       '2000 - Lift Your Skinny Fists Like Antennas To Heaven': 'Godspeed You Black Emperor! – Lift Your Skinny Fists Like Antennas To',
       'Magpie Salute 2018 - High Water I    320': 'The Magpie Salute - 2018 - High Water I'}
for vell, nou in CASOS:
    os.makedirs(os.path.join(fals, nou))
    for f in os.listdir(os.path.join(NAS, ARA[vell])):
        open(os.path.join(fals, nou, f), 'wb').close()
# control: un disc diferent amb carpeta que existeix i una altra carpeta nova d'un altre disc del mateix artista
ctrl = next(d for d in discs if (d.get('carpeta') or '') == 'Rose Tattoo - 1981 - Assault & Battery')
sel.append(json.loads(json.dumps(ctrl)))
artistes[str(ctrl['artista'])] = art[str(ctrl['artista'])]
os.makedirs(os.path.join(fals, ctrl['carpeta']))
for f in os.listdir(os.path.join(NAS, ctrl['carpeta'])):
    open(os.path.join(fals, ctrl['carpeta'], f), 'wb').close()
os.makedirs(os.path.join(fals, 'Rose Tattoo - 1982 - Scarred For Life'))
for f in os.listdir(os.path.join(NAS, 'Rose Tattoo - 1982 - Scarred For Life')):
    open(os.path.join(fals, 'Rose Tattoo - 1982 - Scarred For Life', f), 'wb').close()
json.dump(sel, open(os.path.join(tmp, 'discs.json'), 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(artistes, open(os.path.join(tmp, 'artistes.json'), 'w', encoding='utf-8'), ensure_ascii=False)
abans = len(sel)
C.llegeix_nas()
despres = C.llegeix('discs.json', [])
print(f'Fitxes abans: {abans} · carpetes al NAS fals: {len(os.listdir(fals))} · fitxes després: {len(despres)}')
for d in despres:
    print('  ', d['id'], '|', d.get('carpeta'))
