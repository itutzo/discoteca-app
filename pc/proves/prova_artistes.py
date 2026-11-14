# -*- coding: utf-8 -*-
"""Prova tancada (còpia de les dades; no toca res de veritat): un grup que ja tens no es crea de nou si arriba escrit
diferent, i es queda el nom de la portada que ja hi tens (norma 14/11/2026, «Million $ Reload»).
Ús: python prova_artistes.py <carpeta del codi>"""
import sys, os, json, shutil, tempfile, itertools
CODI = sys.argv[1]
REAL = r'C:\Users\Usuario\Dropbox\Personal\Discoteca\dades'
tmp = tempfile.mkdtemp(prefix='art_')
shutil.copy2(os.path.join(REAL, 'artistes.json'), os.path.join(tmp, 'artistes.json'))
sys.path.insert(0, CODI)
import comu
comu.DADES, comu.CARATULES, comu.COPIES, comu.REGISTRE = tmp, tmp, os.path.join(tmp, 'c'), os.path.join(tmp, 'r.txt')
os.makedirs(comu.COPIES)
import completar as C

SI = [("Million Dollar Reload", "Million $ Reload"), ("MILLION$ RELOAD", "Million $ Reload"), ("Kesha", "Ke$ha"),
      ("Guns And Roses", "Guns N' Roses"), ("Puddle of Mudd", "Puddle Of Mud"), ("Travis Warren", "Travis T. Warren"),
      ("Three Doors Down", "3 Doors Down"), ("Doctor Feelgood", "Dr. Feelgood"), ("Pearls And Brass", "Pearls & Brass"),
      ("The Beatles", "Beatles, The"), ("Motley Crue", "Mötley Crüe")]
NO = [("Bryan Adams", "Ryan Adams"), ("Deerhunter", "Dear Hunter, The"), ("Generation X", "D Generation"),
      ("Architect", "Architects"), ("Dirty Loops", "Dirty Looks"), ("Heart Attack", "Heart Attacks, The"),
      ("Earth", "Earth, Wind & Fire"), ("The Spits", "Spitz")]
mal = 0
for a, b in SI:
    r = comu.mateix_artista(a, b); mal += not r
    print(('OK    ' if r else 'MIRAR ') + f'mateix grup: «{a}» = «{b}»')
for a, b in NO:
    r = comu.mateix_artista(a, b); mal += r
    print(('OK    ' if not r else 'MIRAR ') + f'grups diferents: «{a}» no és «{b}»')

art = comu.llegeix('artistes.json', {})
proves = {k: v for k, v in art.items() if comu.N(v) != comu.N('Million Dollar Reload')}   # com abans del 14/11
proves.setdefault('1341', 'Million $ Reload')
k = C.id_artista('Million Dollar Reload', proves)
nom = proves.get(k)
ok = nom == 'Million $ Reload'
mal += not ok
print(('OK    ' if ok else 'MIRAR ') + f'carpeta nova «Million Dollar Reload» va al grup «{nom}»')
k = C.id_artista('Grup Que No Tinc', proves)
ok = proves.get(k) == 'Grup Que No Tinc'
mal += not ok
print(('OK    ' if ok else 'MIRAR ') + 'un grup nou de debò es crea com a grup nou')

# cap parella d'artistes diferents de la teva discoteca no s'ha de confondre més enllà de les que es veuen aquí
idx = {}
for v in art.values():
    for c in comu.claus_nom(v):
        idx.setdefault(c, set()).add(v)
par = sorted({p for s in idx.values() for p in itertools.combinations(sorted(s), 2) if comu.N(p[0]) != comu.N(p[1])})
print(f'\nGrups que tens repetits amb el nom escrit diferent ({len(par)}): revisar-los a mà')
for p in par:
    print('      «%s» = «%s»' % p)
print('\nTOT BÉ' if not mal else f'\n{mal} CASOS PER MIRAR')
sys.exit(1 if mal else 0)
