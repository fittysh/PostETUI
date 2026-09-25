```
      ▄██████▄▄██████▄     ______         _   _____ _____ _   _ _____
     ██▀    ▀██▀    ▀██    | ___ \       | | |  ___|_   _| | | |_   _|
     ██      ██      ██    | |_/ /__  ___| |_| |__   | | | | | | | |
     ██      ██      ██    |  __/ _ \/ __| __|  __|  | | | | | | | |
    ▄██      ██      ██    | | | (_) \__ \ |_| |___  | | | |_| |_| |_
█████▀       ██      ██    \_|  \___/|___/\__\____/  \_/  \___/ \___/
```

# PostETUI

One terminal console for the Post-E automation scripts (Micron Penang).

You pick a script, fill in a form, check the exact command, and run it as a
dry-run or for real. You watch the output live, read the CSV report, and can
roll back from any earlier run. Every run is written to an audit log.

PostETUI only launches and displays the scripts. It never changes what a
script does. All the safety rules stay inside the scripts themselves.

## Quick install

Open **PowerShell**, paste this line, and press **Enter**:

```powershell
irm https://raw.githubusercontent.com/fittysh/PostETUI/main/install.ps1 | iex
```

Then open a **new** PowerShell window and type `postetui`. The full steps
are below.

![Scripts tab](docs/img/01-scripts.svg)

## Install step by step

**Copy and paste.** Every grey command box on this page has a copy button in
its top-right corner. Click it, click in the PowerShell window, then paste
with **Ctrl+V** (or right-click) and press **Enter**. Run one box at a time.

**What you need:**

- A Windows 10 or 11 PC. You do not need admin rights.
- Access to github.com for Option A. If the PC cannot reach GitHub, use
  Option B.

| Option | Use it when | Needs Python |
|---|---|---|
| [A. One command](#option-a-one-command-recommended) | The PC can reach github.com | No |
| [B. Offline zip](#option-b-offline-zip-pc-without-github-access) | Tool or fab PC with no GitHub access | No |
| [C. From source](#option-c-from-source-developers) | You want to change PostETUI | Yes (3.11+) |

### Option A: one command (recommended)

**Step 1.** Open PowerShell as your normal user, not as administrator. Press
the **Windows** key, type `powershell`, and press **Enter**.

**Step 2.** Install PostETUI:

```powershell
irm https://raw.githubusercontent.com/fittysh/PostETUI/main/install.ps1 | iex
```

When it finishes, the last lines say:

```text
PostETUI installed.
  Run      : open a NEW terminal and type  postetui
```

**Step 3.** Close this PowerShell window and open a new one. The new window
picks up the updated PATH.

**Step 4.** Check the install:

```powershell
postetui --version
```

You should see `PostETUI 1.0.0`.

**Step 5.** Start PostETUI:

```powershell
postetui
```

PostETUI is installed in `%LOCALAPPDATA%\PostETUI`. Next, do
[Set up your scripts](#set-up-your-scripts).

<details>
<summary>Using Command Prompt (cmd.exe) instead of PowerShell?</summary>

Paste this in Command Prompt instead of Step 2:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/fittysh/PostETUI/main/install.ps1 | iex"
```

</details>

### Option B: offline zip (PC without GitHub access)

**Step 1.** On a PC that can reach GitHub, open PowerShell and download the
release zip:

```powershell
Invoke-WebRequest https://github.com/fittysh/PostETUI/releases/latest/download/PostETUI-win64.zip -OutFile "$HOME\Downloads\PostETUI-win64.zip"
```

You can also download it from the
[Releases page](https://github.com/fittysh/PostETUI/releases).

**Step 2.** Copy `PostETUI-win64.zip` to the team share or a USB drive, then
to the target PC's `Downloads` folder.

**Step 3.** On the target PC, open PowerShell and extract the zip:

```powershell
Expand-Archive "$HOME\Downloads\PostETUI-win64.zip" -DestinationPath "$HOME\Downloads\PostETUI-setup" -Force
```

**Step 4.** Run the installer:

```powershell
& "$HOME\Downloads\PostETUI-setup\install.bat"
```

You can also double-click `install.bat` in File Explorer. It finishes with
"Press any key to continue".

**Step 5.** Open a new PowerShell window and check the install:

```powershell
postetui --version
```

### Option C: from source (developers)

You need [Git](https://git-scm.com/download/win). If Python 3.11 or newer
is missing, `install.bat` offers to install it with winget.

**Step 1.** Clone the repository:

```powershell
git clone https://github.com/fittysh/PostETUI.git "$HOME\PostETUI"
```

**Step 2.** Go to the folder:

```powershell
cd "$HOME\PostETUI"
```

**Step 3.** Install. This creates `.venv`, installs the pinned packages, and
adds `bin\` to your PATH:

```powershell
.\install.bat
```

**Step 4.** Run the tests:

```powershell
.\.venv\Scripts\python -m pytest -q
```

**Step 5.** Start PostETUI from source:

```powershell
.\PostETUI.bat
```

In a new terminal, `postetui` also works.

### Set up your scripts

Do this once after installing. These commands use the Option A and B folder.
For Option C, use your clone folder instead.

**Step 1.** Open the scripts folder and copy your `.ps1` files into it, for
example `KLA_Recipe_Proliferate.ps1`:

```powershell
explorer "$env:LOCALAPPDATA\PostETUI\scripts"
```

**Step 2.** List your target tools, one tool ID per line, and save:

```powershell
notepad "$env:LOCALAPPDATA\PostETUI\scripts\tools.txt"
```

**Step 3.** Show each script's SHA-256 fingerprint:

```powershell
postetui --print-hashes
```

**Step 4.** Pin each script. Paste its fingerprint into `sha256:` on that
script's entry, then save. Once a script is pinned, PostETUI refuses to run
it if the file changes.

```powershell
notepad "$env:LOCALAPPDATA\PostETUI\catalog.yaml"
```

To add scripts that are not in the catalog yet, see
[Add more scripts](#add-more-scripts-no-code).

The run checklist for technicians is in
[OPERATOR_GUIDE.md](OPERATOR_GUIDE.md).

### Update

Run the install command again. It keeps your `catalog.yaml`, tool lists,
logs and backups.

```powershell
irm https://raw.githubusercontent.com/fittysh/PostETUI/main/install.ps1 | iex
```

When your `catalog.yaml` already exists, the installer leaves it unchanged.
It saves the new default beside it as `catalog.default.yaml`, so you can
compare the two.

### Uninstall

**Step 1.** Remove PostETUI from your PATH:

```powershell
$k = 'HKCU:\Environment'; $p = (Get-Item $k).GetValue('Path', '', 'DoNotExpandEnvironmentNames'); Set-ItemProperty $k Path (($p -split ';' | Where-Object { $_ -and $_ -notlike '*\PostETUI*' }) -join ';') -Type ExpandString; [Environment]::SetEnvironmentVariable('POSTETUI_HOME', $null, 'User')
```

**Step 2.** Delete the program folder.

> **Warning:** this also deletes `Logs\` (the audit trail) and
> `scripts\backups\`. Copy them somewhere else first if you need them.

```powershell
Remove-Item "$env:LOCALAPPDATA\PostETUI" -Recurse -Force
```

### Install problems

| Symptom | Fix |
|---|---|
| `postetui` is not recognised | Open a **new** PowerShell window. PATH only updates in new windows. |
| `Could not create SSL/TLS secure channel` | Use the command below that forces TLS 1.2. |
| `(407) Proxy Authentication Required` | Use the command below that sends your Windows login to the proxy. |
| Download blocked or times out | Use [Option B](#option-b-offline-zip-pc-without-github-access). |
| `postetui.exe` is blocked by policy (AppLocker) | Ask IT to allow `%LOCALAPPDATA%\PostETUI\postetui.exe`, or use Option C. |
| `pip` fails in Option C | Set your proxy, e.g. `$env:HTTPS_PROXY = 'http://<proxy>:<port>'`, then run `.\install.bat` again. |

Force TLS 1.2:

```powershell
[Net.ServicePointManager]::SecurityProtocol = 'Tls12'; irm https://raw.githubusercontent.com/fittysh/PostETUI/main/install.ps1 | iex
```

Send your Windows login to the corporate proxy:

```powershell
[Net.WebRequest]::DefaultWebProxy.Credentials = [Net.CredentialCache]::DefaultNetworkCredentials; irm https://raw.githubusercontent.com/fittysh/PostETUI/main/install.ps1 | iex
```

## Keybindings

| Key | Where | Action |
|---|---|---|
| `Tab` / `Shift+Tab` | everywhere | Next / previous tab |
| `1` to `5` | outside text fields | Scripts, Run, Output, Reports, Rollback |
| `Backspace` | outside text fields | Back to the previous tab |
| `q`, `Ctrl+Q` | everywhere | Quit (blocked while a run is active) |
| `o` | everywhere | Open the operator guide |
| `Up` / `Down` | Scripts | Move the selection |
| `Enter` | Scripts | Open the script in the Run tab |
| `d` | Scripts, Run | Dry-run (safe, no writes) |
| `/` | Scripts | Filter by name or tag; `Esc` clears |
| `Up` / `Down` / `Enter` | Run form | Next / previous field |
| `Esc` | Run form | Leave the field, so `d` and `Enter` act on the form |
| `Enter` | Run (no field focused) | APPLY. You must type `APPLY` to confirm |
| `c` | Run | Copy the command |
| `Ctrl+O` | Run | Override a hash mismatch. You must type `OVERRIDE` |
| `k` | Output | Cancel the run and stop the process tree |
| `a` | Output | Turn auto-scroll on or off |
| `Enter` | Reports file list | Load that CSV |
| `1` `2` `3` `4` | Reports | Show all, failed, skipped or timeout rows |
| `s` / `r` | Reports | Change the sort column / reload |
| `e` / `x` | Reports | Export the view to CSV / a summary to XLSX in `Reports\` |
| `r` | Rollback | Dry-run the rollback |
| `Enter` | Rollback | Apply the rollback. Only after its dry-run passed; type `APPLY` |
| `F5` | Rollback | Refresh |

The mouse works too, but you never need it.

## Add more scripts (no code)

You don't need to change any code to add a script. Each script needs two
things:

1. The script file in the `scripts` folder.
2. One entry for it in `catalog.yaml`.

Add as many as you need. They all appear on the Scripts tab.

| Option | Who gets the new scripts |
|---|---|
| [1. Your PC only](#option-1-your-pc-only-quick-test) | Only you. Good for testing. |
| [2. All Micron users](#option-2-all-micron-users-through-a-github-release) | Everyone, through a new GitHub release. |

### Option 1: your PC only (quick test)

**Step 1.** Copy the script files into the scripts folder:

```powershell
Copy-Item .\My-Script-1.ps1, .\My-Script-2.ps1 "$env:LOCALAPPDATA\PostETUI\scripts\"
```

**Step 2.** Open the catalog:

```powershell
notepad "$env:LOCALAPPDATA\PostETUI\catalog.yaml"
```

**Step 3.** Add one entry per script under `scripts:`. Indent with spaces,
not tabs. Every entry starts with `  - id:`.

```yaml
  - id: lot_report                     # unique, lower_case
    name: "Lot Report Collector"
    path: "scripts/My-Script-1.ps1"    # inside the PostETUI folder; subfolders are fine
    interpreter: powershell            # powershell | pwsh | python
    tags: [kla, report]
    synopsis: "Collect reports for a lot list."
    supports_dry_run: true
    dry_run_flag: "-DryRun"
    base_args: ["-NonInteractive"]     # always passed
    report_csv_glob: "scripts/reports/*.csv"
    exit_codes: {0: SUCCESS, 1: WARN, 2: FAILED}
    parameters:
      - {name: LotListPath, type: path, required: true, must_exist: true}
      - {name: TimeoutSeconds, type: int, default: 60, min: 10, max: 600}

  - id: height_audit
    name: "Component Height Audit"
    path: "scripts/My-Script-2.ps1"
    parameters:
      - {name: Mode, type: enum, choices: [Audit, Enable], default: Audit}
      - {name: TargetTools, type: list, blast_radius: true}
      - {name: SkipPing, type: bool, default: false}
```

**Step 4.** Check the catalog and show each script's SHA-256 fingerprint.
If the YAML has a mistake, this prints the line number.

```powershell
postetui --print-hashes
```

**Step 5.** Pin each script. Paste its fingerprint into `sha256:` on that
script's entry, then save the file. Once a script is pinned, PostETUI
refuses to run it if the file changes.

**Step 6.** Restart PostETUI. The new scripts appear on the Scripts tab.

```powershell
postetui
```

### Option 2: all Micron users, through a GitHub release

Run these in your source clone (see
[Option C](#option-c-from-source-developers)).

**Step 1.** Go to the clone and get the latest changes:

```powershell
cd "$HOME\PostETUI"; git pull
```

**Step 2.** Copy the script files into `scripts\`:

```powershell
Copy-Item .\My-Script-1.ps1, .\My-Script-2.ps1 .\scripts\
```

**Step 3.** Add one entry per script to the bundled catalog. Use the same
format as Option 1, Step 3.

```powershell
notepad .\postetui\assets\catalog.yaml
```

**Step 4.** Check the catalog and get the fingerprints. Paste each
fingerprint into `sha256:`, then save.

```powershell
.\.venv\Scripts\python -m postetui --print-hashes
```

**Step 5.** Try the scripts in PostETUI. Dry-run each one.

```powershell
.\PostETUI.bat
```

**Step 6.** Commit and push:

```powershell
git add scripts postetui\assets\catalog.yaml; git commit -m "feat: add lot report and height audit scripts"; git push
```

**Step 7.** Publish a release. Use a version one higher than the last one on
the [Releases page](https://github.com/fittysh/PostETUI/releases). The
release workflow tests and builds a new zip that includes the scripts.

```powershell
git tag v1.1.0; git push origin v1.1.0
```

**Step 8.** Tell users to update by running the install command again:

```powershell
irm https://raw.githubusercontent.com/fittysh/PostETUI/main/install.ps1 | iex
```

**Existing installs keep their own `catalog.yaml`.** The installer does not
overwrite it, so a site's pins are never lost. The new entries go into
`catalog.default.yaml` instead. On each PC that already had PostETUI, copy
the new entries from `catalog.default.yaml` into `catalog.yaml`:

```powershell
notepad "$env:LOCALAPPDATA\PostETUI\catalog.default.yaml"; notepad "$env:LOCALAPPDATA\PostETUI\catalog.yaml"
```

### Turn on a draft entry

These four scripts are already in the catalog as `status: draft`:

- KLA Auto Collect Report
- Component Height Enablement
- Coplan / LTS Analyzer
- MAM Reports Auto-Trigger

To turn one on:

1. Put the script file in `scripts\`. Its name must match the entry's
   `path:` exactly.
2. Make `parameters:` match the real script's parameters.
3. Change `status: draft` to `status: active`.
4. Pin it with `postetui --print-hashes`.

### What makes a script work well in PostETUI

- **No prompts.** PostETUI starts scripts with no keyboard input, so
  Read-Host always gets an empty answer. Give every choice a parameter, or
  add a `-NonInteractive` or `-Force` switch to `base_args`.
- **Progress bar.** Print one line per tool, like
  `[ 3 / 10 ] TOOL-A02  SUCCESS`. The bar and counters update live.
- **Reports tab.** Write a CSV with `TargetTool` and `Status` columns into
  the folder that `report_csv_glob` points to.
- **Rollback tab.** Add `rollback_flag`, `manifest_flag` and `backup_glob`.
  See the `kla_recipe_proliferate` entry for an example.
- **Exit codes.** Map them with `exit_codes`. Any code not listed counts as
  FAILED.
- **Python scripts.** Set `interpreter: python`. Parameters are passed as
  `--Name value`.

### Catalog field reference

Script entry:

| Field | Required | Meaning |
|---|---|---|
| `id` | yes | Unique name: lower-case letters, digits and `_` |
| `name` | yes | Name shown in the catalog |
| `path` | yes | Script file, relative to the PostETUI folder. It must stay inside that folder. |
| `interpreter` | | `powershell` (default), `pwsh` or `python` |
| `sha256` | | Pinned fingerprint from `postetui --print-hashes`. Leave it `null` to run with a warning. |
| `status` | | `active` (default) or `draft` |
| `tags`, `synopsis`, `description`, `safety` | | Text shown in the Details panel. The `/` filter searches `tags`. |
| `supports_dry_run`, `dry_run_flag` | | Turn on dry-run and name its switch, e.g. `-DryRun` |
| `base_args` | | Switches added to every run, e.g. `["-NonInteractive", "-Force"]` |
| `timeout_seconds` | | Kill the run after this many seconds (default 3600) |
| `exit_codes` | | e.g. `{0: SUCCESS, 1: WARN, 2: FAILED}` |
| `progress_regex` | | Custom progress line format with named groups `idx`, `total`, `tool` and `status` |
| `report_csv_glob`, `log_glob` | | Where the script writes its CSV reports and logs |
| `rollback_flag`, `manifest_flag`, `backup_glob`, `manifest_name` | | Turn on the Rollback tab for this script |
| `one_of_required` | | At least one of these parameters must be set, e.g. `[[TargetTools, UseToolsFile]]` |

Parameter:

| Field | Meaning |
|---|---|
| `name` | Parameter name. PostETUI passes it as `-Name` (`--Name` for Python). |
| `type` | `string`, `path`, `int`, `bool`, `enum` or `list` |
| `label`, `help` | Text shown in the form |
| `default` | Value the form starts with. After that, PostETUI remembers the last value used. |
| `required` | The field must be filled in |
| `must_exist` | For `path`: the file must exist. UNC paths are not checked. |
| `min`, `max` | For `int`: allowed range |
| `choices` | For `enum`: the allowed values |
| `flag` | Use a different switch name than `-Name` |
| `blast_radius` | Count this field's tools in the "N tool(s) will be written" line |

Rules the catalog enforces:

- The script path must stay inside the PostETUI folder.
- Unpinned scripts run with a warning. A pinned script whose file changed
  is refused until an operator types `OVERRIDE`.
- Values may not contain `;` `&` `|` `` ` `` `"` `$(` or line breaks.
- Dry-run is the default action. APPLY always needs a typed confirmation.

## How it works

```
postetui/
  __main__.py      CLI: --root, --catalog, --no-unicode, --print-hashes
  app.py           tabs, global keys, run lifecycle
  theme.py         palette, status colours, CSS, banner
  core/catalog.py  pydantic models, YAML loader, SHA-256 pins, root check
  core/runner.py   argument checks, async subprocess, streaming, cancel, timeout
  core/parser.py   progress lines, status words, operator hints
  core/reports.py  pandas CSV analysis, trend, repeat offenders, CSV/XLSX export
  core/backups.py  backup sets and manifests for the Rollback tab
  core/audit.py    Logs\postetui_audit.csv + postetui_audit.jsonl
  core/state.py    %APPDATA%\PostETUI\state.json (last values, recent runs)
  widgets/         one module per tab, plus the banner and the confirm dialog
```

How a script is launched:

- PowerShell scripts run as
  `powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "& '<script>' -Param 'value' ...; exit $LASTEXITCODE"`.
- It uses `-Command`, not `-File`, because `-File` passes `-TargetTools A,B`
  as one string and breaks tool lists.
- Every value is single-quoted, which makes it a literal in PowerShell, and
  is checked before it is quoted.
- The argument list goes to the OS directly. No shell is involved.
- The child process has no console window. It cannot draw over the TUI or
  wait on a hidden prompt.

Files written, relative to the PostETUI folder:

| File | Content |
|---|---|
| `Logs\PostETUI_<script>_<yyyyMMdd_HHmmss>.log` | Full transcript of one run |
| `Logs\postetui_audit.csv` / `.jsonl` | One row per launch: user, host, script hash, mode, args, exit code, counts, paths |
| `Reports\PostETUI_export_*.csv`, `PostETUI_summary_*.xlsx` | Exports from the Reports tab |

## Build and release (maintainers)

```bat
install.bat                    :: source setup, once
.venv\Scripts\python -m pytest :: tests
build.bat                      :: dist\postetui.exe + dist\PostETUI-win64.zip
```

To publish a release, push a tag:

```bat
git tag v1.0.1
git push origin v1.0.1
```

`.github/workflows/release.yml` then tests, builds, smoke-tests the exe, and
attaches `PostETUI-win64.zip` to a GitHub release. The one-command installer
always downloads the latest release.

Refresh the guide screenshots with `.venv\Scripts\python docs\screenshots.py`.

## Troubleshooting (running)

| Symptom | Fix |
|---|---|
| "Execution policy blocked the script" | Group Policy blocks unsigned scripts. Ask IT to allow RemoteSigned for this PC, or sign the script. |
| Screen says "Please enlarge the terminal" | PostETUI needs at least 100 x 30. Maximise the window. |
| Boxes look broken on an old console | Run `postetui --no-unicode`, or set `POSTETUI_NO_UNICODE=1`. |
| No colours wanted | Set `NO_COLOR=1`. |
| Audit CSV "locked" warning | `postetui_audit.csv` is open in Excel. The run is still in `postetui_audit.jsonl`. |

## Known limitations

- **Credential prompt.** Not built, because no catalog script takes
  `-Credential` yet. Passing a password on the command line would expose it
  in the process list, so it needs a stdin hand-off when the first script
  needs one.
- **Graceful cancel.** Windows PowerShell ignores polite stop requests from
  another process. `k` asks once, waits `cancel_grace_seconds` (5 s by
  default), then force-kills the process tree with `taskkill /T /F`.
- **UNC paths in path fields.** These are not checked for existence in the
  form, because an unreachable share would freeze it. The script checks them
  at run time, and the run timeout still applies.
- **Blast radius.** When `UseToolsFile` is on, the count uses
  `settings.tools_file`, even if the `ToolsFile` override points somewhere
  else.
- **Progress bar.** It follows the `[ i / n ]` lines the script prints. A
  script that prints no such lines shows an indeterminate bar.
- **No-Unicode mode.** `--no-unicode` switches borders and the banner to
  ASCII. Scrollbars and some Textual widgets still use block characters.
- **Parameters.** Only `KLA_Recipe_Proliferate` has parameters taken from
  the real script. The other four catalog entries are drafts.

## Alternate stack (not built)

If the team standardises on Node, the same design maps onto React + Ink 5 +
execa, packaged with `pkg`. Python + Textual was chosen because it ships as
one `.exe`, and pandas reads the scripts' CSV output directly.
