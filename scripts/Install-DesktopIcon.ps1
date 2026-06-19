# ════════════════════════════════════════════════════════════════════
#  Install-DesktopIcon.ps1
#  Erstellt eine Desktop-Verknüpfung "PI Dashboard 2.0" mit Icon
#  Aufruf:  powershell -ExecutionPolicy Bypass -File Install-DesktopIcon.ps1
# ════════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"
$WarningPreference = "SilentlyContinue"

# ── Konfiguration ───────────────────────────────────────────────────
$ProjectDir      = "D:\Entwicklung\PI-Dashboard 2"
$StarterBat      = Join-Path $ProjectDir "scripts\Start-PiDashboard.bat"
$DesktopDir      = [Environment]::GetFolderPath("Desktop")
$ShortcutName    = "PI Dashboard 2.0.lnk"
$ShortcutPath    = Join-Path $DesktopDir $ShortcutName
$IcoPath         = Join-Path $ProjectDir "assets\pi-dashboard-icon.ico"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  PI Dashboard 2.0 - Desktop-Icon Installation" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ── 1) Pruefe Voraussetzungen ────────────────────────────────────────
Write-Host "[1/4] Pruefe Voraussetzungen..." -ForegroundColor Yellow
if (-not (Test-Path $StarterBat)) {
    Write-Host "  [FEHLT] Starter-Batch nicht gefunden: $StarterBat" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Starter gefunden: $StarterBat" -ForegroundColor Green
Write-Host "  [OK] Desktop: $DesktopDir" -ForegroundColor Green
Write-Host ""

# ── 2) ICO-Datei generieren ─────────────────────────────────────────
Write-Host "[2/4] Generiere Multi-Resolution ICO..." -ForegroundColor Yellow

Add-Type -AssemblyName System.Drawing

function New-PiIconFile {
    param([string]$OutPath)

    # Erstelle Bitmap in mehreren Aufloesungen
    $sizes = @(16, 32, 48, 64, 128, 256)
    $imageDataList = New-Object System.Collections.ArrayList

    foreach ($size in $sizes) {
        $bmp = New-Object System.Drawing.Bitmap $size, $size
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit

        # Hintergrund: dunkler Gradient
        $rect = New-Object System.Drawing.Rectangle 0, 0, $size, $size
        $bgBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush(
            $rect,
            [System.Drawing.Color]::FromArgb(255, 14, 18, 23),
            [System.Drawing.Color]::FromArgb(255, 28, 35, 51),
            45.0
        )
        $g.FillRectangle($bgBrush, $rect)

        # Inner border
        $borderPen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(255, 48, 54, 61), [Math]::Max(1, $size/80))
        $g.DrawRectangle($borderPen, 0, 0, $size-1, $size-1)

        # Pi-Symbol (griechischer Buchstabe)
        $piSize = [single]($size * 0.62)
        $fontStyleVal = [System.Drawing.FontStyle]::Bold -bor [System.Drawing.FontStyle]::Italic
        $piFont = New-Object System.Drawing.Font("Segoe UI", $piSize, $fontStyleVal, [System.Drawing.GraphicsUnit]::Pixel)
        $piBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 88, 166, 255))

        $sf = New-Object System.Drawing.StringFormat
        $sf.Alignment = [System.Drawing.StringAlignment]::Center
        $sf.LineAlignment = [System.Drawing.StringAlignment]::Center
        $textRect = New-Object System.Drawing.RectangleF 0, [single](-$size*0.05), [single]$size, [single]$size
        $g.DrawString([char]0x03C0, $piFont, $piBrush, $textRect, $sf)

        # "2.0" Badge oben rechts (nur ab 32px)
        if ($size -ge 32) {
            $badgeX = [int]($size * 0.62)
            $badgeY = [int]($size * 0.06)
            $badgeW = [int]($size * 0.32)
            $badgeH = [int]($size * 0.17)
            $badgeBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 210, 153, 34))
            $g.FillRectangle($badgeBrush, $badgeX, $badgeY, $badgeW, $badgeH)

            $badgeFontSize = [single]([Math]::Max(7, $size * 0.12))
            $badgeFont = New-Object System.Drawing.Font("Segoe UI", $badgeFontSize, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
            $badgeTextBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 14, 18, 23))
            $textRect2 = New-Object System.Drawing.RectangleF ([single]$badgeX), [single]($badgeY-1), [single]$badgeW, [single]$badgeH
            $g.DrawString("2.0", $badgeFont, $badgeTextBrush, $textRect2, $sf)
        }

        # Active Pulse dot unten links
        if ($size -ge 32) {
            $pulseBrush = New-Object System.Drawing.SolidBrush([System.Drawing.Color]::FromArgb(255, 210, 153, 34))
            $pulseSize = [Math]::Max(2, [int]($size * 0.06))
            $g.FillEllipse($pulseBrush, [int]($size*0.08), [int]($size*0.08), $pulseSize, $pulseSize)
        }

        $g.Dispose()

        # Konvertiere Bitmap zu PNG-Bytes (im Memory)
        $pngMs = New-Object System.IO.MemoryStream
        $bmp.Save($pngMs, [System.Drawing.Imaging.ImageFormat]::Png)
        $pngBytes = $pngMs.ToArray()
        $pngMs.Dispose()
        $bmp.Dispose()

        [void]$imageDataList.Add(@{
            Size = $size
            Bytes = $pngBytes
        })
    }

    # Schreibe Multi-Resolution ICO
    $icoMs = New-Object System.IO.MemoryStream
    $bw = New-Object System.IO.BinaryWriter $icoMs

    # ICONDIR (6 bytes): Reserved(2)=0, Type(2)=1, Count(2)
    $bw.Write([UInt16]0)
    $bw.Write([UInt16]1)
    $bw.Write([UInt16]$imageDataList.Count)

    # Header-Groesse: 6 + 16*Count
    $headerSize = 6 + 16 * $imageDataList.Count
    $offset = $headerSize

    # ICONDIRENTRY (16 bytes pro Eintrag)
    foreach ($img in $imageDataList) {
        $size = $img.Size
        $bytes = $img.Bytes
        $w = if ($size -ge 256) { [byte]0 } else { [byte]$size }
        $h = $w

        $bw.Write([byte]$w)
        $bw.Write([byte]$h)
        $bw.Write([byte]0)        # ColorCount
        $bw.Write([byte]0)        # Reserved
        $bw.Write([UInt16]1)      # Planes
        $bw.Write([UInt16]32)     # BitCount
        $bw.Write([UInt32]$bytes.Length)
        $bw.Write([UInt32]$offset)

        $offset += $bytes.Length
    }

    # Schreibe PNG-Bytes
    foreach ($img in $imageDataList) {
        $bw.Write($img.Bytes)
    }

    $bw.Flush()
    [System.IO.File]::WriteAllBytes($OutPath, $icoMs.ToArray())
    $icoMs.Dispose()
}

try {
    New-PiIconFile -OutPath $IcoPath
    $icoSize = (Get-Item $IcoPath).Length
    Write-Host "  [OK] ICO erstellt: $IcoPath ($icoSize bytes)" -ForegroundColor Green
} catch {
    Write-Host "  [FEHLER] ICO-Generierung: $_" -ForegroundColor Red
    $IcoPath = $null
}
Write-Host ""

# ── 3) Desktop-Verknuepfung erstellen ──────────────────────────────
Write-Host "[3/4] Erstelle Desktop-Verknuepfung..." -ForegroundColor Yellow

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $StarterBat
$Shortcut.WorkingDirectory = $ProjectDir
$Shortcut.WindowStyle = 7
$Shortcut.Description = "PI Dashboard 2.0 - Hermes-Style Web-Dashboard (startet Services + Browser)"

if ($IcoPath -and (Test-Path $IcoPath)) {
    $Shortcut.IconLocation = "$IcoPath,0"
    Write-Host "  [OK] Icon zugewiesen" -ForegroundColor Green
}

$Shortcut.Save()

[System.Runtime.InteropServices.Marshal]::ReleaseComObject($Shortcut) | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($WshShell) | Out-Null
[System.GC]::Collect() | Out-Null

Write-Host "  [OK] Verknuepfung: $ShortcutPath" -ForegroundColor Green
Write-Host ""

# ── 4) Verifiziere ──────────────────────────────────────────────────
Write-Host "[4/4] Verifiziere..." -ForegroundColor Yellow
if (Test-Path $ShortcutPath) {
    $fi = Get-Item $ShortcutPath
    Write-Host "  [OK] Verknuepfung existiert" -ForegroundColor Green
    Write-Host "        Pfad: $($fi.FullName)" -ForegroundColor Gray
    Write-Host "        Groesse: $($fi.Length) bytes" -ForegroundColor Gray
} else {
    Write-Host "  [FEHLT] Verknuepfung nicht gefunden" -ForegroundColor Red
    exit 1
}

if ($IcoPath -and (Test-Path $IcoPath)) {
    $icoFi = Get-Item $IcoPath
    Write-Host "  [OK] Icon-Datei existiert ($($icoFi.Length) bytes, Multi-Resolution)" -ForegroundColor Green
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host "  INSTALLATION ERFOLGREICH" -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Doppelklick auf '$ShortcutName' startet:" -ForegroundColor White
Write-Host "    1. Prueft ob Frontend/Backend laufen" -ForegroundColor Gray
Write-Host "    2. Startet sie ggf. automatisch" -ForegroundColor Gray
Write-Host "    3. Oeffnet Browser mit dem PI Dashboard" -ForegroundColor Gray
Write-Host ""
