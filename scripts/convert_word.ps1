$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$manifest=Get-Content -Raw -Encoding UTF8 (Join-Path $projectRoot 'source_extract/manifest.json') | ConvertFrom-Json
$wordConvert=New-Object -ComObject Word.Application
$wordConvert.Visible=$false
$wordConvert.DisplayAlerts=0
try {
  foreach($item in $manifest) {
    $document=$wordConvert.Documents.Open((Join-Path $projectRoot $item.source),$false,$true)
    try {
      foreach($outputFormat in @(@('docx',16),@('html',10),@('pdf',17))) {
        $convertedPath=[string](Join-Path $projectRoot ('source_extract/'+$item.id+'.'+$outputFormat[0]))
        $format=[int]$outputFormat[1]
        $document.SaveAs([ref]$convertedPath,[ref]$format)
      }
      Write-Output ('Converted '+$item.id)
    } finally { $document.Close(0) }
  }
} finally { $wordConvert.Quit() }
