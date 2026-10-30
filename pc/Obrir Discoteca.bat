@echo off
rem Obre la Discoteca al navegador. Deixa aquesta finestra minimitzada mentre la fas servir.
cd /d "%~dp0"
start "Discoteca" /min python "%~dp0app\servidor.py"
