param([switch]$Apply,[switch]$Remove,[int]$Port=8080)
$ErrorActionPreference='Stop'
$runtimeRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$runtimePython=Join-Path $runtimeRoot '.venv\Scripts\pythonw.exe'
if(-not(Test-Path -LiteralPath $runtimePython)){$runtimePython=Join-Path $runtimeRoot '.venv\Scripts\python.exe'}
$runtimeScript=Join-Path $runtimeRoot 'scripts\run_runtime.py'
if(-not(Test-Path -LiteralPath $runtimePython) -or -not(Test-Path -LiteralPath $runtimeScript)){throw 'Runtime files are missing.'}
if($Port -lt 1 -or $Port -gt 65535){throw 'Invalid port.'}
$runtimeHasher=[Security.Cryptography.SHA256]::Create()
try{$runtimeHash=[BitConverter]::ToString($runtimeHasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($runtimeRoot))).Replace('-','')}finally{$runtimeHasher.Dispose()}
$runtimeTaskName='NawaERP-'+$runtimeHash.Substring(0,10)
$runtimeArgs='"'+$runtimeScript+'" --port '+$Port
if(-not $Apply){[pscustomobject]@{TaskName=$runtimeTaskName;Program=$runtimePython;Arguments=$runtimeArgs;Trigger='Current user logon';ApplyRequired=$true;Remove=[bool]$Remove}|ConvertTo-Json;return}
if($Remove){Unregister-ScheduledTask -TaskName $runtimeTaskName -Confirm:$false -ErrorAction SilentlyContinue;return}
$runtimeAction=New-ScheduledTaskAction -Execute $runtimePython -Argument $runtimeArgs -WorkingDirectory $runtimeRoot
$runtimeTrigger=New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$runtimeSettings=New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
Register-ScheduledTask -TaskName $runtimeTaskName -Action $runtimeAction -Trigger $runtimeTrigger -Settings $runtimeSettings -RunLevel Limited -Description 'Nawa ERP local runtime; encrypted backup destination is configured separately.' -Force|Out-Null
Write-Output ('Startup task registered for this user: '+$runtimeTaskName)
