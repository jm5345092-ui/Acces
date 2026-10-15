@echo off
rem Compila la app de una carpeta de trabajo (jobs\<slug>).
rem Uso: build.cmd "C:\xampp\htdocs\pruebas\jobs\mi_tienda"
setlocal EnableExtensions
set "JOB=%~1"
if "%JOB%"=="" (
    echo Falta la carpeta del job.
    exit /b 1
)
if not exist "%JOB%\env.cmd" (
    echo No existe %JOB%\env.cmd
    exit /b 1
)
call :main >> "%JOB%\build.log" 2>&1
exit /b %ERRORLEVEL%

:main
call "%JOB%\env.cmd"
set "PATH=%JAVA_HOME%\bin;%PATH%"
set "PROJECT=%JOB%\project"
set "RES=%PROJECT%\app\src\main\res"
echo RUNNING> "%JOB%\status.txt"
echo Inicio %DATE% %TIME%
echo.
echo [1/3] Generando iconos...
java -Djava.awt.headless=true "%TOOLS_DIR%\IconGen.java" "%ICON_FILE%" "%RES%" "%APP_COLOR%"
if errorlevel 1 goto :fail
echo.
echo [2/3] Compilando APK con Gradle (la primera vez puede tardar varios minutos)...
call "%GRADLE_BIN%" -p "%PROJECT%" assembleRelease --console=plain
if errorlevel 1 goto :fail
echo.
echo [3/3] Copiando APK...
copy /Y "%PROJECT%\app\build\outputs\apk\release\app-release.apk" "%APK_OUT%"
if errorlevel 1 goto :fail
echo DONE> "%JOB%\status.txt"
echo.
echo LISTO %DATE% %TIME%
exit /b 0

:fail
echo ERROR> "%JOB%\status.txt"
echo.
echo FALLO %DATE% %TIME%
exit /b 1
