@echo off
title Create Desktop Shortcut - Client PDF Unlocker
cd /d "%~dp0"

echo Creating Desktop shortcut for Client PDF Unlocker...

set SCRIPT="%TEMP%\CreateShortcut_%RANDOM%.vbs"
set TARGET=%~dp0run_app.bat
set WORKDIR=%~dp0
set SHORTCUT=%USERPROFILE%\Desktop\Client PDF Unlocker.lnk

echo Set oWS = WScript.CreateObject("WScript.Shell") > %SCRIPT%
echo sLinkFile = "%SHORTCUT%" >> %SCRIPT%
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> %SCRIPT%
echo oLink.TargetPath = "%TARGET%" >> %SCRIPT%
echo oLink.WorkingDirectory = "%WORKDIR%" >> %SCRIPT%
echo oLink.Description = "Client PDF Unlocker Internal Tool" >> %SCRIPT%
echo oLink.WindowStyle = 1 >> %SCRIPT%
echo oLink.Save >> %SCRIPT%

cscript /nologo %SCRIPT%
del %SCRIPT%

echo.
echo [SUCCESS] Shortcut created on your Desktop: "Client PDF Unlocker"
echo You can now launch the app directly from your Desktop anytime!
echo.
pause
