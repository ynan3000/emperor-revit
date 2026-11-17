#!/usr/bin/env bash
# Builds lib/dwg/EmperorDwg_1_1.dll from source.
# Needs: git and the .NET 8 SDK (or newer). Run from this folder: ./build.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ACAD_COMMIT=0acbe974b865afb5ff3b256d5e13a6862574c438   # ACadSharp 3.8.51
WORK="$HERE/_build"
rm -rf "$WORK"
git clone --quiet https://github.com/DomCR/ACadSharp.git "$WORK/ACadSharp"
cd "$WORK/ACadSharp"
git checkout --quiet "$ACAD_COMMIT"
git submodule update --init --recursive --quiet
git apply "$HERE/acadsharp-emperor.patch"
cp -r "$HERE/Emperor" src/ACadSharp/Emperor
dotnet build src/ACadSharp/ACadSharp.csproj -c Release -f net8.0 -p:AssemblyName=EmperorDwg_1_1 -p:GeneratePackageOnBuild=false -nologo -v quiet
cp src/ACadSharp/bin/Release/net8.0/EmperorDwg_1_1.dll "$HERE/EmperorDwg_1_1.dll"
echo "Built: $HERE/EmperorDwg_1_1.dll  (copy it to lib/dwg/)"
