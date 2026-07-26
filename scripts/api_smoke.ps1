param(
    [string]$BaseUrl = "http://127.0.0.1:5000",

    [ValidateRange(1, 300)]
    [int]$TimeoutSec = 15
)

$ErrorActionPreference = "Stop"

function Get-ResponseBody {
    param(
        [object]$Response
    )

    if ($null -eq $Response) {
        return ""
    }

    if ($null -ne $Response.Content) {
        if ($Response.Content -is [string]) {
            return [string]$Response.Content
        }
        if (
            $Response.Content.PSObject.Methods.Name -contains
            "ReadAsStringAsync"
        ) {
            return $Response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        }
    }

    if ($Response.PSObject.Methods.Name -contains "GetResponseStream") {
        $stream = $Response.GetResponseStream()
        if ($null -eq $stream) {
            return ""
        }
        $reader = New-Object System.IO.StreamReader($stream)
        try {
            return $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
            $stream.Dispose()
        }
    }

    return ""
}

function Get-HeaderValue {
    param(
        [object]$Headers,
        [string]$Name
    )

    if ($null -eq $Headers) {
        return $null
    }

    try {
        $value = $Headers[$Name]
        if ($null -eq $value) {
            return $null
        }
        return [string]($value -join ",")
    }
    catch {
        return $null
    }
}

function Invoke-ApiRequest {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Method,

        [Parameter(Mandatory = $true)]
        [string]$Uri,

        [int]$ExpectedStatus = 200,

        [object]$Body = $null,

        [string]$ContentType = "application/json",

        [int]$TimeoutSec = 15,

        [switch]$RequireLocation,

        [string]$Summary = ""
    )

    $parameters = @{
        Method = $Method
        Uri = $Uri
        Headers = @{ Accept = "application/json" }
        TimeoutSec = $TimeoutSec
        ErrorAction = "Stop"
    }
    if ((Get-Command Invoke-WebRequest).Parameters.ContainsKey("UseBasicParsing")) {
        $parameters.UseBasicParsing = $true
    }

    if ($null -ne $Body) {
        $parameters.ContentType = $ContentType
        if (
            $ContentType -eq "application/json" -and
            -not ($Body -is [string])
        ) {
            $parameters.Body = $Body | ConvertTo-Json -Depth 6 -Compress
        }
        else {
            $parameters.Body = [string]$Body
        }
    }

    $actualStatus = $null
    $responseBody = ""
    $responseHeaders = $null

    try {
        $response = Invoke-WebRequest @parameters
        $actualStatus = [int]$response.StatusCode
        $responseBody = [string]$response.Content
        $responseHeaders = $response.Headers
    }
    catch {
        $errorResponse = $_.Exception.Response
        if ($null -eq $errorResponse) {
            throw "$Method $Uri failed: service unavailable or request timed out."
        }

        try {
            $actualStatus = [int]$errorResponse.StatusCode
        }
        catch {
            throw "$Method $Uri failed: HTTP status was unavailable."
        }

        if (-not [string]::IsNullOrWhiteSpace($_.ErrorDetails.Message)) {
            $responseBody = $_.ErrorDetails.Message
        }
        else {
            try {
                $responseBody = Get-ResponseBody -Response $errorResponse
            }
            catch {
                $responseBody = ""
            }
        }
        $responseHeaders = $errorResponse.Headers
    }

    if ($actualStatus -ne $ExpectedStatus) {
        throw "$Method $Uri expected status $ExpectedStatus but received $actualStatus."
    }

    if ($RequireLocation) {
        $location = Get-HeaderValue -Headers $responseHeaders -Name "Location"
        if ([string]::IsNullOrWhiteSpace($location)) {
            throw "$Method $Uri returned status $actualStatus without Location."
        }
    }

    if ([string]::IsNullOrWhiteSpace($responseBody)) {
        throw "$Method $Uri returned an empty response body."
    }

    try {
        $payload = $responseBody | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw "$Method $Uri returned a non-JSON response."
    }

    Write-Host "$Method $Uri [$actualStatus] $Summary"
    return $payload
}

try {
    $rootUrl = $BaseUrl.TrimEnd("/")
    if (-not ($rootUrl.StartsWith("http://") -or $rootUrl.StartsWith("https://"))) {
        throw "BaseUrl must use http or https."
    }

    $apiUrl = "$rootUrl/api/v1"
    $suffix = "{0}{1:D6}" -f (Get-Date -Format "yyyyMMddHHmmss"), (Get-Random -Minimum 0 -Maximum 999999)

    $health = Invoke-ApiRequest `
        -Method "GET" `
        -Uri "$apiUrl/health" `
        -ExpectedStatus 200 `
        -TimeoutSec $TimeoutSec `
        -Summary "health"
    if ($health.status -ne "ok") {
        throw "Health response did not report status=ok."
    }

    $testCases = Invoke-ApiRequest `
        -Method "GET" `
        -Uri "$apiUrl/test-cases?page=1&page_size=1" `
        -ExpectedStatus 200 `
        -TimeoutSec $TimeoutSec `
        -Summary "demo TestCase list"
    $items = @($testCases.items)
    if ($items.Count -eq 0) {
        throw "Demo TestCase list is empty. Run flask --app run.py init-db first."
    }
    $versionId = [int]$items[0].version_id
    if ($versionId -le 0) {
        throw "Demo version_id is invalid."
    }

    $null = Invoke-ApiRequest `
        -Method "POST" `
        -Uri "$apiUrl/test-cases" `
        -ExpectedStatus 415 `
        -Body "{}" `
        -ContentType "text/plain" `
        -TimeoutSec $TimeoutSec `
        -Summary "reject unsupported media type"

    $null = Invoke-ApiRequest `
        -Method "POST" `
        -Uri "$apiUrl/test-cases" `
        -ExpectedStatus 422 `
        -Body @{} `
        -TimeoutSec $TimeoutSec `
        -Summary "reject invalid TestCase"

    $testCaseBody = @{
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
    $testCase = Invoke-ApiRequest `
        -Method "POST" `
        -Uri "$apiUrl/test-cases" `
        -ExpectedStatus 201 `
        -Body $testCaseBody `
        -TimeoutSec $TimeoutSec `
        -RequireLocation `
        -Summary "create TestCase"
    $testCaseId = [int]$testCase.id

    $null = Invoke-ApiRequest `
        -Method "POST" `
        -Uri "$apiUrl/test-cases" `
        -ExpectedStatus 409 `
        -Body $testCaseBody `
        -TimeoutSec $TimeoutSec `
        -Summary "reject duplicate TestCase"

    $execution = Invoke-ApiRequest `
        -Method "POST" `
        -Uri "$apiUrl/executions" `
        -ExpectedStatus 201 `
        -TimeoutSec $TimeoutSec `
        -RequireLocation `
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

    $defect = Invoke-ApiRequest `
        -Method "POST" `
        -Uri "$apiUrl/defects" `
        -ExpectedStatus 201 `
        -TimeoutSec $TimeoutSec `
        -RequireLocation `
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

    $patchedDefect = Invoke-ApiRequest `
        -Method "PATCH" `
        -Uri "$apiUrl/defects/$defectId" `
        -ExpectedStatus 200 `
        -TimeoutSec $TimeoutSec `
        -Summary "fix Defect" `
        -Body @{
            status = "fixed"
            resolution = "sample_powershell_fix"
            resolution_note = "Verified by the local PowerShell demo workflow."
        }
    if ($patchedDefect.status -ne "fixed") {
        throw "Patched Defect did not report status=fixed."
    }

    $null = Invoke-ApiRequest `
        -Method "GET" `
        -Uri "$apiUrl/test-cases/$testCaseId" `
        -ExpectedStatus 200 `
        -TimeoutSec $TimeoutSec `
        -Summary "read TestCase id=$testCaseId"
    $null = Invoke-ApiRequest `
        -Method "GET" `
        -Uri "$apiUrl/executions/$executionId" `
        -ExpectedStatus 200 `
        -TimeoutSec $TimeoutSec `
        -Summary "read Execution id=$executionId"
    $null = Invoke-ApiRequest `
        -Method "GET" `
        -Uri "$apiUrl/defects/$defectId" `
        -ExpectedStatus 200 `
        -TimeoutSec $TimeoutSec `
        -Summary "read Defect id=$defectId"

    Write-Host "REST API V1 PowerShell smoke workflow passed."
    exit 0
}
catch {
    [Console]::Error.WriteLine("Smoke failed: $($_.Exception.Message)")
    exit 1
}
