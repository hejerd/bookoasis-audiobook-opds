param([string]$TaskSourceRoot = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference='Stop'
$taskMapRoots = @(
    @{From=[Environment]::GetFolderPath('UserProfile'); To='/build/home'},
    @{From=$env:CARGO_HOME; To='/build/cargo'},
    @{From=$env:RUSTUP_HOME; To='/build/rustup'},
    @{From=[IO.Path]::GetFullPath($TaskSourceRoot); To='/build/readest'}
)
# Preserve Android link flags set by cargo-mobile/Tauri in this build.
$taskRustFlags = @('-Clink-arg=-landroid','-Clink-arg=-llog','-Clink-arg=-lOpenSLES')
if ($env:CARGO_ENCODED_RUSTFLAGS) {
    $taskRustFlags = @($env:CARGO_ENCODED_RUSTFLAGS -split [char]31)
} elseif ($env:RUSTFLAGS) {
    $taskRustFlags = @($env:RUSTFLAGS -split '\s+' | Where-Object { $_ })
}
foreach ($taskMap in $taskMapRoots) {
    if (!$taskMap.From) { continue }
    foreach ($taskPrefix in @($taskMap.From,$taskMap.From.Replace('\','/')) | Select-Object -Unique) {
        $taskRustFlags += '--remap-path-prefix=' + $taskPrefix.TrimEnd('/','\') + '=' + $taskMap.To
    }
}
$env:CARGO_ENCODED_RUSTFLAGS = $taskRustFlags -join [char]31
