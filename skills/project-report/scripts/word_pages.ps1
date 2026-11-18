param([Parameter(Mandatory)][string]$Src, [string]$PagesOut, [string]$Pdf)
# Opens a .docx in Microsoft Word, writes the page number of every Heading 1
# (numbering like "3. " stripped) to $PagesOut as JSON, and optionally exports a PDF.
$w = New-Object -ComObject Word.Application
$w.Visible = $false
try {
  $d = $w.Documents.Open((Resolve-Path $Src).Path, $false, $false)
  $d.Repaginate()
  $map = @{}
  foreach ($para in $d.Paragraphs) {
    if ($para.Style.NameLocal -eq 'Heading 1') {
      $t = $para.Range.Text.Trim() -replace '^\d+\.\s*', ''
      $map[$t] = $para.Range.Information(1)   # wdActiveEndAdjustedPageNumber
    }
  }
  "TOTAL_PAGES=" + $d.ComputeStatistics(2)
  $json = $map | ConvertTo-Json -Compress
  "PAGES=" + $json
  if ($PagesOut) { [IO.File]::WriteAllText($PagesOut, $json) }
  if ($Pdf) { $d.ExportAsFixedFormat($Pdf, 17); "PDF=" + $Pdf }
  $d.Close($false)
} finally { $w.Quit() }
