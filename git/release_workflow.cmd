@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem AVI Pro repository release workflow helper.
rem Non-destructive by design: never runs destructive reset or clean commands.

set "COMMAND=%~1"
set "ARG1=%~2"
set "ARG2=%~3"

if "%COMMAND%"=="" goto :usage

if /I "%COMMAND%"=="status" goto :status
if /I "%COMMAND%"=="sync" goto :sync
if /I "%COMMAND%"=="feature" goto :feature
if /I "%COMMAND%"=="fix" goto :fix
if /I "%COMMAND%"=="hotfix" goto :hotfix
if /I "%COMMAND%"=="release" goto :release

echo ERROR: Unknown command "%COMMAND%".
goto :usage

:usage
echo.
echo Usage:
echo   release_workflow.cmd status
echo   release_workflow.cmd sync
echo   release_workflow.cmd feature ^<feature-name^>
echo   release_workflow.cmd fix ^<problem-name^>
echo   release_workflow.cmd hotfix ^<problem-name^>
echo   release_workflow.cmd release ^<MAJOR.MINOR.PATCH^> "Release title"
echo.
echo Branch prefixes allowed: feature/, fix/, hotfix/
exit /b 2

:require_git_repo
git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 (
    echo ERROR: This directory is not inside a Git repository.
    exit /b 1
)
exit /b 0

:current_branch
for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%B"
if not defined CURRENT_BRANCH (
    echo ERROR: Could not determine the current branch.
    exit /b 1
)
exit /b 0

:require_origin
git remote get-url origin >nul 2>nul
if errorlevel 1 (
    echo ERROR: No 'origin' remote is configured. Add one before syncing, pushing, or releasing.
    exit /b 1
)
exit /b 0

:require_clean
git diff --quiet --exit-code
if errorlevel 1 (
    echo ERROR: Working tree has unstaged changes. Commit or stash them first.
    exit /b 1
)
git diff --cached --quiet --exit-code
if errorlevel 1 (
    echo ERROR: Index has staged changes. Commit or unstage them first.
    exit /b 1
)
exit /b 0

:fetch_origin
call :require_origin || exit /b 1
git fetch origin
if errorlevel 1 (
    echo ERROR: git fetch origin failed.
    exit /b 1
)
exit /b 0

:ensure_not_main_for_dev
call :current_branch || exit /b 1
if /I "%CURRENT_BRANCH%"=="main" (
    echo ERROR: You are on main. Do not develop directly on main.
    echo        Create feature/, fix/, or hotfix/ branch from latest main.
    exit /b 1
)
exit /b 0

:status
call :require_git_repo || exit /b 1
call :current_branch || exit /b 1
echo Current branch: %CURRENT_BRANCH%
echo.
git status
if errorlevel 1 exit /b 1
echo.
echo Remotes:
git remote -v
if errorlevel 1 exit /b 1
exit /b 0

:sync
call :require_git_repo || exit /b 1
call :require_clean || exit /b 1
call :fetch_origin || exit /b 1
call :current_branch || exit /b 1
if /I "%CURRENT_BRANCH%"=="main" (
    git pull --ff-only origin main
) else (
    git pull --ff-only
)
if errorlevel 1 (
    echo ERROR: Sync failed. Resolve the issue and rerun after the working tree is clean.
    exit /b 1
)
exit /b 0

:feature
call :create_branch feature "%ARG1%"
exit /b %ERRORLEVEL%

:fix
call :create_branch fix "%ARG1%"
exit /b %ERRORLEVEL%

:hotfix
call :create_branch hotfix "%ARG1%"
exit /b %ERRORLEVEL%

:create_branch
set "PREFIX=%~1"
set "NAME=%~2"
if "%NAME%"=="" (
    echo ERROR: Missing branch name. Example: release_workflow.cmd %PREFIX% linked-room-selection
    exit /b 2
)
echo %NAME%| findstr /R /C:"^[a-z0-9][a-z0-9._-]*$" >nul
if errorlevel 1 (
    echo ERROR: Invalid branch name "%NAME%". Use lowercase letters, numbers, dots, underscores, and hyphens.
    exit /b 2
)
call :require_git_repo || exit /b 1
call :require_clean || exit /b 1
call :fetch_origin || exit /b 1
set "NEW_BRANCH=%PREFIX%/%NAME%"
git show-ref --verify --quiet "refs/heads/%NEW_BRANCH%"
if not errorlevel 1 (
    echo ERROR: Local branch "%NEW_BRANCH%" already exists.
    exit /b 1
)
git ls-remote --exit-code --heads origin "%NEW_BRANCH%" >nul 2>nul
if not errorlevel 1 (
    echo ERROR: Remote branch "origin/%NEW_BRANCH%" already exists.
    exit /b 1
)
git checkout main
if errorlevel 1 (
    echo ERROR: Could not checkout main.
    exit /b 1
)
git pull --ff-only origin main
if errorlevel 1 (
    echo ERROR: Could not fast-forward main from origin/main.
    exit /b 1
)
git checkout -b "%NEW_BRANCH%"
if errorlevel 1 (
    echo ERROR: Could not create branch "%NEW_BRANCH%".
    exit /b 1
)
echo Created branch %NEW_BRANCH% from latest main.
exit /b 0

:release
set "VERSION=%ARG1%"
set "TITLE=%~3"
if "%VERSION%"=="" (
    echo ERROR: Missing version. Example: release_workflow.cmd release 1.1.0 "Add Workset Manager"
    exit /b 2
)
echo %VERSION%| findstr /R /C:"^[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*$" >nul
if errorlevel 1 (
    echo ERROR: Version must match MAJOR.MINOR.PATCH, for example 1.1.0.
    exit /b 2
)
if "%TITLE%"=="" set "TITLE=Release %VERSION%"
call :require_git_repo || exit /b 1
call :require_clean || exit /b 1
call :fetch_origin || exit /b 1
call :current_branch || exit /b 1
if /I not "%CURRENT_BRANCH%"=="main" (
    echo ERROR: Releases must be created from main after review and merge.
    exit /b 1
)
git pull --ff-only origin main
if errorlevel 1 (
    echo ERROR: Could not fast-forward main from origin/main.
    exit /b 1
)
set "TAG=v%VERSION%"
git rev-parse -q --verify "refs/tags/%TAG%" >nul 2>nul
if not errorlevel 1 (
    echo ERROR: Tag %TAG% already exists locally. Never overwrite release tags.
    exit /b 1
)
git ls-remote --exit-code --tags origin "%TAG%" >nul 2>nul
if not errorlevel 1 (
    echo ERROR: Tag %TAG% already exists on origin. Never overwrite release tags.
    exit /b 1
)
echo Ready to create annotated tag %TAG%.
echo This script will create and push the tag, but it will NOT create a GitHub Release.
echo Create the GitHub Release manually after confirming release notes and testing status.
choice /M "Create and push tag %TAG% now"
if errorlevel 2 (
    echo Release tagging cancelled.
    exit /b 0
)
git tag -a "%TAG%" -m "Version %VERSION% - %TITLE%"
if errorlevel 1 (
    echo ERROR: Failed to create tag %TAG%.
    exit /b 1
)
git push origin "%TAG%"
if errorlevel 1 (
    echo ERROR: Failed to push tag %TAG%.
    exit /b 1
)
echo Tag %TAG% pushed. Now create a GitHub Release with release notes and testing status.
exit /b 0
