# Discoteca: context per a Claude

Catàleg personal de discos de l'Ignasi (uns 3.000 enregistraments en MP3, CD i vinil). Substitueix una base de dades d'Access antiga, que es conserva com a còpia de seguretat i **no s'ha de tocar**.

Respon sempre en **català**. Quan donis instruccions de l'app d'escriptori de Claude, fes servir els noms en castellà dels menús i dels botons. Quan siguin del Windows, fes servir els noms en català.

## Parts del projecte

| Carpeta | Què és | On viu |
|---|---|---|
| `pc/` | App local en Python (només la biblioteca estàndard, més `curl_cffi`, `beautifulsoup4` i `playwright`) | `C:\Users\Usuario\Dropbox\Personal\Discoteca\` al PC de l'Ignasi |
| `mobil/` | Versió web per a iPhone i iPad, que llegeix i escriu directament al Dropbox | Publicada a https://itutzo.github.io/discoteca/ (repositori **públic** `itutzo/discoteca`, GitHub Pages) |

En aquest repositori **no** hi ha dades, caràtules ni claus. Les dades són a `Dropbox\Personal\Discoteca\dades\` i les caràtules a `...\caratules\<id>.jpg`.

### PC (`pc/app`)
- `servidor.py`: servidor HTTP a `127.0.0.1:8800`, només local. Comprova la capçalera Host (contra el DNS rebinding) i l'Origin i el Sec-Fetch-Site als POST. En arrencar, torna a registrar la tasca programada amb la ruta actual de la carpeta.
- `completar.py`: completa dades automàticament. Té els modes `nit` (el de la tasca diària de les 14:30), `tot`, `pendents`, `disc`, `discogs`, `nas`, `duplicats` i `perfil`. Cada tanda és de 300 discos com a mínim.
  - A cada execució, `tradueix_catala()` passa al català la `qualitat` i les `notes` que encara són en castellà (només valors exactes de la llista; el primer cop deixa una còpia a `dades/copies/catala-discs-abans.json`).
- `fonts.py`:
  - **AllMusic** sempre amb Playwright i el **Chrome** instal·lat (`channel='chrome'`, finestra fora de la pantalla), perquè bloqueja els altres clients.
  - **Discogs** per l'API amb token, **Last.fm** (`getsimilar`, `getinfo`, `gettoptags` i `album.getinfo` per a les durades) i **Apple Music** (HTML).
  - **MusicBrainz** (API oberta, 1 consulta per segon, User-Agent amb l'adreça del repositori) quan AllMusic no dona el disc: any, gèneres, compositors (relacions de *work*), intèrprets i caràtula de Cover Art Archive. AllMusic bloqueja l'accés automàtic des del 28/10/2026 (403): no s'ha d'intentar esquivar.
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

## Dades (`dades/`)
- `discs.json`: llista de discos. Camps principals: `id`, `artista` (és l'id que apunta a `artistes.json`), `titol`, `any`, `suport` (`"mp3, cd, lp"`), `carpeta` (nom de la carpeta al NAS), `temes` `[[n, títol, compositor, '', 0, 0]]`, `interprets`, `classificacio`, `notes`, `clasamg`, `genere`, `estil`, `segell`, `catno`, `barcode`, `edicio`, `bitrate`, `caratula`/`cv`, `estat:"pendent"`, `fonts`, `auto`, `proc`, `no_trobat`, `reintenta`, `am_error` (data en què AllMusic no va deixar consultar el disc: es torna a provar), `br`, i `nas_t`/`nas_m` (firma dels temes llegits dels noms dels arxius i data de la carpeta: si l'Ignasi canvia els arxius, els temes es tornen a llegir; si els ha corregit a l'app, la firma ja no coincideix i no es toquen).
- `artistes.json` `{id: nom}` · `recs.json` (recomanacions per artista; `v: 2` porta `urls` per font, i l'enllaç de cada recomanació obre la font de la seva etiqueta) · `lastfm.json` (etiquetes i oients) · `ignorats.json` `{artistes, discos, carpetes}`.
- `registre.txt` (a partir de 2 MB passa a `registre-anterior.txt`), `migracions.json` (canvis d'un sol cop ja fets), `estat.json`, `duplicats_informe.txt` i `discogs_informe.txt`.

## Normes de l'Ignasi (obligatòries)
- **No sobreescriure mai** cap camp que ell hagi omplert. L'automatisme només omple els camps buits. **No omplir mai** `classificacio` (la seva nota) ni `notes`.
- **Bitrate:** si és fix, el valor (`192`, `320`); si és variable, `VBR ~<mitjana>`; i `Flac`. Si els MP3 ja són al PC, es llegeix només la seva capçalera (uns pocs kB: bitrate fix o mitjana VBR exacta). Si són «a demanda» (atributs de Windows OFFLINE/RECALL), **no s'obren ni es descarreguen** (el NAS és Synology on-demand): es calcula la mida dels arxius dividida per la durada dels temes (AllMusic, Discogs, MusicBrainz i, si no n'hi ha, Last.fm `album.getinfo`). El camp `br: 3` marca els discos ja provats amb aquest mètode.
- **NAS:** `C:\SynologyMusic\Mi Musica`, amb carpetes de nom «Artista - Any - Àlbum». Si una carpeta es reanomena, el disc antic l'adopta. Les carpetes esborrades es guarden a `ignorats.carpetes`.
- **Duplicats:** es queda una sola entrada, la que té més fonts d'internet i més dades, i fusiona els camps de l'usuari. Els noms bons són els de la carpeta que existeix al NAS.
- Només **Chrome**, mai Edge.
- Mai demanar ni mostrar els tokens. L'App key de Dropbox no és secreta.
- `Dropbox\Fotos` s'ha de quedar només al núvol.
- Abans de lliurar qualsevol document, netejar-ne les metadades.

## Com es desplega
- **PC:** amb el pont cap al PC (escriptori de Claude enllaçat), copiar els arxius a `C:\Users\Usuario\Dropbox\Personal\Discoteca\app\`. Els canvis al servidor necessiten **Eines → Tanca la Discoteca** i tornar-la a obrir; els canvis a la pàgina, **Ctrl+F5**.
- **Mòbil:** copiar `mobil/*` a l'arrel del repositori `itutzo/discoteca` i fer push a `main`. GitHub Pages ho publica en un parell de minuts.
- Per fer canvis a les dades des de fora del PC, val més escriure arxius a `dades/mobil/` que no pas editar `discs.json` directament.
