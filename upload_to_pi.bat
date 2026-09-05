@echo off
setlocal

set SRC=%~dp0
set STAGE=%~dp0..\orion-llm-upload-stage
set PI_USER=rpi
set PI_HOST=192.168.109.178
set PI_DEST=/home/rpi/orion-llm/

echo Staging a clean copy (excluding models, __pycache__, .git)...
robocopy "%SRC%." "%STAGE%\." /E /XD models __pycache__ .git /NFL /NDL /NJH /NJS

echo Uploading Orion codebase to Raspberry Pi 5 (%PI_USER%@%PI_HOST%)...
scp -r "%STAGE%\*" %PI_USER%@%PI_HOST%:%PI_DEST%

echo Upload completed successfully!
echo (models/ was skipped - transfer that separately if needed)
pause