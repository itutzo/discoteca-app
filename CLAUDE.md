# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Discoteca: context per a Claude

Catàleg personal de discos de l'Ignasi (uns 3.000 enregistraments en MP3, CD i vinil). Substitueix una base de dades d'Access antiga, que es conserva com a còpia de seguretat i **no s'ha de tocar**.

Respon sempre en **català**. Quan donis instruccions de l'app d'escriptori de Claude, fes servir els noms en castellà dels menús i dels botons. Quan siguin del Windows, fes servir els noms en català.

## Parts del projecte

| Carpeta | Què és | On viu |
|---|---|---|
| `pc/` | App local en Python (només la biblioteca estàndard, més `curl_cffi`, `beautifulsoup4`, `playwright`, `numpy` i `av`) | `C:\Users\Usuario\Dropbox\Personal\Discoteca\` al PC de l'Ignasi |
| `mobil/` | Versió web per a iPhone i iPad, que llegeix i escriu directament al Dropbox | Publicada a https://itutzo.github.io/discoteca/ (repositori **públic** `itutzo/discoteca`, GitHub Pages) |

En aquest repositori **no** hi ha dades, caràtules ni claus. Les dades són a `Dropbox\Personal\Discoteca\dades\` i les caràtules a `...\caratules\<id>.jpg`.

### PC (`pc/app`)
- `servidor.py`: servidor HTTP a `127.0.0.1:8800`, només local. Comprova la capçalera Host (contra el DNS rebinding) i l'Origin i el Sec-Fetch-Site als POST. En arrencar, torna a registrar la tasca programada amb la ruta actual de la carpeta.
- `completar.py`: completa dades automàticament. Té els modes `nit` (el de la tasca diària de les 14:30), `tot`, `pendents`, `disc` (amb `--id`), `discogs`, `nas`, `duplicats`, `perfil`, `so`, `destacats` i `reanomena` (només reanomena carpetes i arxius després d'un canvi de títol fet a mà). Cada tanda és de 300 discos com a mínim (`--n`). La pàgina el llança com a procés separat amb `POST /api/completa?mode=…` (un sol procés alhora).
  - `main()` fa cada pas (canvis del mòbil, català, bitrate, NAS, Discogs, duplicats, noms i format del NAS, títols, discos dobles, tanda, perfil, so) en un `try` propi: si un falla, els altres continuen. Un pas nou s'hi ha d'afegir igual.
  - A cada execució, `tradueix_catala()` passa al català la `qualitat` i les `notes` que encara són en castellà (només valors exactes de la llista; el primer cop deixa una còpia a `dades/copies/catala-discs-abans.json`).
- `fonts.py`:
  - **AllMusic** sempre amb Playwright i el **Chrome** instal·lat (`channel='chrome'`, finestra fora de la pantalla), perquè bloqueja els altres clients.
  - **Discogs** per l'API amb token, **Last.fm** (`getsimilar`, `getinfo`, `gettoptags` i `album.getinfo` per a les durades) i **Apple Music** (HTML).
  - **MusicBrainz** (API oberta, 1 consulta per segon, User-Agent amb l'adreça del repositori) quan AllMusic no dona el disc: any, gèneres, compositors (relacions de *work*), intèrprets i caràtula de Cover Art Archive. AllMusic bloqueja l'accés automàtic des del 28/10/2026 (403): no s'ha d'intentar esquivar.
- `so.py`: el so dels discos per als similars. Mostres de 30 s d'Apple Music (iTunes Search API, `search` + `lookup`, 3 temes per disc, 3,1 s entre consultes), descodificades amb PyAV i analitzades amb numpy (37 mesures: MFCC, brillantor, greus/aguts, dinàmica, tempo). Es desa a `dades/so.json` (`{id: {v, n, d, u, ver}}` o `{no: data}`, es torna a provar al cap de 120 dies). numpy i av s'instal·len sols amb pip `--user`. Mode `so` (botó **Eines → Escolta el so dels discos**), i també a `nit`, `tot` i `disc` (300 discos per tanda, màxim 90 minuts). **Mai** s'obren els MP3 del NAS per a això.
- `comu.py`:
  - Rutes i configuració (`%USERPROFILE%\.discoteca\config.ini`, **fora** de Dropbox, amb els tokens de Discogs i Last.fm).
  - Escriptura atòmica amb reintents, perquè Dropbox bloqueja arxius, i còpies diàries a `dades/copies`.
  - `aplica_canvis_mobil()`, que incorpora els arxius `dades/mobil/*.json`.
- `eines.py`: obre la configuració, programa la tasca (`Discoteca - completar`, cada dia a les 14:30, StartWhenAvailable) i crea l'accés directe amb `vinil.ico`.
- `web/index.html`: la interfície. És la mateixa que la del mòbil, però sense la capa de Dropbox.

### Mòbil (`mobil/index.html`)
- Entra amb Dropbox per OAuth PKCE (App key `eym3tcbw043ubzr`, que és pública, amb refresh token guardat a localStorage).
- Llegeix `/Personal/Discoteca/dades/*.json` i les miniatures amb `get_thumbnail_batch`.
- Els canvis es desen com a arxius `dades/mobil/<ts>-<rand>.json` de tipus `disc` (amb `patch`; el valor `null` esborra el camp), `esborra`, `artista` o `ignora`. El PC els incorpora.
- Té una CSP que limita les connexions a Dropbox, MusicBrainz, Wikidata i la Wikipedia. Si s'afegeix una font nova, cal afegir-la al `connect-src`.
- Les caselles del formulari no fan servir l'autoemplenat del navegador: proposen suggeriments en català (`SUGG`) i, per a gènere i estil, els valors del catàleg.
- **La interfície està duplicada**: qualsevol canvi a `pc/app/web/index.html` s'ha d'aplicar també a `mobil/index.html`, i al revés.

## Ordres

No hi ha proves automàtiques, linter ni compilació. Per comprovar el Python abans de pujar-lo:

```bash
python3 -m py_compile pc/app/*.py
```

Per executar-lo (pensat per al Windows de l'Ignasi; aquí, sense dades, NAS ni claus, gairebé res fa feina real):

```bash
python pc/app/completar.py --mode nit            # el mateix que fa "Completar ara.bat"
python pc/app/completar.py --mode disc --id <id>  # un sol disc
python pc/app/servidor.py                         # obre http://localhost:8800/
```

`comu.py` calcula l'arrel de les dades com la carpeta pare d'`app/` (`ARREL`) i, només d'importar-lo, crea `dades/`, `caratules/` i `dades/copies/` al costat de `pc/app` (estan al `.gitignore`), i `~/.discoteca/config.ini` amb la plantilla buida. Els `.bat` de `pc/` són les dreceres de l'Ignasi per a aquestes mateixes ordres.

## Dades (`dades/`)
- `discs.json`: llista de discos. Camps principals: `id`, `artista` (és l'id que apunta a `artistes.json`), `titol`, `any`, `suport` (`"mp3, cd, lp"`), `carpeta` (nom de la carpeta al NAS), `temes` `[[n, títol, compositor, cara/CD, bonus, inèdit, destacat]]`, `interprets`, `classificacio`, `notes`, `clasamg`, `genere`, `estil`, `segell`, `catno`, `barcode`, `edicio`, `bitrate`, `caratula`/`cv`, `estat:"pendent"`, `fonts`, `auto`, `proc`, `no_trobat`, `reintenta`, `am_error` (data en què AllMusic no va deixar consultar el disc: es torna a provar), `br`, i `nas_t`/`nas_m` (firma dels temes llegits dels noms dels arxius i data de la carpeta: si l'Ignasi canvia els arxius, els temes es tornen a llegir; si els ha corregit a l'app, la firma ja no coincideix i no es toquen).
- `so.json`: mesures del so de cada disc (vegeu `so.py`); la pàgina les normalitza (z) i compara amb el cosinus: suma `4·s` als similars i, si dos discos sonen molt diferent (s < 0), l'estil sol no els fa «relació forta».
- `artistes.json` `{id: nom}` · `recs.json` (recomanacions per artista; `v: 2` porta `urls` per font, i l'enllaç de cada recomanació obre la font de la seva etiqueta) · `lastfm.json` (etiquetes i oients) · `ignorats.json` `{artistes, discos, carpetes}`.
- `registre.txt` (a partir de 2 MB passa a `registre-anterior.txt`), `migracions.json` (canvis d'un sol cop ja fets), `estat.json`, `duplicats_informe.txt` i `discogs_informe.txt`.

## Normes de l'Ignasi (obligatòries)
- **Cada ordre que dona l'Ignasi queda com a norma per defecte del projecte**: s'ha d'anotar aquí (i a la memòria del projecte) en el mateix moment, perquè no l'hagi de repetir en una altra sessió.
- **Temes destacats (★):** quan es completen les dades automàticament, també s'hi afegeixen els temes destacats. Com que AllMusic bloqueja, es fan servir els temes més escoltats de l'artista a Last.fm (`artist.getTopTracks`): com a molt 3 per disc, els que tenen almenys el 40 % de les escoltes del més escoltat (`destaca_temes()`, camps `dst`/`dst_n`, modes `nit`, `tot`, `disc` i `destacats`). Només als discos que no en tenen cap: les estrelles de l'Ignasi no es toquen mai.
- **No sobreescriure mai** cap camp que ell hagi omplert. L'automatisme només omple els camps buits. **No omplir mai** `classificacio` (la seva nota) ni `notes`.
- **Bitrate:** si és fix, el valor (`192`, `320`); si és variable, `VBR ~<mitjana>`; i `Flac`. Si els MP3 ja són al PC, es llegeix només la seva capçalera (uns pocs kB: bitrate fix o mitjana VBR exacta). Si són «a demanda» (atributs de Windows OFFLINE/RECALL), **no s'obren ni es descarreguen** (el NAS és Synology on-demand): es calcula la mida dels arxius dividida per la durada dels temes (AllMusic, Discogs, MusicBrainz i, si no n'hi ha, Last.fm `album.getinfo`). El camp `br: 3` marca els discos ja provats amb aquest mètode.
- **NAS:** `C:\SynologyMusic\Mi Musica`, amb carpetes de nom «Artista - Any - Àlbum». Si una carpeta es reanomena, el disc antic l'adopta. També l'adopta si la carpeta s'esborra i se'n crea una altra del mateix artista amb gairebé els mateixos temes. Els arxius de cada carpeta es reanomenen al format «Artista - Àlbum - 01 - Cançó», i als discos dobles «Artista - Àlbum - Disc 2 - 01 - Cançó» (cada paraula amb majúscula; `formata_tots()`, només les carpetes noves o canviades, camps `fmt_m` i `fmt_v`), sense obrir-los. Un disc nou copiat tal com venia, sense l'any («'77 - High Decibels»), passa a «Artista - Any - Títol» quan la fitxa ja té l'any (`posa_any_carpeta()` a `formata_tots()`, que també es crida després de la tanda) i llavors se'n formaten els arxius. Si la carpeta no porta l'artista («2009 - Cycle of Pain», «In the Red») i el disc encara no té fonts, l'artista es treu de l'etiqueta ID3 dels MP3 que ja són al PC (`etiqueta_mp3()`: només l'etiqueta, mai l'àudio ni els arxius «a demanda»), el disc es torna a completar i la carpeta passa a «Artista - Any - Títol» (`artista_de_etiquetes()`, `posa_artista_carpeta()`, camp `art_id3`). Les carpetes esborrades es guarden a `ignorats.carpetes`.
- **Discos dobles (norma fixa, no cal tornar-la a demanar):**
  - Arxius: «Artista - Àlbum - Disc 2 - 01 - Cançó» (sempre «Disc N», mai «CD N»).
  - Fitxa de l'app: els temes es mostren «Disc 1 10» en una sola línia. Internament, la columna `t[3]` dels temes és la cara o el disc (`CD1`/`CD2`), i `t[6] = 1` marca un **tema destacat** (l'estrella `*` de l'Access, com els *picks* d'AllMusic; la fitxa hi posa ★). La migració `destacats` va treure les estrelles de `t[3]`. Les estrelles són de l'Ignasi: no s'han de perdre mai en reordenar o ajuntar temes.
  - **Columna de l'estrella (norma fixa):** a la llista de temes de la fitxa, la ★ va en una columna pròpia entre el número i el títol (`<span class="s">`), perquè tots els títols quedin alineats, també als discos dobles («Disc 1 10»). PC i mòbil igual.
  - Si un disc doble tenia una fitxa per CD («... - CD1», «... - CD2») i l'Ignasi n'ajunta els arxius en una sola carpeta, queda **una sola fitxa** amb els temes marcats del seu disc i ordenats per disc i número (`ajunta_discs_partits()` a `llegeix_nas()`).
- **Títols mal escrits:** un disc s'ha de trobar encara que el títol no estigui ben escrit, si s'assembla prou al de Discogs (`cerca_aprox()`): ≥70 % de semblança i ≥60 % dels temes iguals (els temes de la fitxa o, si no en té, els dels noms dels arxius de la carpeta del NAS, sense obrir-los); si l'entrada no té temes (moltes de l'Access), ≥90 % de semblança, el mateix any i un sol candidat. Llavors el títol es corregeix sol a la fitxa i a la carpeta del NAS (és l'única excepció a «no sobreescriure»).
- **Duplicats:** es queda una sola entrada, la que té més fonts d'internet i més dades, i fusiona els camps de l'usuari. Els noms bons són els de la carpeta que existeix al NAS.
- **Notes amb punt decimal (norma fixa, 04/11/2026):** la meva nota (`classificacio`) i la d'AllMusic (`clasamg`) es mostren i es desen sempre amb punt («7.5»), encara que s'escriguin amb coma. La pàgina ho fa en desar (`decimal()`, PC i mòbil) i `normalitza_notes()` a cada execució de `completar.py` passa les que ja hi ha (el primer cop deixa una còpia a `dades/copies/notes-punt-discs-abans.json`). Només es canvia la coma pel punt: la nota mai no s'omple ni es modifica d'una altra manera.
- Només **Chrome**, mai Edge.
- Mai demanar ni mostrar els tokens. L'App key de Dropbox no és secreta.
- `Dropbox\Fotos` s'ha de quedar només al núvol.
- Abans de lliurar qualsevol document, netejar-ne les metadades.

## Com es desplega
- **PC:** amb el pont cap al PC (escriptori de Claude enllaçat), copiar els arxius a `C:\Users\Usuario\Dropbox\Personal\Discoteca\app\`. Els canvis al servidor necessiten **Eines → Tanca la Discoteca** i tornar-la a obrir; els canvis a la pàgina, **Ctrl+F5**.
- **Mòbil:** copiar `mobil/*` a l'arrel del repositori `itutzo/discoteca` i fer push a `main`. GitHub Pages ho publica en un parell de minuts.
- Per fer canvis a les dades des de fora del PC, val més escriure arxius a `dades/mobil/` que no pas editar `discs.json` directament.
