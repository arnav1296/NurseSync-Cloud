# Build the React app against the Cognito pool, upload it to S3, and refresh CloudFront.
# Run from the repo root after `terraform apply`. Needs Node and the AWS CLI.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent

$pool   = terraform -chdir="$root\infra" output -raw cognito_user_pool_id
$client = terraform -chdir="$root\infra" output -raw cognito_client_id
$bucket = terraform -chdir="$root\infra" output -raw site_bucket
$dist   = terraform -chdir="$root\infra" output -raw cloudfront_distribution_id
$url    = terraform -chdir="$root\infra" output -raw app_url

# the API is on the same CloudFront domain, so the base URL is empty
@"
VITE_API_BASE_URL=
VITE_COGNITO_USER_POOL_ID=$pool
VITE_COGNITO_CLIENT_ID=$client
"@ | Set-Content -Encoding ascii "$root\frontend\.env.production"

Push-Location "$root\frontend"
try {
    npm install --no-audit --no-fund
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "build failed" }
} finally {
    Pop-Location
}

aws s3 sync "$root\frontend\dist" "s3://$bucket" --delete
aws cloudfront create-invalidation --distribution-id $dist --paths "/*" | Out-Null
Write-Host "Done. Open $url (CloudFront may take a minute to refresh)."
