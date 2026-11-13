import sys, os, tempfile
sys.path.insert(0, sys.argv[1])
import comu
tmp = tempfile.mkdtemp(prefix='any_')
comu.DADES = comu.CARATULES = tmp; comu.REGISTRE = os.path.join(tmp, 'r.txt')
import completar as C
CASOS = [("Magpie Salute, the 2017 - The magpipe Salute  FLAC", {'any': '2017', 'titol': 'The Magpie Salute', 'titol_abans': 'The magpipe Salute'}, "Magpie Salute, the - 2017 - The Magpie Salute"),
         ("'77 - High Decibels", {'any': '2011', 'titol': 'High Decibels'}, "'77 - 2011 - High Decibels"),
         ("Dag Nasty - Dag With Shawn (2010)", {'any': '2010', 'titol': 'Dag With Shawn'}, "Dag Nasty - 2010 - Dag With Shawn"),
         ("Rufio - MCMLXXXV (1985)", {"any": "2003", "titol": "MCMLXXXV"}, "Rufio - 2003 - MCMLXXXV (1985)"),
         ("[1981] Rose Tattoo - Assault & Battery", {'any': '1981', 'titol': 'Assault & Battery'}, "Rose Tattoo - 1981 - Assault & Battery"),
         ("Thelonious Monster - Beautiful Mess", {'any': '1992', 'titol': 'Beautiful Mess'}, "Thelonious Monster - 1992 - Beautiful Mess"),
         ("Brides of Destruction - Here Come the Brides", {'any': '2004', 'titol': 'Here Come the Brides'}, "Brides of Destruction - 2004 - Here Come The Brides"),
         ("Blink-182 - Enema Of The State 320", {'any': '1999', 'titol': 'Enema Of The State'}, "Blink-182 - 1999 - Enema Of The State")]
for c, d, esperat in CASOS:
    os.makedirs(os.path.join(tmp, 'nas', c)); d['carpeta'] = c
    C.posa_any_carpeta(d, os.path.join(tmp, 'nas'))
    print(('OK   ' if esperat is None or d['carpeta'] == esperat else 'MIRAR ') + c + '  ->  ' + d['carpeta'])
