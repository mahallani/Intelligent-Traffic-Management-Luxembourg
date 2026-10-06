$repoUrl = "https://github.com/lcodeca/LuSTScenario.git"
$targetFolder = "LuSTScenario"

if (Test-Path $targetFolder) {
    Write-Host "LuSTScenario existe deja."
} else {
    Write-Host "Telechargement de LuSTScenario..."
    git clone $repoUrl $targetFolder
    Write-Host "LuSTScenario telecharge avec succes."
}