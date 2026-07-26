param(
    [string]$BaseUrl = "http://127.0.0.1:5000"
)

$ErrorActionPreference = "Stop"

function Invoke-DemoApi {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [string]$Url,

        [Parameter(Mandatory = $true)]
        [int]$ExpectedStatus,

        [hashtable]$Body,

        [string]$Summary = ""
    )

    $parameters = @{
        Method = $Method
        Uri = $Url
        Headers = @{ Accept = "application/json" }
        ErrorAction = "Stop"
    }

    if ($null -ne $Body) {
        $parameters.ContentType = "application/json"
        $parameters.Body = $Body | ConvertTo-Json -Depth 6 -Compress
    }

    try {
        $response = Invoke-RestMethod @parameters
    }
    catch {
        $status = "unavailable"
        if ($null -ne $_.Exception.Response) {
            try {
                $status = [int]$_.Exception.Response.StatusCode
            }
            catch {
                $status = "http-error"
            }
        }
        throw "$Method $Url failed with status $status."
    }

    Write-Host "$Method $Url [$ExpectedStatus] $Summary"
    return $response
}

try {
    $rootUrl = $BaseUrl.TrimEnd("/")
    if (-not ($rootUrl.StartsWith("http://") -or $rootUrl.StartsWith("https://"))) {
        throw "BaseUrl must use http or https."
    }

    $apiUrl = "$rootUrl/api/v1"
    $suffix = "{0}{1:D6}" -f (Get-Date -Format "yyyyMMddHHmmss"), (Get-Random -Minimum 0 -Maximum 999999)

    $health = Invoke-DemoApi `
        -Method "GET" `
        -Url "$apiUrl/health" `
        -ExpectedStatus 200 `
        -Summary "health"
    if ($health.status -ne "ok") {
        throw "Health response did not report status=ok."
    }

    $testCases = Invoke-DemoApi `
        -Method "GET" `
        -Url "$apiUrl/test-cases?page=1&page_size=1" `
        -ExpectedStatus 200 `
        -Summary "demo TestCase list"
    $items = @($testCases.items)
    if ($items.Count -eq 0) {
        throw "Demo TestCase list is empty. Run flask --app run.py init-db first."
    }
    $versionId = [int]$items[0].version_id
    if ($versionId -le 0) {
        throw "Demo version_id is invalid."
    }

    $testCase = Invoke-DemoApi `
        -Method "POST" `
        -Url "$apiUrl/test-cases" `
        -ExpectedStatus 201 `
        -Summary "create TestCase" `
        -Body @{
            version_id = $versionId
            code = "TC_PS_SMOKE_$suffix"
            title = "Sample PowerShell API smoke TestCase"
            module = "Audio"
            priority = "P2"
            case_type = "checklist"
            precondition = "Use mock device state only."
            steps = "Run the sample PowerShell smoke workflow."
            expected_result = "The sample workflow records a result."
            status = "draft"
        }
    $testCaseId = [int]$testCase.id

    $execution = Invoke-DemoApi `
        -Method "POST" `
        -Url "$apiUrl/executions" `
        -ExpectedStatus 201 `
        -Summary "create failed Execution" `
        -Body @{
            test_case_id = $testCaseId
            result = "failed"
            actual_result = "Sample PowerShell smoke failure."
            tester = "PowerShell API Demo Tester"
            environment = "Local Demo Environment"
            notes = "Created by the PowerShell smoke script."
        }
    $executionId = [int]$execution.id

    $defect = Invoke-DemoApi `
        -Method "POST" `
        -Url "$apiUrl/defects" `
        -ExpectedStatus 201 `
        -Summary "create Defect" `
        -Body @{
            test_execution_id = $executionId
            code = "DEF_PS_$suffix"
            title = "Sample PowerShell API smoke defect"
            description = "Mock defect created by the PowerShell smoke workflow."
            component = "Audio"
            severity = "major"
            priority = "P2"
            status = "open"
            reproduction_steps = "Run the sample PowerShell API steps."
            observed_result = "The mock execution records a sample failure."
            reporter = "PowerShell API Demo Tester"
            assignee = $null
        }
    $defectId = [int]$defect.id

    $patchedDefect = Invoke-DemoApi `
        -Method "PATCH" `
        -Url "$apiUrl/defects/$defectId" `
        -ExpectedStatus 200 `
        -Summary "fix Defect" `
        -Body @{
            status = "fixed"
            resolution = "sample_powershell_fix"
            resolution_note = "Verified by the local PowerShell demo workflow."
        }
    if ($patchedDefect.status -ne "fixed") {
        throw "Patched Defect did not report status=fixed."
    }

    $null = Invoke-DemoApi `
        -Method "GET" `
        -Url "$apiUrl/test-cases/$testCaseId" `
        -ExpectedStatus 200 `
        -Summary "read TestCase id=$testCaseId"
    $null = Invoke-DemoApi `
        -Method "GET" `
        -Url "$apiUrl/executions/$executionId" `
        -ExpectedStatus 200 `
        -Summary "read Execution id=$executionId"
    $null = Invoke-DemoApi `
        -Method "GET" `
        -Url "$apiUrl/defects/$defectId" `
        -ExpectedStatus 200 `
        -Summary "read Defect id=$defectId"

    Write-Host "REST API V1 PowerShell smoke workflow passed."
    exit 0
}
catch {
    Write-Error "Smoke failed: $($_.Exception.Message)"
    exit 1
}
