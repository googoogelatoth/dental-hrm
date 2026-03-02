# ===================================================================
# PowerShell Script: Deploy New ENCRYPTION_KEY to Cloud Run
# ===================================================================
#
# Usage: 
#   1. Generate new key first: python generate_new_key.py
#   2. Copy the key from NEW_ENCRYPTION_KEY.txt
#   3. Edit this script and paste the key in $NEW_KEY variable
#   4. Run: .\deploy_new_encryption_key.ps1
#
# ===================================================================

# 🔐 PASTE YOUR NEW ENCRYPTION KEY HERE (from NEW_ENCRYPTION_KEY.txt)
$NEW_KEY = "YOUR_NEW_KEY_HERE"

# Configuration
$SERVICE_NAME = "mini-hrm"
$REGION = "asia-southeast1"

Write-Host "=" -ForegroundColor Cyan
Write-Host "🚀 Deploying New ENCRYPTION_KEY to Cloud Run" -ForegroundColor Cyan
Write-Host "=" -ForegroundColor Cyan
Write-Host ""

# Validation
if ($NEW_KEY -eq "YOUR_NEW_KEY_HERE") {
    Write-Host "❌ ERROR: Please edit this script and paste your new key!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Steps:" -ForegroundColor Yellow
    Write-Host "  1. Run: python generate_new_key.py" -ForegroundColor Yellow
    Write-Host "  2. Copy the key from output or NEW_ENCRYPTION_KEY.txt" -ForegroundColor Yellow
    Write-Host "  3. Edit this script (line 17) and paste the key" -ForegroundColor Yellow
    Write-Host "  4. Run this script again" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "Service: $SERVICE_NAME" -ForegroundColor Green
Write-Host "Region: $REGION" -ForegroundColor Green
Write-Host "Key Length: $($NEW_KEY.Length) characters" -ForegroundColor Green
Write-Host ""

# Confirm before proceeding
$confirm = Read-Host "Deploy new ENCRYPTION_KEY? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "❌ Deployment cancelled" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "⏳ Updating Cloud Run service..." -ForegroundColor Yellow

# Update Cloud Run service
gcloud run services update $SERVICE_NAME `
    --region $REGION `
    --set-env-vars "ENCRYPTION_KEY=$NEW_KEY"

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ Deployment successful!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next Steps:" -ForegroundColor Cyan
    Write-Host "  1. Run SQL script: clear_encrypted_data.sql" -ForegroundColor White
    Write-Host "  2. Test the application: visit /my-profile" -ForegroundColor White
    Write-Host "  3. Verify no 'InvalidToken' errors in logs" -ForegroundColor White
    Write-Host "  4. Ask users to re-enter their personal data" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "❌ Deployment failed!" -ForegroundColor Red
    Write-Host "Check the error message above and try again" -ForegroundColor Red
    Write-Host ""
    exit 1
}
