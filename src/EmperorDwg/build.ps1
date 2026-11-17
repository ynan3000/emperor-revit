# Builds lib/dwg/EmperorDwg_1_1.dll from source on Windows.
# Needs: git and the .NET 8 SDK (or newer). Run from this folder: .\build.ps1
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$acadCommit = '0acbe974b865afb5ff3b256d5e13a6862574c438'   # ACadSharp 3.8.51
$work = Join-Path $here '_build'
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
git clone --quiet https://github.com/DomCR/ACadSharp.git (Join-Path $work 'ACadSharp')
Set-Location (Join-Path $work 'ACadSharp')
git checkout --quiet $acadCommit
git submodule update --init --recursive --quiet
git apply (Join-Path $here 'acadsharp-emperor.patch')
Copy-Item (Join-Path $here 'Emperor') 'src\ACadSharp\Emperor' -Recurse
dotnet build src\ACadSharp\ACadSharp.csproj -c Release -f net8.0 -p:AssemblyName=EmperorDwg_1_1 -p:GeneratePackageOnBuild=false -nologo -v quiet
Copy-Item 'src\ACadSharp\bin\Release\net8.0\EmperorDwg_1_1.dll' (Join-Path $here 'EmperorDwg_1_1.dll')
Set-Location $here
Write-Host "Built: $here\EmperorDwg_1_1.dll  (copy it to lib\dwg\)"
