#!/usr/bin/env pwsh
# Install a pre-built plug-in release into the current user's GIMP 3 plug-in
# directory. Bundled into the release archive next to the gimp-comfyui folder
# so it works on Windows without a Python interpreter.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $ScriptDir "gimp-comfyui"

if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
    Write-Error "gimp-comfyui folder not found next to this script"
    exit 1
}

$Version = if ($env:GIMP_VERSION) { $env:GIMP_VERSION } else { "3.2" }
if ($env:GIMP_PLUGIN_DIR) {
    $PluginRoot = $env:GIMP_PLUGIN_DIR
} elseif ($env:GIMP_CONFIG_DIR) {
    $PluginRoot = Join-Path $env:GIMP_CONFIG_DIR "plug-ins"
} else {
    $PluginRoot = Join-Path $env:APPDATA "GIMP\$Version\plug-ins"
}

$Destination = Join-Path $PluginRoot "gimp-comfyui"

if (Test-Path -LiteralPath $Destination) {
    Remove-Item -LiteralPath $Destination -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PluginRoot | Out-Null
Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force

Write-Output "Installed to $Destination"
