@echo off
rem Completa ara: discos nous del NAS, Discogs i una tanda de discos. Pots tancar-la quan vulguis.
cd /d "%~dp0"
python "%~dp0app\completar.py" --mode nit
echo.
echo Fet. Pots tancar aquesta finestra.
pause
