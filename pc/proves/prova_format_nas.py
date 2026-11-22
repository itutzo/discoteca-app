# -*- coding: utf-8 -*-
"""Prova tancada del guardià del format del NAS (norma fixa, 22/11/2026). NAS fals amb arxius petits a una carpeta
temporal; no toca ni les dades ni el NAS de veritat. Comprova que, a cada execució, totes les carpetes acaben amb el
format «Artista - Any - Títol» i tots els arxius amb «Artista - Títol - 01 - Cançó», sense dependre de cap marca, i
que el que ja estava bé no es toca. S'ha de passar abans d'instal·lar qualsevol canvi (totes les línies «OK»).
Ús: python prova_format_nas.py <carpeta del codi>"""
import sys, os, json, tempfile
sys.path.insert(0, sys.argv[1])
import comu
tmp = tempfile.mkdtemp(prefix='guardia_')
nas = os.path.join(tmp, 'Mi Musica')
comu.DADES, comu.CARATULES, comu.COPIES, comu.REGISTRE = tmp, tmp, os.path.join(tmp, 'c'), os.path.join(tmp, 'r.txt')
os.makedirs(comu.COPIES)
comu.nas_connectat = lambda *a, **k: True
import completar as C
C.CFG['carpeta_musica'] = nas
DG = {'Discogs': 'https://www.discogs.com/release/1'}


def carpeta(nom, arxius, mida=1000):
    os.makedirs(os.path.join(nas, nom))
    for a in arxius:
        with open(os.path.join(nas, nom, a), 'wb') as f:
            f.write(b'\0' * mida)


TEMES_MCD = ['I Want a Lot Now (So Come on)', "Dancin' Shoes", '18 Wheels', 'Left Hand, Right Hand']
TEMES_EE = ['How Much Time', 'Talk Yourself Blind', 'American Nightmare (Revisited)', 'Someone']
TEMES_PFE = ['Count Me Out', 'Strangelove', 'Elusive', 'Only Way For Me']
T = lambda L: [[str(i + 1), t, '', '', 0, 0] for i, t in enumerate(L)]
artistes = {'1': 'Murder City Devils', '2': 'Before Cars', '3': 'Injected', '4': 'Varios', '5': 'Rose Tattoo',
            '6': "Endino's Earthworm", '7': 'Jack Endino', '8': 'The Gaslight Anthem', '9': 'Kiss', '10': 'Nobody'}
discs = []
# 1. disc identificat amb el NAS desconnectat i després desat des de la pàgina (sense «ident_temes»)
carpeta('1998 - Empty Bottles, Broken Hearts', [f'{i + 1:02d}. The Murder City Devils - {t}.mp3' for i, t in enumerate(TEMES_MCD)])
discs.append({'id': 'nas1', 'artista': '1', 'any': '1998', 'titol': 'Empty Bottles, Broken Hearts', 'fonts': DG,
              'carpeta': '1998 - Empty Bottles, Broken Hearts', 'temes': T(TEMES_MCD), 'auto': ['artista', 'titol', 'temes']})
# 2. any entre parèntesis
carpeta('(2013) How We Run', ['01 - Hold On.mp3', '02 - Freedom.mp3', '03 - Fire.mp3'])
discs.append({'id': 'nas2', 'artista': '2', 'any': '2013', 'titol': 'How We Run', 'fonts': DG, 'carpeta': '(2013) How We Run',
              'temes': T(['Hold On', 'Freedom', 'Fire']), 'auto': ['titol']})
# 3. no trobat a cap font i sense any: no es toca, va a l'informe
carpeta('Injected - The Truth About You (Unreleased)', ['01 - A.mp3', '02 - B.mp3', '03 - C.mp3'])
discs.append({'id': 3, 'artista': '3', 'titol': 'The Truth About You (Unreleased)', 'carpeta': 'Injected - The Truth About You (Unreleased)'})
# 4. «Varios» (cançons soltes): no es toca mai
carpeta('Varios', ['Aerosmith - Inèdit.mp3', 'Altres - Tema.mp3'])
discs.append({'id': 'nas4', 'artista': '4', 'any': '1985', 'titol': 'Varios', 'fonts': DG, 'carpeta': 'Varios'})
# 5. carpeta amb format i fmt_m ja posat, però arxius sense format (copiats després)
carpeta('Rose Tattoo - 1981 - Assault & Battery', ['01 Out Of This Place.mp3', '02 All The Lessons.mp3', '03 Let It Go.mp3'])
discs.append({'id': 5, 'artista': '5', 'any': '1981', 'titol': 'Assault & Battery', 'fonts': DG,
              'carpeta': 'Rose Tattoo - 1981 - Assault & Battery', 'fmt_v': 2,
              'fmt_m': os.stat(os.path.join(nas, 'Rose Tattoo - 1981 - Assault & Battery')).st_mtime})
# 6. disc copiat de nou amb la mateixa qualitat (la nova és a ignorats): la nova a la paperera; la vella es queda i,
#    com que el programa va corregir l'artista amb Discogs, passa a «Endino's Earthworm - ...»
carpeta("Jack Endino - 1992 - Endino's Earthworm", [f"Jack Endino - Endino's Earthworm - {i + 1:02d} - {t}.mp3" for i, t in enumerate(TEMES_EE)], 1000)
carpeta("1992 - Endino's Earthworm", [f'{i + 1:02d} - {t}.mp3' for i, t in enumerate(TEMES_EE)], 1010)
discs.append({'id': 6, 'artista': '6', 'any': '1992', 'titol': "Endino's Earthworm", 'fonts': DG, 'artista_abans': 'Jack Endino',
              'auto': ['artista'], 'carpeta': "Jack Endino - 1992 - Endino's Earthworm", 'temes': T(TEMES_EE)})
# 7. disc copiat de nou amb més qualitat: la vella a la paperera i la nova agafa el nom i el format
carpeta('Jack Endino - 2005 - Permanent Fatal Error', [f'Jack Endino - Permanent Fatal Error - {i + 1:02d} - {t}.mp3' for i, t in enumerate(TEMES_PFE)], 600)
carpeta('Jack Endino - Permanent Fatal Error (2005) CD MP3 320', [f'{i + 1:02d} {t}.mp3' for i, t in enumerate(TEMES_PFE)], 1000)
discs.append({'id': 7, 'artista': '7', 'any': '2005', 'titol': 'Permanent Fatal Error', 'fonts': DG,
              'carpeta': 'Jack Endino - 2005 - Permanent Fatal Error', 'temes': T(TEMES_PFE)})
# 8. grup amb «The»
carpeta('Handwritten', ['01 - 45.mp3', '02 - Handwritten.mp3', '03 - Here Comes My Man.mp3'])
discs.append({'id': 'nas8', 'artista': '8', 'any': '2012', 'titol': 'Handwritten', 'fonts': DG, 'carpeta': 'Handwritten'})
# 9. control: carpeta i arxius ja bé: no s'ha de tocar res
bons = ['Kiss - Destroyer - 01 - Detroit Rock City.mp3', 'Kiss - Destroyer - 02 - King Of The Night Time World.mp3']
carpeta('Kiss - 1976 - Destroyer', bons)
discs.append({'id': 9, 'artista': '9', 'any': '1976', 'titol': 'Destroyer', 'fonts': DG, 'carpeta': 'Kiss - 1976 - Destroyer'})
# 10. arxius sense número de pista: no es poden formatar, van a l'informe (i res peta)
carpeta('Nobody - 2000 - Sense Números', ['Primer.mp3', 'Segon.mp3'])
discs.append({'id': 10, 'artista': '10', 'any': '2000', 'titol': 'Sense Números', 'fonts': DG, 'carpeta': 'Nobody - 2000 - Sense Números'})

json.dump(discs, open(os.path.join(tmp, 'discs.json'), 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(artistes, open(os.path.join(tmp, 'artistes.json'), 'w', encoding='utf-8'), ensure_ascii=False)
json.dump({'artistes': [], 'discos': [], 'carpetes': ["1992 - Endino's Earthworm", 'Jack Endino - Permanent Fatal Error (2005) CD MP3 320']},
          open(os.path.join(tmp, 'ignorats.json'), 'w', encoding='utf-8'), ensure_ascii=False)
json.dump({'the_arxius': '2026-11-14'}, open(os.path.join(tmp, 'migracions.json'), 'w', encoding='utf-8'))

C.formata_tots()
C.formata_tots()        # una segona passada no ha de canviar res més
D = {str(d['id']): d for d in C.llegeix('discs.json', [])}
ara = set(os.listdir(nas))
paperera = [x for x in ara if x.startswith('.Paperera')]
dins_paperera = set(os.listdir(os.path.join(nas, paperera[0]))) if paperera else set()
informe = open(os.path.join(tmp, 'format_nas_informe.txt'), encoding='utf-8').read()
ok = True


def comprova(nom, cond):
    global ok
    ok &= bool(cond)
    print(('OK     ' if cond else 'FALLA  ') + nom)


def arxius(c):
    return sorted(os.listdir(os.path.join(nas, c)))


c1 = 'Murder City Devils - 1998 - Empty Bottles, Broken Hearts'
comprova('1. carpeta sense marca reanomenada: ' + c1, D['nas1']['carpeta'] == c1 and c1 in ara)
comprova('1. arxius amb format', c1 in ara and arxius(c1)[0] == 'Murder City Devils - Empty Bottles, Broken Hearts - 01 - I Want A Lot Now (So Come On).mp3')
comprova('2. «(2013) How We Run» -> «Before Cars - 2013 - How We Run»', D['nas2']['carpeta'] == 'Before Cars - 2013 - How We Run')
comprova('3. disc no trobat: no es toca i surt a l\'informe', D['3']['carpeta'] in ara and 'Injected - The Truth About You' in informe)
comprova('4. «Varios» no es toca', 'Varios' in ara and D['nas4']['carpeta'] == 'Varios' and 'Varios' not in informe)
comprova('5. arxius copiats després a una carpeta ja formatada: formatats',
         arxius('Rose Tattoo - 1981 - Assault & Battery')[0] == 'Rose Tattoo - Assault & Battery - 01 - Out Of This Place.mp3')
c6 = "Endino's Earthworm - 1992 - Endino's Earthworm"
comprova('6. còpia repetida a la paperera i carpeta amb l\'artista corregit: ' + c6,
         D['6']['carpeta'] == c6 and c6 in ara and "1992 - Endino's Earthworm" in dins_paperera
         and arxius(c6)[0].startswith("Endino's Earthworm - Endino's Earthworm - 01 - "))
c7 = 'Jack Endino - 2005 - Permanent Fatal Error'
comprova('7. es queda la còpia de més qualitat, amb el nom i el format',
         D['7']['carpeta'] == c7 and c7 in ara and 'Jack Endino - 2005 - Permanent Fatal Error' in dins_paperera
         and arxius(c7)[0] == 'Jack Endino - Permanent Fatal Error - 01 - Count Me Out.mp3'
         and os.path.getsize(os.path.join(nas, c7, arxius(c7)[0])) == 1000)
comprova('8. grup amb «The»: «Gaslight Anthem, The - 2012 - Handwritten» i arxius «The Gaslight Anthem - …»',
         D['nas8']['carpeta'] == 'Gaslight Anthem, The - 2012 - Handwritten'
         and arxius('Gaslight Anthem, The - 2012 - Handwritten')[0] == 'The Gaslight Anthem - Handwritten - 01 - 45.mp3')
comprova('9. el que ja estava bé no es toca', arxius('Kiss - 1976 - Destroyer') == bons and D['9']['carpeta'] == 'Kiss - 1976 - Destroyer')
comprova('10. arxius sense número: a l\'informe', 'Nobody - 2000 - Sense Números' in informe)
ig = C.llegeix('ignorats.json', {})
comprova('les carpetes ignorades que ja s\'han resolt surten de la llista', not ig.get('carpetes'))
# 11. desar una fitxa des de la pàgina no esborra les marques del programa (causa del 17/11/2026)
vell = {'id': 1, 'titol': 'X', 'ident_temes': True, 'dg_ok': True, 'classificacio': '7'}
nou = comu.conserva_interns(vell, {'id': 1, 'titol': 'X', 'classificacio': '8'})
comprova('11. desar des de la pàgina conserva les marques internes', nou.get('ident_temes') and nou.get('dg_ok') and nou['classificacio'] == '8')
import re as _re
pag = open(os.path.join(sys.argv[1], 'web', 'index.html'), encoding='utf-8').read()
camps = set(_re.findall(r"\['(\w+)',", _re.search(r'const FIELDS = (\[.*?\]);', pag).group(1)))
comprova('11. tots els camps del formulari són a comu.CAMPS_PAGINA', camps and camps <= comu.CAMPS_PAGINA)
print('\nInforme:\n' + informe)
print('TOT OK' if ok else 'HI HA FALLADES: no s\'instal·la')
