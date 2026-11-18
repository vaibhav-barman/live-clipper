# Hands-off from PowerShell:  .\clip.ps1 <link> [--clips 5] [--out ~\folder]
# Windows twin of scripts/clip. Runs Claude Code headless with the live-clipper autopilot.
if ($args.Count -lt 1) { Write-Host "usage: clip <link> [--clips N] [--out DIR] [--minutes M] [--rush]"; exit 1 }
$root = Split-Path -Parent $PSScriptRoot
claude -p "/live-clipper:live-clipper $($args -join ' ')" `
  --plugin-dir "$root" `
  --permission-mode acceptEdits `
  --allowedTools "Bash Read Write Edit Glob Grep Skill Agent TodoWrite mcp__plugin_live-clipper_clipper mcp__clipper"
exit $LASTEXITCODE
