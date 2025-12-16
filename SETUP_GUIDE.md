# Setup Guide for yt2md Command

## Current Setup
- Python 3.13 virtual environment: `.venv-2`
- `yt2md` command installed in: `D:\repos\YouTubeToMarkdown\.venv-2\Scripts\yt2md.exe`

## Usage Options

### Option 1: Activate Virtual Environment (Recommended)
Always activate the virtual environment before using `yt2md`:

```powershell
& D:\repos\YouTubeToMarkdown\.venv-2\Scripts\Activate.ps1
yt2md --help
```

### Option 2: Use Full Path
Call the command using its full path:

```powershell
D:\repos\YouTubeToMarkdown\.venv-2\Scripts\yt2md.exe --help
```

### Option 3: Add to PATH Permanently
Add the Scripts directory to your system PATH:

#### Windows (PowerShell as Administrator):
```powershell
# Add to User PATH (recommended)
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$newPath = "D:\repos\YouTubeToMarkdown\.venv-2\Scripts"
if ($userPath -notlike "*$newPath*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$newPath", "User")
    Write-Host "Added to PATH. Please restart your terminal."
}
```

After adding to PATH, you can use `yt2md` from any directory without activation.

## Verification
Check which Python the command is using:

```powershell
where.exe yt2md
# Should show: D:\repos\YouTubeToMarkdown\.venv-2\Scripts\yt2md.exe

# Verify Python version
D:\repos\YouTubeToMarkdown\.venv-2\Scripts\python.exe --version
# Should show: Python 3.13.x
```

## Cleanup Performed
- ✅ Removed old `.venv` and `.venv-1` directories
- ✅ Uninstalled `yt2md` from Python 3.11 global installation
- ✅ Installed `yt2md` in Python 3.13 virtual environment (`.venv-2`)
- ✅ Removed temporary debug files
- ✅ All tests passing with new setup
