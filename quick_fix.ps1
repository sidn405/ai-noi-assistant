# Quick Fix and Deploy Script for Windows
# Run this in PowerShell from your ai_noi_assistant directory

Write-Host "=================================="
Write-Host "AI NOI Assistant - Quick Fix"
Write-Host "=================================="
Write-Host ""

# Check if we're in the right directory
if (-not (Test-Path "main.py")) {
    Write-Host "ERROR: main.py not found!" -ForegroundColor Red
    Write-Host "Please run this script from your ai_noi_assistant directory."
    exit 1
}

Write-Host "✓ Found main.py" -ForegroundColor Green

# Create backup
Write-Host "Creating backup of main.py..."
Copy-Item "main.py" "main.py.backup"
Write-Host "✓ Backup created: main.py.backup" -ForegroundColor Green

# Check if we need to apply the fix
$content = Get-Content "main.py" -Raw
if ($content -match "metadata = Column\(JSON") {
    Write-Host ""
    Write-Host "⚠️  Found the SQLAlchemy error!" -ForegroundColor Yellow
    Write-Host "The 'metadata' column needs to be renamed to 'extra_data'"
    Write-Host ""
    
    # Apply fix
    $content = $content -replace "metadata = Column\(JSON, nullable=True\)", "extra_data = Column(JSON, nullable=True)  # Renamed from 'metadata' (reserved by SQLAlchemy)"
    Set-Content "main.py" -Value $content
    
    Write-Host "✓ Fix applied!" -ForegroundColor Green
    Write-Host ""
} elseif ($content -match "extra_data = Column\(JSON") {
    Write-Host "✓ main.py already has the fix applied!" -ForegroundColor Green
    Write-Host ""
} else {
    Write-Host "⚠️  Could not find the Analytics model in main.py" -ForegroundColor Yellow
    Write-Host "You may need to manually update the file."
    Write-Host ""
}

# Git operations
Write-Host "Committing fix to git..."
git add main.py
git commit -m "Fix: Rename metadata column to extra_data (SQLAlchemy conflict)"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Committed!" -ForegroundColor Green
    Write-Host ""
    
    Write-Host "Pushing to GitHub..."
    git push origin main
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Pushed to GitHub!" -ForegroundColor Green
        Write-Host ""
        Write-Host "=================================="
        Write-Host "SUCCESS!"
        Write-Host "=================================="
        Write-Host ""
        Write-Host "Railway will automatically detect the change and redeploy."
        Write-Host "Check your Railway dashboard in 1-2 minutes."
        Write-Host ""
        Write-Host "Your app should now deploy successfully!"
        Write-Host ""
    } else {
        Write-Host "❌ Push failed" -ForegroundColor Red
        Write-Host "Please push manually: git push origin main"
    }
} else {
    Write-Host "⚠️  Nothing to commit (may already be committed)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Try pushing: git push origin main"
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Check Railway logs for successful deployment"
Write-Host "2. Visit your Railway URL to test the dashboard"
Write-Host "3. Run 'railway run python init_db.py' to setup database"
Write-Host ""