# 安装依赖并构建前端（Windows 本机自用），自动选择最快的下载源。与 scripts/setup.sh 行为一致。
#
#   scripts\setup.cmd                          安装后端依赖（含 OCR）+ 前端依赖并构建
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1   同上（不经 setup.cmd 时）
#
# 环境变量（与 setup.sh 相同）：
#   NO_OCR=1                 不安装 OCR（截图凭证只按文件名识别）
#   MIRROR=auto|cn|global    下载源：测速选择（默认）/ 强制国内镜像 / 强制官方源
#   FRONTEND_BUILD=local     本地构建前端（默认）；prebuilt：只用 CI 预构建前端（无需 Node.js）；auto：优先预构建
#   SKIP_FRONTEND=1          跳过前端
#   PYPI_INDEX / NPM_REGISTRY / PYTHON_MIRROR   手工指定下载源，跳过测速
#
# 需要：uv；本地构建前端时还需要 Node.js >= 20 与 pnpm。版本严格按 uv.lock / pnpm-lock.yaml 安装。
# 兼容 Windows PowerShell 5.1；本文件需保存为带 BOM 的 UTF-8，否则 5.1 会按系统代码页读错中文。

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 3.0

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root  # 在仓库目录内运行，避免读取调用者目录中的 uv.toml / .npmrc

# 慢速网络下放宽下载超时（uv 默认 30 秒）
if (-not $env:UV_HTTP_TIMEOUT) { $env:UV_HTTP_TIMEOUT = '300' }
if (-not $env:UV_HTTP_RETRIES) { $env:UV_HTTP_RETRIES = '5' }

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Green }

function Fail([string]$Message) {
    Write-Host $Message -ForegroundColor Red
    exit 1
}

# 运行外部命令，非 0 退出码即中止（PowerShell 不会因外部命令失败自动停止）
function Invoke-Native([string]$Label, [scriptblock]$Command) {
    & $Command
    if ($LASTEXITCODE -ne 0) { Fail "$Label 失败（退出码 $LASTEXITCODE）" }
}

function Test-Command([string]$Name) { [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

# 运行外部命令并丢弃其 stderr。PowerShell 5.1 在 ErrorActionPreference=Stop 下重定向原生命令的 stderr
# 会把每行包装成错误并中止脚本，所以只在本函数内放宽为 Continue；调用方自行检查 $LASTEXITCODE
function Invoke-Quiet([scriptblock]$Command) {
    $ErrorActionPreference = 'Continue'
    & $Command 2>$null
}

# ---------- 下载源选择（对应 scripts/lib/mirrors.sh） ----------

$Mirror = if ($env:MIRROR) { $env:MIRROR } else { 'auto' }
$ProbeBytes = 499999

$PypiCandidates = @(
    'https://pypi.org/simple',
    'https://mirrors.aliyun.com/pypi/simple',
    'https://pypi.tuna.tsinghua.edu.cn/simple'
)
$NpmCandidates = @(
    'https://registry.npmjs.org',
    'https://registry.npmmirror.com'
)
$PythonCandidates = @(
    'https://github.com/astral-sh/python-build-standalone/releases/download',
    'https://registry.npmmirror.com/-/binary/python-build-standalone'
)

# 测速样本与 mirrors.sh 相同：各源上同一个真实文件（只取前 500KB），只比较速度，与本机平台无关
$PypiSample = 'packages/eb/47/c95ffc2009878c7aac0c5e08528022dcb885933252a88b5f170058014464/pydantic-2.13.5-py3-none-any.whl'
$NpmSample = 'lodash/-/lodash-4.17.21.tgz'
$PythonSample = '20250317/cpython-3.12.9+20250317-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz'

function Get-ProbeUrl([string]$Url) {
    if ($Url -eq 'https://pypi.org/simple') { return "https://files.pythonhosted.org/$PypiSample" }
    if ($Url -like '*/simple') { return ($Url -replace '/simple$', '') + "/$PypiSample" }
    if ($Url -like '*python-build-standalone*') { return "$Url/$PythonSample" }
    if ($Url -like '*registry.npm*') { return "$Url/$NpmSample" }
    return $Url
}

# 下载速度（KB/s，整数）；失败返回 0。用 Windows 10 起自带的 curl.exe（不是 PowerShell 的 curl 别名）
function Get-ProbeKbps([string]$Url, [int]$TimeoutSeconds) {
    if (-not (Test-Command 'curl.exe')) { return 0 }
    $probe = Get-ProbeUrl $Url
    $result = Invoke-Quiet {
        curl.exe -sL -r "0-$ProbeBytes" -o NUL --max-time $TimeoutSeconds `
            -w '%{http_code} %{size_download} %{speed_download}' $probe
    }
    if (-not $result) { return 0 }
    $parts = "$result".Trim() -split '\s+'
    if ($parts.Count -lt 3 -or ($parts[0] -ne '200' -and $parts[0] -ne '206')) { return 0 }
    if ([double]$parts[1] -le 0) { return 0 }
    return [int][math]::Floor([double]$parts[2] / 1024)
}

# global 取第一个（官方），cn 取第二个（首选国内镜像），auto 取下载最快
function Select-Fastest([string]$Label, [string[]]$Candidates, [int]$TimeoutSeconds = 5) {
    if ($Mirror -eq 'global') { return $Candidates[0] }
    if ($Mirror -eq 'cn') { return $Candidates[1] }
    $best = $Candidates[0]
    $bestKbps = 0
    foreach ($url in $Candidates) {
        $kbps = Get-ProbeKbps $url $TimeoutSeconds
        $shown = if ($kbps -gt 0) { "$kbps KB/s" } else { '不可用' }
        Write-Host ('    {0,-8} {1,-60} {2}' -f $Label, $url, $shown)
        if ($kbps -gt $bestKbps) { $best = $url; $bestKbps = $kbps }
    }
    return $best
}

function Select-Mirrors {
    Write-Step "选择下载源（MIRROR=$Mirror）"
    $script:PypiIndex = if ($env:PYPI_INDEX) { $env:PYPI_INDEX } else { Select-Fastest 'PyPI' $PypiCandidates }
    $script:NpmRegistry = if ($env:NPM_REGISTRY) { $env:NPM_REGISTRY } else { Select-Fastest 'npm' $NpmCandidates }
    $script:PythonMirror = ''
    if ($null -ne $env:PYTHON_MIRROR) {
        $script:PythonMirror = $env:PYTHON_MIRROR
    } else {
        # 已有 uv 可用的 Python 3.12 时无需下载解释器，跳过测速
        $found = Invoke-Quiet { uv python find 3.12 }
        if ($LASTEXITCODE -ne 0 -or -not $found) {
            $picked = Select-Fastest 'Python' $PythonCandidates 10
            if ($picked -ne $PythonCandidates[0]) { $script:PythonMirror = $picked }
        }
    }
    Write-Host "    → PyPI:    $script:PypiIndex"
    Write-Host "    → npm:     $script:NpmRegistry"
    $shownPython = if ($script:PythonMirror) { $script:PythonMirror } else { '官方 GitHub（或使用已安装的 3.12）' }
    Write-Host "    → Python:  $shownPython"
}

# ---------- 后端 ----------

function Install-Backend {
    $backend = Join-Path $Root 'backend'
    $python = Join-Path $backend '.venv\Scripts\python.exe'
    $extras = @()
    if ($env:NO_OCR -ne '1') { $extras = @('--extra', 'ocr') }
    $requirements = [System.IO.Path]::GetTempFileName()

    Write-Step "安装后端依赖（$script:PypiIndex）"
    if ($script:PythonMirror) { $env:UV_PYTHON_INSTALL_MIRROR = $script:PythonMirror }
    try {
        if (-not (Test-Path $python)) {
            Invoke-Native '创建虚拟环境' { uv venv --quiet --python 3.12 (Join-Path $backend '.venv') }
        }
        # 按锁文件导出精确版本（含哈希），再从选中的源安装，保证与锁文件一致
        Invoke-Native '导出锁定依赖' {
            uv export --quiet --project $backend --frozen --no-dev --no-emit-project `
                --format requirements-txt @extras -o $requirements
        }
        Invoke-Native '安装后端依赖' {
            uv pip install --quiet --python $python --index-url $script:PypiIndex -r $requirements
        }
    } finally {
        Remove-Item $requirements -ErrorAction SilentlyContinue
    }
    Invoke-Native '安装后端' { uv pip install --quiet --python $python --no-deps -e $backend }
}

# ---------- 前端 ----------

function Build-FrontendLocally {
    $frontend = Join-Path $Root 'frontend'
    # 直接调用 pnpm.cmd：pnpm.ps1 会被默认的脚本执行策略拦下
    if (-not (Test-Command 'pnpm.cmd')) {
        Fail '未找到 pnpm，请先安装 Node.js 20+，再执行 npm.cmd install -g pnpm（或设 FRONTEND_BUILD=prebuilt 免装 Node.js）'
    }
    Write-Step "安装前端依赖（$script:NpmRegistry）"
    # 慢速网络：放宽超时并重试；corepack 按 package.json 固定的 pnpm 版本下载，不查询最新版
    $env:COREPACK_NPM_REGISTRY = $script:NpmRegistry
    $env:COREPACK_ENABLE_DOWNLOAD_PROMPT = '0'
    $env:npm_config_fetch_retries = '5'
    $env:npm_config_fetch_timeout = '300000'
    Invoke-Native '安装前端依赖' {
        pnpm.cmd --dir $frontend install --frozen-lockfile --silent --registry $script:NpmRegistry
    }
    Write-Step '构建前端'
    Invoke-Native '构建前端' { pnpm.cmd --dir $frontend build | Out-Null }
}

# 下载 CI 预构建的前端（Release「frontend-dist」），校验与本地前端代码版本一致（对应 scripts/fetch-frontend.sh）
# 成功返回 $true；网络失败或版本不一致返回 $false（调用方可退回本地构建）
function Get-PrebuiltFrontend {
    $url = if ($env:FRONTEND_DIST_URL) { $env:FRONTEND_DIST_URL } else {
        'https://github.com/lsgoodlionel/Invoice-sorting/releases/download/frontend-dist/frontend-dist.tar.gz'
    }
    if (-not (Test-Command 'git')) { Write-Host '无法确定前端代码版本（需要 git）'; return $false }
    $key = Invoke-Quiet { git log -1 --format=%H -- frontend }
    if (-not $key) { Write-Host '无法确定前端代码版本（需要 git 仓库）'; return $false }
    foreach ($tool in 'curl.exe', 'tar.exe') {
        if (-not (Test-Command $tool)) { Write-Host "缺少 $tool（Windows 10 1803 起自带）"; return $false }
    }

    $work = Join-Path ([System.IO.Path]::GetTempPath()) ("invoice-frontend-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $work | Out-Null
    try {
        Write-Step "下载预构建前端（$url）"
        $archive = Join-Path $work 'frontend-dist.tar.gz'
        & curl.exe -fL -# --retry 5 --retry-all-errors --retry-delay 3 --connect-timeout 20 --max-time 900 -o $archive $url
        if ($LASTEXITCODE -ne 0) { Write-Host '预构建前端下载失败'; return $false }
        & tar.exe -xzf $archive -C $work
        if ($LASTEXITCODE -ne 0) { Write-Host '预构建前端解压失败'; return $false }
        $builtFile = Join-Path $work 'BUILD_COMMIT'
        $built = if (Test-Path $builtFile) { (Get-Content $builtFile -Raw).Trim() } else { '' }
        if ($built -ne $key) {
            $shown = if ($built) { $built } else { '未知' }
            Write-Host "预构建前端版本（$shown）与代码（$key）不一致"
            return $false
        }
        if (-not (Test-Path (Join-Path $work 'dist\index.html'))) { Write-Host '预构建前端内容不完整'; return $false }
        $target = Join-Path $Root 'frontend\dist'
        if (Test-Path $target) { Remove-Item $target -Recurse -Force }
        Move-Item (Join-Path $work 'dist') $target
        Write-Step "已使用预构建前端（$($key.Substring(0, 7))）"
        return $true
    } finally {
        Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Install-Frontend {
    if ($env:SKIP_FRONTEND -eq '1') { return }
    switch ($env:FRONTEND_BUILD) {
        'prebuilt' { if (-not (Get-PrebuiltFrontend)) { Fail '预构建前端不可用' } }
        'auto' { if (-not (Get-PrebuiltFrontend)) { Build-FrontendLocally } }
        default { Build-FrontendLocally }
    }
}

# ---------- 入口 ----------

if (-not (Test-Command 'uv')) {
    Fail '未找到 uv，请先安装：powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"（装完重开终端）'
}
Select-Mirrors
Install-Backend
Install-Frontend
Write-Step "完成。启动：$Root\backend\.venv\Scripts\invoice-sorting.exe"
