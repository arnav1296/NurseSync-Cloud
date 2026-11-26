# One-off: load the demo ward (staff, patients, notes, handoffs, alerts) into the empty
# RDS database and create a Cognito login for every staff member.
#   .\scripts\seed-demo.ps1 -Password "nursesync123"
param(
    [Parameter(Mandatory = $true)][string]$Password,
    [switch]$SubscribeEmails
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

$url   = terraform -chdir="$root\infra" output -raw app_url
$token = terraform -chdir="$root\infra" output -raw internal_api_token

$body = @{ password = $Password; subscribe_emails = [bool]$SubscribeEmails } | ConvertTo-Json
$result = Invoke-RestMethod -Method Post -Uri "$url/api/internal/seed" `
    -Headers @{ "X-Internal-Token" = $token } -ContentType "application/json" -Body $body
$result | ConvertTo-Json -Depth 4
Write-Host "Sign in at $url with any of the logins above and the password you chose."
