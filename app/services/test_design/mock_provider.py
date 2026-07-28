import hashlib

from .provider import TestDesignProvider
from .schemas import (
    CaseType,
    Priority,
    ScenarioType,
    TestCaseDraftData,
    TestDesignContext,
    TestDesignResult,
    TestPoint,
    TestPointCategory,
)


DOMAIN_RULES = (
    (
        "connection",
        (
            "connect",
            "reconnect",
            "bluetooth",
            "连接",
            "蓝牙",
        ),
        "Connection",
        "Validate connection and reconnect state transitions",
    ),
    (
        "audio",
        (
            "audio",
            "volume",
            "loudness",
            "音频",
            "音量",
            "响度",
        ),
        "Audio",
        "Validate audio control and observable output",
    ),
    (
        "power",
        (
            "charge",
            "charging",
            "battery",
            "power",
            "充电",
            "电量",
        ),
        "Power",
        "Validate power and battery state feedback",
    ),
    (
        "network",
        (
            "network",
            "api",
            "timeout",
            "网络",
            "超时",
        ),
        "Network",
        "Validate network response and timeout handling",
    ),
    (
        "permission",
        (
            "permission",
            "authorization",
            "access denied",
            "权限",
            "授权",
            "拒绝访问",
        ),
        "Security",
        "Validate permission and authorization handling",
    ),
    (
        "failure",
        (
            "fail",
            "failure",
            "exception",
            "error handling",
            "失败",
            "异常",
            "错误处理",
        ),
        "Reliability",
        "Validate failure and exception handling",
    ),
)
OTA_MARKERS = ("ota", "upgrade", "firmware update", "升级", "恢复")
MULTI_DEVICE_MARKERS = (
    "left and right",
    "earbuds",
    "multiple device",
    "multi-device",
    "左右耳",
    "多设备",
)


class MockTestDesignProvider(TestDesignProvider):
    provider_name = "mock"
    provider_model = None
    is_demo = True

    def generate(self, context: TestDesignContext) -> TestDesignResult:
        normalized = (
            f"{context.title}\n{context.requirement_text}".casefold()
        )
        domain, module, test_point_title = self._domain(normalized)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:6]
        scenarios = [
            ScenarioType.NORMAL,
            ScenarioType.NEGATIVE,
            ScenarioType.BOUNDARY,
        ]
        if any(marker in normalized for marker in OTA_MARKERS):
            scenarios.append(ScenarioType.RECOVERY)
        if any(marker in normalized for marker in MULTI_DEVICE_MARKERS):
            scenarios.append(ScenarioType.COMPATIBILITY)

        drafts = [
            self._draft(domain, module, digest, index, scenario)
            for index, scenario in enumerate(scenarios, start=1)
        ]
        test_points = [
            TestPoint(
                category={
                    "permission": TestPointCategory.SECURITY,
                    "failure": TestPointCategory.RELIABILITY,
                }.get(domain, TestPointCategory.FUNCTIONAL),
                title=test_point_title,
                description=(
                    f"Exercise observable mock {domain} behavior from the "
                    "provided sample requirement."
                ),
                priority=Priority.P0,
            ),
            TestPoint(
                category=TestPointCategory.BOUNDARY,
                title=f"Validate {domain} boundary handling",
                description=(
                    f"Check a bounded mock {domain} limit without using a "
                    "real device or production service."
                ),
                priority=Priority.P1,
            ),
        ]
        if ScenarioType.RECOVERY in scenarios:
            test_points.append(
                TestPoint(
                    category=TestPointCategory.RECOVERY,
                    title="Validate upgrade recovery behavior",
                    description=(
                        "Verify that the sample OTA flow exposes a bounded "
                        "and observable recovery state."
                    ),
                    priority=Priority.P0,
                )
            )
        if ScenarioType.COMPATIBILITY in scenarios:
            test_points.append(
                TestPoint(
                    category=TestPointCategory.COMPATIBILITY,
                    title="Validate multi-device compatibility",
                    description=(
                        "Compare observable mock states across sample devices."
                    ),
                    priority=Priority.P1,
                )
            )

        return TestDesignResult(
            summary=(
                f"Demo AI Design for a sample {domain} requirement. "
                "The output is deterministic and remains a human-reviewed "
                "draft."
            ),
            test_points=test_points,
            case_drafts=drafts,
            limitations=[
                "Generated from requirement text only and requires human review.",
                "Mock results do not confirm behavior on a real device.",
            ],
        )

    @staticmethod
    def _domain(text):
        for domain, markers, module, title in DOMAIN_RULES:
            if any(marker in text for marker in markers):
                return domain, module, title
        return (
            "functional",
            "General",
            "Validate sample functional behavior",
        )

    @staticmethod
    def _draft(domain, module, digest, index, scenario):
        scenario_label = scenario.value
        priority = (
            Priority.P0
            if scenario in {ScenarioType.NORMAL, ScenarioType.RECOVERY}
            else Priority.P1
        )
        expected = (
            f"The displayed mock {domain} status shows the expected "
            f"{scenario_label} value and no unreviewed TestCase is created."
        )
        return TestCaseDraftData(
            suggested_code=(
                f"TC_AI_{domain.upper()}_{digest.upper()}_{index:02d}"
            ),
            title=f"Validate sample {domain} {scenario_label} behavior",
            module=module,
            priority=priority,
            case_type=CaseType.CHECKLIST,
            scenario_type=scenario,
            precondition=(
                f"Mock {domain} fixture is available in a known sample state."
            ),
            steps=(
                f"1. Configure the mock {domain} fixture for the "
                f"{scenario_label} scenario.\n"
                "2. Trigger the bounded sample action.\n"
                "3. Record the displayed status."
            ),
            expected_result=expected,
        )
