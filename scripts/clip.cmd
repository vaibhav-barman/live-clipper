@echo off
rem Hands-off from cmd.exe:  clip <link> [--clips 5] [--out C:\folder]   (Windows twin of scripts/clip)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0clip.ps1" %*
