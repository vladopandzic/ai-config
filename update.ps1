# Brings this machine up to date with the rules pushed from another machine:
# pulls the repo, then runs install.ps1 so newly added guides get linked too.
#
#   & <repo folder>\update.ps1

param(
    [string] $HomeDirectory = $env:USERPROFILE
)

$ErrorActionPreference = 'Stop'

git -C $PSScriptRoot pull --ff-only
if ($LASTEXITCODE -ne 0)
{
    throw "git pull failed in $PSScriptRoot; resolve it there and run update.ps1 again."
}

& "$PSScriptRoot\install.ps1" -HomeDirectory $HomeDirectory
