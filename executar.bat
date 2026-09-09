@echo off
cd /d "%~dp0"
echo ======================================================
echo Atualizando mural: CasadosMotoresCMEMobi
echo ======================================================

echo 1. Baixando fotos e videos do Instagram...
python baixar_mural.py

echo.
echo 2. Enviando para o repositorio GitHub...
git add -A

git diff-index --quiet HEAD || git commit -m "Atualizacao automatica mural CasadosMotoresCMEMobi"
git push origin main

echo.
echo Concluido!