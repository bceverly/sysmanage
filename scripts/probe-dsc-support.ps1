# Copyright (c) 2024-2026 Bryan Everly
# Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
# See the LICENSE file in the project root for the full terms.
#
# Phase 20.1 spike probe: can THIS Windows host apply desired state LOCALLY?
#
# The POSIX half of 20.1 is pull-style Ansible (see probe-ansible-support.sh).
# Windows cannot take that path -- ansible-core declares `Operating System ::
# POSIX` and Windows is a MANAGED node, never a control node -- so Windows was
# decided (Bryan, 2026-08-26) to get a DSC / PowerShell executor behind the same
# profile abstraction. This probe establishes what that executor can actually
# rely on, before any of it is written.
#
# The question it answers is deliberately narrow: can we apply a resource
# IMPERATIVELY on this box, with no MOF compile, no LCM configuration, and above
# all NO INBOUND PORT -- because "agent -> server on 443 only" is a Phase 19
# guarantee we are not going to spend.
#
# That last point is the subtle one. On Windows PowerShell 5.1,
# Invoke-DscResource historically goes through the local CIM/WinRM stack, so a
# host with WinRM disabled may fail even for a purely local apply. This probe
# reports the WinRM service state for exactly that reason.
#
# Writes nothing outside a temp directory; installs nothing.
#
# Usage:   powershell -ExecutionPolicy Bypass -File scripts\probe-dsc-support.ps1
#    or:   pwsh -File scripts/probe-dsc-support.ps1

[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'

function Get-Safe { param([scriptblock]$Block, $Fallback = 'error')
  try { $v = & $Block; if ($null -eq $v -or "$v" -eq '') { return 'none' }; return $v } catch { return $Fallback } }

Write-Output '=== SysManage Phase 20.1 DSC / PowerShell control-plane probe ==='

# --- Host -------------------------------------------------------------------
$osCaption = Get-Safe { (Get-CimInstance Win32_OperatingSystem).Caption }
$osVersion = Get-Safe { [string][System.Environment]::OSVersion.Version }
$arch      = Get-Safe { $env:PROCESSOR_ARCHITECTURE }
Write-Output "os=$osCaption version=$osVersion arch=$arch"

# --- PowerShell -------------------------------------------------------------
$psVersion = Get-Safe { [string]$PSVersionTable.PSVersion }
$psEd = Get-Safe { [string]$PSVersionTable.PSEdition }   # NOT $psEdition: PowerShell variable names are case-insensitive, so that collides with the read-only built-in
Write-Output "powershell_version=$psVersion edition=$psEd"

# Both matter: 5.1 has DSC v1/v2 built in, PS7 does not and needs a module or
# the standalone DSC v3 engine. An executor may well have to target 5.1.
$winPs = Get-Safe { (Get-Command powershell.exe -ErrorAction Stop).Source }
$pwsh  = Get-Safe { (Get-Command pwsh.exe -ErrorAction Stop).Source }
Write-Output "windows_powershell=$winPs"
Write-Output "pwsh=$pwsh"

$execPolicy = Get-Safe { [string](Get-ExecutionPolicy) }
Write-Output "execution_policy=$execPolicy"

# DSC generally requires elevation; the agent runs as a service, so what matters
# later is the SERVICE account, not this shell -- but a non-elevated result here
# means the probe's own apply test is not conclusive.
$elevated = Get-Safe {
  $id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
  [string](New-Object System.Security.Principal.WindowsPrincipal($id)).IsInRole(
    [System.Security.Principal.WindowsBuiltInRole]::Administrator) }
Write-Output "elevated=$elevated"

# --- Which DSC generation is present ----------------------------------------
$dscModule = Get-Safe {
  $m = Get-Module -ListAvailable PSDesiredStateConfiguration | Sort-Object Version -Descending | Select-Object -First 1
  if ($m) { "$($m.Version)" } else { 'none' } }
Write-Output "psdesiredstateconfiguration_module=$dscModule"

$invokeDsc = Get-Safe { if (Get-Command Invoke-DscResource -ErrorAction Stop) { 'available' } else { 'none' } }
Write-Output "invoke_dscresource=$invokeDsc"

# DSC v3 is a standalone cross-platform engine, not a PowerShell module.
$dscV3 = Get-Safe { (Get-Command dsc.exe -ErrorAction Stop).Source }
Write-Output "dsc_v3_binary=$dscV3"

$lcm = Get-Safe { [string](Get-DscLocalConfigurationManager -ErrorAction Stop).RefreshMode }
Write-Output "lcm_refresh_mode=$lcm"

# --- WinRM: the "no inbound port" question ----------------------------------
# We are NOT asking to manage this box over WinRM. We are asking whether a
# purely LOCAL Invoke-DscResource still drags the WinRM stack in as a
# dependency, because if it does, a hardened host with WinRM disabled cannot run
# the executor even though nothing is listening on the network.
$winrmSvc = Get-Safe { [string](Get-Service WinRM -ErrorAction Stop).Status }
$winrmStart = Get-Safe { [string](Get-CimInstance Win32_Service -Filter "Name='WinRM'").StartMode }
Write-Output "winrm_service=$winrmSvc start_mode=$winrmStart"

# --- Does an imperative apply actually work? --------------------------------
# The closest analogue to `connection: local` on POSIX: Test, then Set, then
# Test again -- the second Test MUST come back true, which is the idempotency
# signal the POSIX probe gets from `changed=1` rather than `changed=2`.
$applyResult = 'skipped'
$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ("sysmanage-dsc-probe-" + [guid]::NewGuid().ToString('N').Substring(0,8))
if ($invokeDsc -eq 'available') {
  try {
    New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null
    $target = Join-Path $tmpDir 'probe.txt'
    $props = @{ DestinationPath = $target; Contents = "sysmanage probe`n"; Ensure = 'Present'; Type = 'File' }
    $before = Invoke-DscResource -Name File -ModuleName PSDesiredStateConfiguration -Method Test -Property $props -ErrorAction Stop
    Invoke-DscResource -Name File -ModuleName PSDesiredStateConfiguration -Method Set -Property $props -ErrorAction Stop | Out-Null
    $after = Invoke-DscResource -Name File -ModuleName PSDesiredStateConfiguration -Method Test -Property $props -ErrorAction Stop
    $b = if ($before.InDesiredState) { 'true' } else { 'false' }
    $a = if ($after.InDesiredState) { 'true' } else { 'false' }
    # test_before=false,test_after=true is the healthy result: it was not in the
    # desired state, we applied it, and it now is. test_after=false means Set
    # silently did not take -- worse than an exception.
    $applyResult = "test_before=$b,applied,test_after=$a"
  } catch {
    $applyResult = "FAILED: " + ($_.Exception.Message -replace '[\r\n]+', ' ' -replace ',', ';')
  } finally {
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
  }
}
Write-Output "imperative_apply=$applyResult"

# --- one greppable line to send back ----------------------------------------
Write-Output ("PROBE-RESULT os=windows version=$osVersion arch=$arch ps=$psVersion/$psEd " +
  "elevated=$elevated dsc_module=$dscModule invoke_dsc=$invokeDsc dsc_v3=$dscV3 " +
  "lcm=$lcm winrm=$winrmSvc/$winrmStart apply=$applyResult")
