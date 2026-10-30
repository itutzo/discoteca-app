# -*- coding: utf-8 -*-
"""Eines de configuració: obrir les claus i programar la tasca nocturna."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comu

APP = os.path.dirname(os.path.abspath(__file__))


def claus():
    comu.config()                      # crea l'arxiu si no existeix
    subprocess.Popen(['notepad.exe', comu.CONFIG])
    print('Arxiu de configuració:', comu.CONFIG)


def programar(hora='14:30'):
    pyw = sys.executable.replace('python.exe', 'pythonw.exe')
    if not os.path.exists(pyw):
        pyw = sys.executable
    script = os.path.join(APP, 'completar.py')
    ps = (
        f"$a = New-ScheduledTaskAction -Execute '{pyw}' -Argument '\"{script}\" --mode nit' -WorkingDirectory '{APP}';"
        f"$t = New-ScheduledTaskTrigger -Daily -At '{hora}';"
        "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 4);"
        "Register-ScheduledTask -TaskName 'Discoteca - completar' -Action $a -Trigger $t -Settings $s -Force | Out-Null"
    )
    r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps], capture_output=True, text=True,
                       creationflags=0x08000000 if os.name == 'nt' else 0)   # sense finestra
    if r.returncode == 0:
        print(f'Tasca programada: cada dia a les {hora}. Si el PC està apagat a aquella hora, s\'executarà quan l\'encenguis.')
    else:
        print('No s\'ha pogut programar la tasca:', r.stderr or r.stdout)


def acces_directe():
    pyw = sys.executable.replace('python.exe', 'pythonw.exe')
    if not os.path.exists(pyw):
        pyw = sys.executable
    ps = (
        "$d = [Environment]::GetFolderPath('Desktop');"
        "$w = New-Object -ComObject WScript.Shell;"
        "$s = $w.CreateShortcut((Join-Path $d 'Discoteca.lnk'));"
        f"$s.TargetPath = '{pyw}';"
        f"$s.Arguments = '\"{os.path.join(APP, 'servidor.py')}\"';"
        f"$s.WorkingDirectory = '{APP}';"
        f"$s.IconLocation = '{os.path.join(APP, 'vinil.ico')},0';"
        "$s.Description = 'Obre la Discoteca';"
        "$s.Save(); Write-Output $d"
    )
    r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', ps], capture_output=True, text=True)
    if r.returncode == 0:
        print('Accés directe «Discoteca» creat a:', r.stdout.strip())
    else:
        print('No s\'ha pogut crear l\'accés directe:', r.stderr or r.stdout)


def desprogramar():
    r = subprocess.run(['schtasks', '/Delete', '/F', '/TN', 'Discoteca - completar'], capture_output=True, text=True)
    print('Tasca eliminada.' if r.returncode == 0 else (r.stderr or r.stdout))


if __name__ == '__main__':
    {'claus': claus, 'programar': programar, 'desprogramar': desprogramar, 'acces': acces_directe}[sys.argv[1]](*sys.argv[2:])
