# rename_files.ps1
# Right-click > Run with PowerShell, or: powershell -ExecutionPolicy Bypass -File rename_files.ps1

function Get-FolderPath {
    while ($true) {
        $path = Read-Host "Enter folder path"
        $path = $path.Trim('"')
        if (Test-Path $path) { return $path }
        Write-Host "Folder not found. Try again." -ForegroundColor Red
    }
}

function Invoke-Clean($folder) {
    $files = @(Get-ChildItem -LiteralPath $folder -File)
    foreach ($f in $files) {
        $new = $f.Name.ToLower()
        $new = $new -replace '[ _&]', '-'
        $new = $new -replace '[?!/\$#@*]', ''
        $new = $new -replace '-+', '-'
        $base = [IO.Path]::GetFileNameWithoutExtension($new).Trim('-')
        $ext  = [IO.Path]::GetExtension($new)
        $new  = $base + $ext
        if ($f.Name -cne $new) {
            Write-Host "Renaming: $($f.Name) -> $new"
            if ($f.Name -ieq $new) {
                # Case-only change: rename via temp name
                $tmp = $f.Name + '__tmp__'
                Rename-Item -LiteralPath $f.FullName -NewName $tmp
                Rename-Item -LiteralPath (Join-Path $f.DirectoryName $tmp) -NewName $new
            } else {
                Rename-Item -LiteralPath $f.FullName -NewName $new
            }
        }
    }
}

function Invoke-Add($folder) {
    Write-Host ""
    Write-Host "Where do you want to add text?"
    Write-Host "  before / after / both"
    $choice = (Read-Host "Enter choice").ToLower()

    $prefix = ""
    $suffix = ""

    if ($choice -eq "before" -or $choice -eq "both") {
        $prefix = Read-Host "Text to add before"
    }
    if ($choice -eq "after" -or $choice -eq "both") {
        $suffix = Read-Host "Text to add after"
    }
    if ($choice -notin @("before","after","both")) {
        Write-Host "Invalid choice." -ForegroundColor Red
        return
    }

    foreach ($f in @(Get-ChildItem -LiteralPath $folder -File)) {
        $base = [IO.Path]::GetFileNameWithoutExtension($f.Name)
        $ext  = [IO.Path]::GetExtension($f.Name)
        $new  = $prefix + $base + $suffix + $ext
        if ($f.Name -ne $new) {
            Write-Host "Renaming: $($f.Name) -> $new"
            Rename-Item -LiteralPath $f.FullName -NewName $new
        }
    }
}

function Invoke-FindReplace($folder) {
    Write-Host ""
    $find    = Read-Host "Text to find"
    $replace = Read-Host "Replace with (leave blank to remove)"

    foreach ($f in @(Get-ChildItem -LiteralPath $folder -File)) {
        $base    = [IO.Path]::GetFileNameWithoutExtension($f.Name)
        $ext     = [IO.Path]::GetExtension($f.Name)
        $newBase = $base -replace [regex]::Escape($find), $replace
        $new     = $newBase + $ext
        if ($f.Name -ne $new) {
            Write-Host "Renaming: $($f.Name) -> $new"
            Rename-Item -LiteralPath $f.FullName -NewName $new
        }
    }
}

# --- Main ---
$folder = Get-FolderPath

while ($true) {
    Write-Host ""
    Write-Host "What do you want to do?"
    Write-Host "  clean   - lowercase, replace spaces/underscores with hyphens, remove special characters"
    Write-Host "  add     - add text before and/or after filenames"
    Write-Host "  rename  - find and replace text in filenames"
    Write-Host "  exit    - quit"
    Write-Host ""
    $action = (Read-Host "Enter action").ToLower()

    switch ($action) {
        "clean"  { Invoke-Clean $folder }
        "add"    { Invoke-Add $folder }
        "rename" { Invoke-FindReplace $folder }
        "exit"   { exit }
        default  { Write-Host "Invalid action." -ForegroundColor Red }
    }

    Write-Host ""
    Write-Host "Done."
    Write-Host ""
    $again = Read-Host "Do anything else? (y/n)"
    if ($again -ine "y") { exit }
}
