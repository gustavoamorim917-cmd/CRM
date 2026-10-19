@echo off
cd /d "%~dp0"
if not exist "%~dp0INICIAR_APP.ps1" (
  echo.
  echo ERRO: Arquivos do app nao foram encontrados.
  echo.
  echo Voce provavelmente abriu o INICIAR_APP.bat direto de dentro do arquivo ZIP.
  echo Primeiro clique com o botao direito no ZIP e escolha "Extrair Tudo".
  echo Depois abra a pasta extraida "sp_integrado" e execute este arquivo novamente.
  echo.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0INICIAR_APP.ps1"
if errorlevel 1 pause
pause
