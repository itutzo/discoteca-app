# -*- coding: utf-8 -*-
"""Prova en un entorn tancat (còpia de les dades, cap canvi al NAS): els 14 pendents i els casos ja resolts.
Ús: python prova.py <carpeta del codi> <sortida.json> [pendents|regressio|tot]"""
import sys, os, json, shutil, time, re, tempfile

CODI, SORTIDA = sys.argv[1], sys.argv[2]
QUE = sys.argv[3] if len(sys.argv) > 3 else 'tot'
SCR = os.path.dirname(os.path.abspath(__file__))
REAL = r'C:\Users\Usuario\Dropbox\Personal\Discoteca\dades'
NAS = r'C:\SynologyMusic\Mi Musica'
tmp = tempfile.mkdtemp(prefix="prova_")
for f in ('discs.json', 'artistes.json', 'ignorats.json', 'migracions.json'):
    shutil.copy2(os.path.join(REAL, f), os.path.join(tmp, f))
os.makedirs(os.path.join(tmp, 'car'), exist_ok=True)

sys.path.insert(0, CODI)
import comu
comu.DADES = tmp
comu.CARATULES = os.path.join(tmp, 'car')
comu.COPIES = os.path.join(tmp, 'copies')
os.makedirs(comu.COPIES, exist_ok=True)
comu.REGISTRE = os.path.join(tmp, 'registre.txt')
comu.nas_connectat = lambda *a, **k: False
renames = []
os.rename = lambda a, b: renames.append((a, b))          # mai es reanomena res
import fonts
fonts.descarrega = lambda url: None
import completar as C
C.recomana = lambda *a, **k: None
C.bitrate_estimat = lambda *a, **k: None
_et = C.etiqueta_mp3
C.etiqueta_mp3 = lambda ruta: {} if ruta.lower().startswith(NAS.lower()) else _et(ruta)   # mai s'obren els MP3 del NAS

out = {'renames': renames}


def resum(d, artistes):
    return {'artista': artistes.get(str(d.get('artista')), ''), 'titol': d.get('titol'), 'any': d.get('any'),
            'discogs': (d.get('fonts') or {}).get('Discogs'), 'mb': (d.get('fonts') or {}).get('MusicBrainz'),
            'estat': d.get('estat'), 'carpeta': d.get('carpeta')}


if QUE in ('pendents', 'tot'):
    discs0 = C.llegeix('discs.json', [])
    pend_ids = [d['id'] for d in discs0 if d.get('estat') == 'pendent']
    try:
        out['duplicats'] = C.elimina_duplicats()
    except Exception as e:
        out['duplicats'] = repr(e)
    try:
        out['repara'] = C.repara_pendents() if hasattr(C, 'repara_pendents') else 'no existeix'
    except Exception as e:
        out['repara'] = repr(e)
    artistes = C.llegeix('artistes.json', {})
    discs = C.llegeix('discs.json', [])
    estils = {C.N(d['estil']): d['estil'] for d in discs if d.get('estil')}
    per_id = {d['id']: d for d in discs}
    res = {}
    for i in pend_ids:
        d = per_id.get(i)
        if not d:
            res[i] = {'ajuntat': True, 'abans': next(resum(x, C.llegeix('artistes.json', {})) for x in discs0 if x['id'] == i)}
            continue
        try:
            if not (d.get('fonts') or {}).get('Discogs'):
                # primer com si el NAS no respongués (només completa(), sense llegir res de la carpeta)
                for k in ('id_temes', 'art_dg', 'no_trobat'):
                    d.pop(k, None)
                C.completa(d, artistes, estils)
                if not d.get('fonts') and C.artista_de_etiquetes(d, NAS, artistes):
                    C.completa(d, artistes, estils)
        except Exception as e:
            import traceback; traceback.print_exc()
            res[i] = {'error': repr(e)}
            continue
        res[i] = resum(d, artistes)
    out['pendents'] = res
    json.dump(out, open(SORTIDA, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

# ---------------- casos ja resolts: carpeta amb el nom original i els arxius d'ara (arxius buits en una carpeta falsa)
CASOS = [
    ('1989 - God\'s Balls', 'Tad - 1989 - God\'s Balls', 'Tad', "God's Balls"),
    ('Noiseworks', 'Noiseworks - 1987 - Noiseworks', 'Noiseworks', 'Noiseworks'),
    ('Touch', 'Noiseworks - 1988 - Touch', 'Noiseworks', 'Touch'),
    ('Copper Blue (1992) - [320]', 'Sugar - 1992 - Copper Blue', 'Sugar', 'Copper Blue'),
    ('Sons Of Texas - Baptized In The Rio Grande (2015)-Texas,US (Groove Metal)', 'Sons Of Texas - 2015 - Baptized In The Rio Grande', 'Sons Of Texas', 'Baptized In The Rio Grande'),
    ('2008-Jumpstart Diary', 'Russell Morris - 2008 - Jumpstart Diary', 'Russell Morris', 'Jumpstart Diary'),
    ('Stone Machine - American Honey (2012)-West Virginia,US', 'Stone Machine - 2012 - American Honey', 'Stone Machine', 'American Honey'),
    ('Guns Of Gold - 2006', 'The Fumes - 2006 - Guns Of Gold', 'The Fumes', 'Guns Of Gold'),
    ('Tad - 8-Way Santa [1991]', 'Tad - 1991 - 8-Way Santa', 'Tad', '8-Way Santa'),
    ('Thelonious Monster - Beautiful Mess', 'Thelonious Monster - 1992 - Beautiful Mess', 'Thelonious Monster', 'Beautiful Mess'),
    ('Hollywood Rose - The Roots Of Guns N\' Roses', 'Hollywood Rose - 2004 - The Roots Of Guns N\' Roses', 'Hollywood Rose', "The Roots Of Guns N' Roses"),
    ('Brides of Destruction - Here Come the Brides', 'Brides of Destruction - 2004 - Here Come The Brides', 'Brides Of Destruction', 'Here Come The Brides'),
    ('Glenn Proudfoot - Fire & Rain', 'Glenn Proudfoot - 2017 - Fire & Rain', 'Glenn Proudfoot', 'Fire & Rain'),
    ('Live - Throwing Copper', 'Live - 1994 - Throwing Copper', 'Live', 'Throwing Copper'),
    # els 14 pendents del 12/11/2026 (resolts el 13/11 amb la identificació robusta)
    ('California Breed - 2014 - California Breed', 'California Breed - 2014 - California Breed', 'California Breed', 'California Breed'),
    ('Dozer - Call it Conspiracy', 'Dozer - Call it Conspiracy', 'Dozer', 'Call It Conspiracy'),
    ('[1978] Rose Tattoo - Rose Tattoo', 'Rose Tattoo - Rose Tattoo', 'Rose Tattoo', 'Rose Tattoo'),
    ('High Water II', 'The Magpie Salute – High Water II', 'The Magpie Salute', 'High Water II'),
    ('Magpie Salute 2018 - High Water I    320', 'The Magpie Salute - 2018 - High Water I', 'The Magpie Salute', 'High Water I'),
    ('Magpie Salute, the 2017 - The magpipe Salute  FLAC', 'Magpie Salute, the 2017 - The magpipe Salute  FLAC', 'The Magpie Salute', 'The Magpie Salute'),
    ('Godspeed You Black Emperor! – Lift Your Skinny Fists Like Antennas To', 'Godspeed You Black Emperor! – Lift Your Skinny Fists Like Antennas To', 'Godspeed You Black Emperor!', 'Lift Your Skinny Fists Like Antennas To Heaven'),
    ('2010 - Love Is In The Missile', '2010 - Love Is In The Missile', 'Atom Smash', 'Love Is In The Missile'),
    ('In Vino Verilivicus MMXIX (Live) (2020)', 'In Vino Verilivicus MMXIX (Live) (2020)', "Tyla's Dogs D'Amour", 'In Vino Verilivicus'),
    ('Mothership Connection [1975]', 'Mothership Connection [1975]', 'Parliament', 'Mothership Connection'),
    # resolts el 14/11/2026 (carpetes noves del dia)
    ('2019 - One Man Gang', 'Michael Monroe - 2019 - One Man Gang', 'Michael Monroe', 'One Man Gang'),
    ('Bright Side of Dim', 'Mothership, The - 2014 - Bright Side Of Dim', 'The Mothership', 'Bright Side Of Dim'),
    ('Skin Of My teeth-MAD JUANA', 'Mad Juana - 1997 - Skin Of My Teeth', 'Mad Juana', 'Skin Of My Teeth'),
    # l'artista amb notes entre parèntesis ha de quedar net (14/11/2026)
    ('Grease Helmet (FIN,pre-Ajattara,Amorphis,Amoral) [glam,hard-rock] - 2012 - Grease Helmet',
     'Grease Helmet (FIN,pre-Ajattara,Amorphis,Amoral) [glam,hard-rock] - 2012 - Grease Helmet', 'Grease Helmet', 'Grease Helmet'),
]


def carpeta_ara(ara, art, tit):
    """La carpeta d'avui al NAS (pot haver canviat de nom des que es va afegir el cas)."""
    if os.path.isdir(os.path.join(NAS, ara)):
        return ara
    for c in os.listdir(NAS):
        if C.N(art) in C.N(c) and C.NT(tit) in C.NT(c):
            return c
    return ara


def casos_extra():
    """Discos dobles i carpetes normals ja trobades: es busquen tal com estan ara."""
    discs = json.load(open(os.path.join(REAL, 'discs.json'), encoding='utf-8'))
    ar = json.load(open(os.path.join(REAL, 'artistes.json'), encoding='utf-8'))
    al_nas = set(os.listdir(NAS))
    dobles, normals = [], []
    for d in discs:
        c = d.get('carpeta')
        if not c or c not in al_nas or not (d.get('fonts') or {}).get('Discogs') or not str(d.get('id', '')).startswith('nas'):
            continue
        if any(len(t) > 3 and str(t[3]).startswith('CD2') for t in d.get('temes') or []):
            dobles.append(d)
        else:
            normals.append(d)
    import random
    random.seed(13)
    sel = random.sample(dobles, min(3, len(dobles))) + random.sample(normals, min(8, len(normals)))
    return [(d['carpeta'], d['carpeta'], ar.get(str(d['artista'])), d.get('titol')) for d in sel]


if QUE in ('regressio', 'tot'):
    fals = os.path.join(tmp, 'nas_fals')
    res = []
    artistes = C.llegeix('artistes.json', {})
    discs = C.llegeix('discs.json', [])
    estils = {C.N(d['estil']): d['estil'] for d in discs if d.get('estil')}
    for orig, ara, art_ok, tit_ok in CASOS + casos_extra():
        src = os.path.join(NAS, carpeta_ara(ara, art_ok, tit_ok))
        if not os.path.isdir(src):
            res.append({'carpeta': orig, 'error': 'no trobo la carpeta ' + ara})
            continue
        dst = os.path.join(fals, orig)
        for r, _, fs in os.walk(src):
            sub = os.path.relpath(r, src)
            os.makedirs(os.path.join(dst, sub), exist_ok=True)
            for f in fs:
                open(os.path.join(dst, sub, f), 'wb').close()
        if hasattr(C, 'parteix_carpeta'):
            art, any_, tit = C.parteix_carpeta(orig)
        else:
            m = re.match(r'^(.+?)\s*[-–—]\s*(\d{4})\s*[-–—]\s*(.+)$', orig) or re.match(r'^(.+?)\s*[-–—]\s*()(.+)$', orig)
            art, any_, tit = (m.group(1).strip(), m.group(2), m.group(3).strip()) if m else (orig, '', orig)
            net, any_p = comu.titol_net(tit)
            if net and m:
                tit, any_ = net, any_ or any_p
        arx = C.arxius_de(dst)
        d = {'id': 'nas' + str(int(time.time() * 1000)), 'artista': C.id_artista(art, artistes), 'titol': tit, 'suport': 'mp3',
             'estat': 'pendent', 'carpeta': orig, 'temes': C.temes_de_noms(arx), 'interprets': [],
             'auto': ['titol', 'suport', 'temes', 'data'] + (['any'] if any_ else [])}
        if any_:
            d['any'] = any_
        t0 = time.time()
        try:
            for nit in range(2):          # dues nits: primer l'artista dels arxius o de Discogs, després completar
                C.artista_de_etiquetes(d, fals, artistes)
                C.neteja_titol_nou(d)
                C.completa(d, artistes, estils)
                if (d.get('fonts') or {}).get('Discogs'):
                    break
        except Exception as e:
            import traceback; traceback.print_exc()
            res.append({'carpeta': orig, 'error': repr(e)})
            continue
        r = resum(d, artistes)
        r['esperat'] = f'{art_ok} - {tit_ok}'
        r['segons'] = round(time.time() - t0)
        r['ok'] = bool(r['discogs']) and C.N(r['artista']) == C.N(art_ok) and C.NT(r['titol']) == C.NT(tit_ok)
        res.append(r)
        print(('OK ' if r['ok'] else 'FALLA ') + orig + ' -> ' + f"{r['artista']} - {r['titol']} ({r['segons']} s)", flush=True)
    out['regressio'] = res
    json.dump(out, open(SORTIDA, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('fet')
