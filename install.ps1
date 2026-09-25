<#
.SYNOPSIS
    Installs or updates PostETUI for the current user. No admin rights needed.

.DESCRIPTION
    Every route ends the same way: open a new terminal and type  postetui

    1. One line in PowerShell (latest GitHub release, no Python needed):
           irm https://raw.githubusercontent.com/fittysh/PostETUI/main/install.ps1 | iex

    2. Release zip from a file share (GitHub blocked on the PC):
           extract PostETUI-win64.zip anywhere, double-click install.bat

    3. Source clone (developers):
           git clone https://github.com/fittysh/PostETUI.git, double-click install.bat
           Needs Python 3.11+; offers to install it with winget.

    Routes 1 and 2 install to %LOCALAPPDATA%\PostETUI. Running them again
    updates PostETUI and keeps catalog.yaml, tools.txt, recipes.txt, Logs,
    reports and backups.

    No #Requires and no "exit" in this file: both break the "irm | iex" route.
#>

& {
    $ErrorActionPreference = 'Stop'
    $ZipUrl = 'https://github.com/fittysh/PostETUI/releases/latest/download/PostETUI-win64.zip'
    $AppDir = Join-Path $env:LOCALAPPDATA 'PostETUI'

    function Add-UserPath([string] $Dir) {
        # Read PATH raw so %VARS% in it stay unexpanded (REG_EXPAND_SZ).
        $key = 'HKCU:\Environment'
        $userPath = (Get-Item -LiteralPath $key).GetValue('Path', '', 'DoNotExpandEnvironmentNames')
        if (($userPath -split ';') -notcontains $Dir) {
            $newPath = @($userPath.TrimEnd(';'), $Dir) -ne '' -join ';'
            Set-ItemProperty -LiteralPath $key -Name 'Path' -Value $newPath -Type ExpandString
            $env:Path = $env:Path.TrimEnd(';') + ';' + $Dir
        }
        # Setting a variable through .NET broadcasts WM_SETTINGCHANGE, so new terminals see the new PATH.
        [Environment]::SetEnvironmentVariable('POSTETUI_HOME', $Dir, 'User')
    }

    function Initialize-Lists([string] $Root) {
        # Starter lists for KLA_Recipe_Proliferate.ps1. Never overwrite existing ones.
        $scripts = Join-Path $Root 'scripts'
        New-Item -ItemType Directory -Force -Path $scripts | Out-Null
        $lists = @{
            'tools.txt'   = '# One target tool ID per line, e.g. TOOL-A02. Lines starting with # are ignored.'
            'recipes.txt' = '# One recipe file name per line, e.g. EXAMPLE_PRODUCT_RECIPE.rcp'
        }
        foreach ($name in $lists.Keys) {
            $path = Join-Path $scripts $name
            if (-not (Test-Path -LiteralPath $path)) {
                Set-Content -LiteralPath $path -Value $lists[$name] -Encoding UTF8
            }
        }
        # Clear the downloaded-from-internet mark so a RemoteSigned group policy allows the files.
        Get-ChildItem -Path $Root -Recurse -File -Include '*.ps1', '*.bat', '*.cmd', '*.exe' | Unblock-File
    }

    function Install-Release([string] $From) {
        # $From holds postetui.exe, catalog.yaml, scripts\ and the docs.
        Get-Process -Name postetui -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$AppDir*" } | ForEach-Object {
            throw 'PostETUI is running. Close it and run the installer again.'
        }
        New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
        $siteCatalog = Test-Path -LiteralPath (Join-Path $AppDir 'catalog.yaml')
        # install.* stay out of the app folder: it goes on PATH and should expose only "postetui".
        Get-ChildItem -LiteralPath $From | Where-Object { $_.Name -notin 'install.bat', 'install.ps1', 'catalog.yaml' } |
            Copy-Item -Destination $AppDir -Recurse -Force
        if ($siteCatalog) {
            # Keep the site's pins and paths; ship the new default beside it for comparison.
            Copy-Item -LiteralPath (Join-Path $From 'catalog.yaml') -Destination (Join-Path $AppDir 'catalog.default.yaml') -Force
            Write-Host 'Kept your catalog.yaml. The new default is catalog.default.yaml.' -ForegroundColor Yellow
        } else {
            Copy-Item -LiteralPath (Join-Path $From 'catalog.yaml') -Destination $AppDir
        }
        Initialize-Lists $AppDir
        Add-UserPath $AppDir
        return $AppDir
    }

    function Find-Python {
        foreach ($cmd in 'py', 'python') {
            if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { continue }
            $extra = @()
            if ($cmd -eq 'py') { $extra = @('-3') }
            try {
                $version = & $cmd @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            } catch {
                continue
            }
            # 'python' can be the Microsoft Store stub, which fails here.
            if ($LASTEXITCODE -eq 0 -and $version -and [version]$version -ge [version]'3.11') {
                return , (@($cmd) + $extra)
            }
        }
        return $null
    }

    function Install-Source([string] $Root) {
        $python = Find-Python
        if (-not $python) {
            Write-Host 'Python 3.11 or newer was not found.' -ForegroundColor Yellow
            Write-Host 'No Python? Use the release instead: irm https://raw.githubusercontent.com/fittysh/PostETUI/main/install.ps1 | iex'
            if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
                throw 'winget is not available. Install Python 3.12 from https://www.python.org/downloads/ and run install.bat again.'
            }
            $answer = Read-Host 'Install Python 3.12 for this user with winget now? (Y/N)'
            if ($answer -notmatch '^[Yy]') { throw 'Python is required for a source install.' }
            winget install --exact --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
            $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
            $python = Find-Python
            if (-not $python) { throw 'Python was installed but is not on PATH yet. Open a new terminal and run install.bat again.' }
        }
        $exe = $python[0]
        $pyArgs = @($python | Select-Object -Skip 1)
        $venv = Join-Path $Root '.venv'
        if (-not (Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
            Write-Host "Creating $venv" -ForegroundColor Cyan
            & $exe @pyArgs -m venv $venv
            if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
        }
        Write-Host 'Installing Python packages (textual, pandas, pydantic, ...)' -ForegroundColor Cyan
        & (Join-Path $venv 'Scripts\python.exe') -m pip install --disable-pip-version-check -e $Root
        if ($LASTEXITCODE -ne 0) {
            throw 'pip could not install the packages. Behind a proxy? Set HTTPS_PROXY=http://<proxy>:<port> and run install.bat again.'
        }
        Initialize-Lists $Root
        Add-UserPath (Join-Path $Root 'bin')
        return $Root
    }

    if ($PSVersionTable.PSVersion -lt [version]'5.1') {
        throw ('PostETUI needs Windows PowerShell 5.1 or newer (found {0}).' -f $PSVersionTable.PSVersion)
    }

    $here = $PSScriptRoot
    if ($here -and (Test-Path -LiteralPath (Join-Path $here 'postetui.exe'))) {
        Write-Host "Installing PostETUI from $here" -ForegroundColor Cyan
        $installed = Install-Release $here
    } elseif ($here -and (Test-Path -LiteralPath (Join-Path $here 'pyproject.toml'))) {
        Write-Host "Setting up PostETUI from source in $here" -ForegroundColor Cyan
        $installed = Install-Source $here
    } else {
        $tmp = Join-Path $env:TEMP ('PostETUI_' + [guid]::NewGuid().ToString('N'))
        Write-Host "Downloading $ZipUrl" -ForegroundColor Cyan
        [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        try {
            Invoke-WebRequest -Uri $ZipUrl -OutFile "$tmp.zip" -UseBasicParsing
            Expand-Archive -LiteralPath "$tmp.zip" -DestinationPath $tmp
            $installed = Install-Release $tmp
        } finally {
            Remove-Item -LiteralPath "$tmp.zip", $tmp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host ''
    Write-Host 'PostETUI installed.' -ForegroundColor Green
    Write-Host '  Run      : open a NEW terminal and type  postetui'
    Write-Host "  Folder   : $installed"
    Write-Host '  Scripts  : put your .ps1 files in the scripts folder and list them in catalog.yaml'
    Write-Host '  Tools    : one tool ID per line in scripts\tools.txt'
}
