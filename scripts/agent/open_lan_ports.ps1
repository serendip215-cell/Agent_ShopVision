#Requires -RunAsAdministrator

$rules = @(
    @{ Name = "ShopVision-Retrieval-8000"; Port = 8000 },
    @{ Name = "ShopVision-Model-8100"; Port = 8100 }
)

foreach ($rule in $rules) {
    if (-not (Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule `
            -DisplayName $rule.Name `
            -Direction Inbound `
            -Protocol TCP `
            -LocalPort $rule.Port `
            -Action Allow `
            -Profile Any | Out-Null
    }
}

Get-NetFirewallRule -DisplayName "ShopVision-*" |
    Select-Object DisplayName, Enabled, Direction, Action, Profile
