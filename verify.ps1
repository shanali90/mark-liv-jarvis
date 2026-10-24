$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Split-Path -Parent $MyInvocation.MyCommand.Path)).Path
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Checks = [ordered]@{}

function Report-Check([string]$Name, [bool]$Passed) {
    $Checks[$Name] = $Passed
    if ($Passed) {
        Write-Output "PASS: $Name"
    } else {
        Write-Output "FAIL: $Name"
    }
}

Write-Output "=== pytest -v -rs ==="
$pytestPassed = $false
if (Test-Path $Python) {
    $PytestOutput = @(& $Python -m pytest -v -rs 2>&1)
    $PytestExit = $LASTEXITCODE
    $PytestOutput | ForEach-Object { Write-Output $_ }
    $HasTestSummary = [bool]($PytestOutput | Where-Object {
        $_ -match '\b\d+ passed\b|\b\d+ failed\b|\b\d+ skipped\b|\b\d+ error\b'
    })
    if ($PytestExit -eq 5) {
        Write-Output "pytest collected 0 tests."
    }
    $pytestPassed = ($PytestExit -eq 0 -and $HasTestSummary)
} else {
    Write-Output "Python environment not found: $Python"
}
Report-Check "pytest collected tests and passed" $pytestPassed

Write-Output "=== pyflakes: all project Python files (per-file, no command-line length limit) ==="
$pyflakesPassed = $false
if (Test-Path $Python) {
    $PyflakesCheck = @'
from pathlib import Path
import sys
import pyflakes.api
from pyflakes.reporter import Reporter

excluded = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
files = sorted(
    path for path in Path(".").rglob("*.py")
    if not excluded.intersection(path.parts)
)
reporter = Reporter(sys.stdout, sys.stderr)
warnings = 0
for path in files:
    warnings += pyflakes.api.checkPath(str(path), reporter)
print(f"Checked {len(files)} project Python files; {warnings} pyflakes warning(s).")
sys.exit(1 if warnings else 0)
'@
    $PyflakesEncoded = [Convert]::ToBase64String(
        [System.Text.Encoding]::UTF8.GetBytes($PyflakesCheck)
    )
    & $Python -c "import base64; exec(base64.b64decode('$PyflakesEncoded'))"
    $pyflakesPassed = ($LASTEXITCODE -eq 0)
} else {
    Write-Output "Python environment not found: $Python"
}
Report-Check "pyflakes" $pyflakesPassed

Write-Output "=== main.py startup: wait 40 seconds and inspect only this run's log bytes ==="
$StartedPid = $null
$TreePids = @()
$TreeIdentity = @{}
$AppStarted = $false
$LogPath = Join-Path $Root "logs\jarvis_activity.log"
$StdoutPath = Join-Path $Root "logs\verify_main.stdout.log"
$StderrPath = Join-Path $Root "logs\verify_main.stderr.log"
New-Item -ItemType Directory -Path (Split-Path -Parent $LogPath) -Force | Out-Null
$LogStartLength = 0
if (Test-Path $LogPath) {
    $LogStartLength = (Get-Item $LogPath).Length
}
try {
    if (-not (Test-Path $Python)) {
        throw "Python environment not found: $Python"
    }
    $App = Start-Process -FilePath $Python -ArgumentList "main.py" `
        -WorkingDirectory $Root -PassThru `
        -RedirectStandardOutput $StdoutPath -RedirectStandardError $StderrPath
    $StartedPid = [int]$App.Id
    $AppStarted = $true
    Write-Output "Started main.py PID=$StartedPid; waiting 40 seconds."
    Start-Sleep -Seconds 40
} catch {
    Write-Output "Startup error: $_"
} finally {
    if ($null -ne $StartedPid) {
        try {
            $Processes = @(Get-CimInstance Win32_Process -ErrorAction Stop)
            $Frontier = @($StartedPid)
            while ($Frontier.Count -gt 0) {
                $Parent = [int]$Frontier[0]
                $Frontier = @($Frontier | Select-Object -Skip 1)
                $Children = @($Processes | Where-Object {
                    [int]$_.ParentProcessId -eq $Parent
                })
                foreach ($Child in $Children) {
                    $ChildPid = [int]$Child.ProcessId
                    if ($TreePids -notcontains $ChildPid) {
                        $TreePids += $ChildPid
                        $Frontier += $ChildPid
                    }
                }
            }
            $TreeProcessIds = @($StartedPid) + $TreePids
            foreach ($Process in $Processes) {
                $ProcessId = [int]$Process.ProcessId
                if ($TreeProcessIds -contains $ProcessId -and $Process.CreationDate) {
                    $TreeIdentity[[string]$ProcessId] = ([datetime]$Process.CreationDate).ToUniversalTime().Ticks
                }
            }
            for ($Index = $TreePids.Count - 1; $Index -ge 0; $Index--) {
                Stop-Process -Id $TreePids[$Index] -Force -ErrorAction SilentlyContinue
            }
            Stop-Process -Id $StartedPid -Force -ErrorAction SilentlyContinue
            Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
                Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($Root, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.Name -match '^python' } |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 2
        } catch {
            Write-Output "Process-tree cleanup error: $_"
        }
    }
}

$ConnectedLine = $null
if (Test-Path $LogPath) {
    $LogBytes = [System.IO.File]::ReadAllBytes($LogPath)
    $ReadStart = [Math]::Min($LogStartLength, $LogBytes.Length)
    $NewLog = [System.Text.Encoding]::UTF8.GetString(
        $LogBytes, $ReadStart, $LogBytes.Length - $ReadStart
    )
    $ConnectedLine = $NewLog -split "`r?`n" |
        Where-Object { $_ -match 'State:\s*CONNECTED\b' } |
        Select-Object -First 1
}
if ($ConnectedLine) {
    Write-Output $ConnectedLine
    Report-Check "main.py connected" $AppStarted
} else {
    Write-Output "FAIL: no State: CONNECTED line found in logs\jarvis_activity.log"
    Report-Check "main.py connected" $false
}

$TreeStillRunning = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $ProcessId = [string][int]$_.ProcessId
            $TreeIdentity.ContainsKey($ProcessId) -and
                $TreeIdentity[$ProcessId] -eq ([datetime]$_.CreationDate).ToUniversalTime().Ticks
        }
)
if ($TreeStillRunning.Count -eq 0) {
    Write-Output "Started process tree stopped: root=$StartedPid children=$($TreePids -join ',')"
    Report-Check "started process tree stopped" ($null -ne $StartedPid)
} else {
    $TreeStillRunning | Select-Object ProcessId, ParentProcessId, Name | Format-Table -AutoSize
    Report-Check "started process tree stopped" $false
}

Write-Output "=== python processes after cleanup (including CommandLine) ==="
$PythonProcesses = @(
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^python(w)?\.exe$' }
)
$RootPythonProcesses = @(
    $PythonProcesses | Where-Object {
        $_.CommandLine -and $_.CommandLine.IndexOf(
            $Root, [System.StringComparison]::OrdinalIgnoreCase
        ) -ge 0
    }
)
if ($PythonProcesses.Count -gt 0) {
    $PythonProcesses |
        Select-Object ProcessId, Name, CommandLine |
        Format-List
} else {
    Write-Output "No python processes running."
}
if ($RootPythonProcesses.Count -eq 0) {
    Report-Check "no project python processes remain" $true
} else {
    Report-Check "no project python processes remain" $false
}
Write-Output "=== Get-Process python ==="
Get-Process python -ErrorAction SilentlyContinue |
    Format-Table Id, ProcessName, StartTime -AutoSize

Write-Output "=== git status --short ==="
$GitStatus = @(& git status --short 2>&1)
$GitStatus | ForEach-Object { Write-Output $_ }
$GitStatusExit = $LASTEXITCODE
Report-Check "git status --short is clean" `
    ($GitStatusExit -eq 0 -and $GitStatus.Count -eq 0)

Write-Output "=== git diff --numstat pre-refactor -- core/prompt.txt ==="
& git rev-parse --verify pre-refactor *> $null
if ($LASTEXITCODE -eq 0) {
    $PromptNumstat = @(& git diff --numstat pre-refactor -- core/prompt.txt 2>&1)
    $PromptNumstat | ForEach-Object { Write-Output $_ }
    $PromptExit = $LASTEXITCODE
    $PromptAdded = 0
    $PromptDeleted = 0
    $PromptParsePassed = $true
    if ($PromptNumstat.Count -gt 0 -and $PromptNumstat[0] -match '^(\d+)\t(\d+)\t') {
        $PromptAdded = [int]$Matches[1]
        $PromptDeleted = [int]$Matches[2]
    } elseif ($PromptNumstat.Count -gt 0) {
        $PromptParsePassed = $false
    }
    $promptPassed = ($PromptExit -eq 0 -and $PromptParsePassed -and $PromptDeleted -eq 0 -and $PromptAdded -le 2)
} else {
    Write-Output "Not applicable: fresh-history repository has no pre-refactor baseline."
    $promptPassed = $true
}
Report-Check "prompt has zero deletions and at most two additions" `
    $promptPassed

Write-Output "=== non-ASCII comparison: main.py, core/audio, core/tools vs pre-refactor ==="
$NonAsciiCheck = @'
from collections import Counter
from pathlib import Path
import subprocess
import sys

paths = ["main.py"]
paths.extend(str(p) for folder in ("core/audio", "core/tools")
             for p in sorted(Path(folder).rglob("*.py")))
baseline_ref = subprocess.run(
    ["git", "rev-parse", "--verify", "pre-refactor"],
    capture_output=True,
)
if baseline_ref.returncode != 0:
    print("Not applicable: fresh-history repository has no pre-refactor baseline.")
    sys.exit(0)
try:
    baseline = subprocess.run(
        ["git", "show", "pre-refactor:main.py"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")
    current = [Path(path).read_text(encoding="utf-8") for path in paths]
except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
    print(f"Could not read comparison input: {exc}")
    sys.exit(1)

before = Counter(ch for ch in baseline if ord(ch) > 127)
after = Counter(ch for text in current for ch in text if ord(ch) > 127)
print("Compared files: " + ", ".join(paths))
print(f"pre-refactor non-ASCII characters: {sum(before.values())}")
print(f"current combined non-ASCII characters: {sum(after.values())}")
print("MATCH" if before == after else "MISMATCH")
if before != after:
    print("Only in pre-refactor: " + ascii(before - after))
    print("Only in current files: " + ascii(after - before))
    sys.exit(1)
'@
if (Test-Path $Python) {
    $NonAsciiEncoded = [Convert]::ToBase64String(
        [System.Text.Encoding]::UTF8.GetBytes($NonAsciiCheck)
    )
    & $Python -c "import base64; exec(base64.b64decode('$NonAsciiEncoded'))"
    $nonAsciiPassed = ($LASTEXITCODE -eq 0)
} else {
    $nonAsciiPassed = $false
}
Report-Check "non-ASCII comparison" $nonAsciiPassed

Write-Output "=== active pre-commit hook ==="
$HooksPath = git config --get core.hooksPath
if ($HooksPath) {
    $HookPath = Join-Path $Root $HooksPath
} else {
    $HookPath = Join-Path $Root ".git\hooks"
}
$HookPath = Join-Path $HookPath "pre-commit"
$hookPassed = $false
if (Test-Path $HookPath) {
    Write-Output "Hook: $HookPath"
    $HookContent = Get-Content $HookPath -Raw
    Get-Content $HookPath -TotalCount 30
    $requiredHookPatterns = @(
        'AIza', 'sk-ant-', 'Bearer', 'api_key',
        'client_secret', 'token', '\.db'
    )
    $MissingHookPatterns = @(
        $requiredHookPatterns | Where-Object { $HookContent -notmatch [regex]::Escape($_) }
    )
    if ($MissingHookPatterns.Count -eq 0) {
        $hookPassed = $true
    } else {
        Write-Output ("Missing required hook checks: " + ($MissingHookPatterns -join ", "))
    }
} else {
    Write-Output "FAIL: active pre-commit hook not found at $HookPath"
}
Report-Check "pre-commit hook has required secret checks" $hookPassed

Write-Output "=== git ls-files memory ==="
$MemoryFiles = @(& git ls-files memory)
$MemoryFiles
$MemoryExit = $LASTEXITCODE
$TrackedPersonalMemory = @(
    $MemoryFiles | Where-Object { $_ -match '(?i)(\.bak$|\.json$|\.db$)' }
)
Report-Check "git ls-files memory contains no personal files" `
    ($MemoryExit -eq 0 -and $TrackedPersonalMemory.Count -eq 0)

Write-Output "=== final results ==="
$AllPassed = $true
foreach ($Check in $Checks.GetEnumerator()) {
    if ($Check.Value) {
        Write-Output "PASS: $($Check.Key)"
    } else {
        Write-Output "FAIL: $($Check.Key)"
        $AllPassed = $false
    }
}
if ($AllPassed) {
    Write-Output "PASS"
    exit 0
} else {
    Write-Output "FAIL"
    exit 1
}
