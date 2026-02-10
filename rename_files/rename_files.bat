@echo off

:start
set /p "folderPath=Enter folder path: "

rem Remove any surrounding quotes
set "folderPath=%folderPath:"=%"

if not exist "%folderPath%" (
    echo Folder not found.
    pause
    exit /b
)

:menu
echo.
echo What do you want to do?
echo - clean   : make lowercase, replace spaces/underscores with hyphens, remove special characters
echo - add     : add text before and/or after filenames
echo - rename  : find and replace text in filenames (leave replacement blank to remove)
echo.
set /p "action=Enter action: "

if /i "%action%"=="clean" goto doClean
if /i "%action%"=="add" goto doadd
if /i "%action%"=="rename" goto doRename

echo Invalid action.
pause
exit /b

:doClean
powershell -ExecutionPolicy Bypass -Command "$files = @(Get-ChildItem -LiteralPath '%folderPath%' -File); foreach ($f in $files) { $newName = $f.Name.ToLower(); $newName = $newName -replace '[ _&]', '-'; $newName = $newName -replace '[?!/%%$#@*]', ''; $newName = $newName -replace '-+', '-'; $base = [IO.Path]::GetFileNameWithoutExtension($newName).Trim('-'); $ext = [IO.Path]::GetExtension($newName); $newName = $base + $ext; if ($f.Name -ne $newName) { Write-Host ('Renaming: ' + $f.Name + ' -> ' + $newName); Rename-Item -LiteralPath $f.FullName -NewName $newName } }"
goto done

:doadd
echo.
echo Where do you want to add text?
echo - before
echo - after
echo - both
echo.
set /p "choice=Enter choice: "

set "prefix="
set "suffix="

if /i "%choice%"=="before" goto getBefore
if /i "%choice%"=="after" goto getAfter
if /i "%choice%"=="both" goto getBoth

echo Invalid choice.
pause
exit /b

:getAfter
set /p "suffix=Enter text to add after: "
goto doaddRename

:getBefore
set /p "prefix=Enter text to add before: "
goto doaddRename

:getBoth
set /p "prefix=Enter text to add before: "
set /p "suffix=Enter text to add after: "
goto doaddRename

:doaddRename
powershell -ExecutionPolicy Bypass -Command "$files = @(Get-ChildItem -LiteralPath '%folderPath%' -File); foreach ($f in $files) { $base = [IO.Path]::GetFileNameWithoutExtension($f.Name); $ext = [IO.Path]::GetExtension($f.Name); $newName = '%prefix%' + $base + '%suffix%' + $ext; if ($f.Name -ne $newName) { Write-Host ('Renaming: ' + $f.Name + ' -> ' + $newName); Rename-Item -LiteralPath $f.FullName -NewName $newName } }"
goto done

:doRename
echo.
echo Enter the text you want to find in filenames.
echo.
set /p "findText=Text to find: "

echo.
echo Enter replacement text (leave blank to remove).
echo.
set "replaceText="
set /p "replaceText=Replace with: "

powershell -ExecutionPolicy Bypass -Command "$files = @(Get-ChildItem -LiteralPath '%folderPath%' -File); foreach ($f in $files) { $base = [IO.Path]::GetFileNameWithoutExtension($f.Name); $ext = [IO.Path]::GetExtension($f.Name); $newBase = $base -replace [regex]::Escape('%findText%'), '%replaceText%'; $newName = $newBase + $ext; if ($f.Name -ne $newName) { Write-Host ('Renaming: ' + $f.Name + ' -> ' + $newName); Rename-Item -LiteralPath $f.FullName -NewName $newName } }"
goto done

:done
echo.
echo Done.
echo.
set /p "again=Do anything else? (y/n): "
if /i "%again%"=="y" goto menu
exit /b