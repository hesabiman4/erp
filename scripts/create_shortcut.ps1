param([switch]$Desktop)
$ErrorActionPreference='Stop'
$erpRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$erpTarget=Join-Path $erpRoot 'Open Nawa ERP.cmd'
if(-not(Test-Path -LiteralPath $erpTarget)){throw 'ERP launcher is missing.'}
$erpFolder=if($Desktop){[Environment]::GetFolderPath('Desktop')}else{$erpRoot}
$erpLink=Join-Path $erpFolder 'Nawa ERP.lnk'
$erpShell=New-Object -ComObject WScript.Shell
if(Test-Path -LiteralPath $erpLink){
    $erpExisting=$erpShell.CreateShortcut($erpLink)
    if($erpExisting.TargetPath -and $erpExisting.TargetPath -ne $erpTarget){throw 'An existing shortcut points to another installation; it was preserved.'}
}
$erpShortcut=$erpShell.CreateShortcut($erpLink)
$erpShortcut.TargetPath=$erpTarget
$erpShortcut.WorkingDirectory=$erpRoot
$erpShortcut.Description='Start the verified local Nawa ERP and open the browser'
$erpShortcut.Save()
Write-Output ('Shortcut created: '+$erpLink)
