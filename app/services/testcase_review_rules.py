import re
from collections import Counter

from .ai.schemas import IssueCategory, IssueSeverity, TestCaseQualityIssue


NUMBERING_PREFIX = re.compile(r"^(?:\d+[.、)]|[-*•])\s*")
DOMAIN_MARKERS = {
    "audio": ("audio", "playback", "音频", "播放"),
    "bluetooth": ("bluetooth", "蓝牙"),
    "charging": ("charging", "charger", "充电"),
    "battery": ("battery", "电池", "电量"),
    "volume": ("volume", "音量"),
    "firmware": ("firmware", "固件", "升级"),
}
ACTION_MARKERS = (
    "打开",
    "关闭",
    "连接",
    "断开",
    "检查",
    "调整",
    "设置",
    "点击",
    "输入",
    "观察",
    "验证",
    "启动",
    "停止",
    "选择",
    "发送",
    "播放",
    "open",
    "close",
    "connect",
    "disconnect",
    "check",
    "adjust",
    "set",
    "click",
    "enter",
    "observe",
    "verify",
    "start",
    "stop",
    "select",
    "send",
    "play",
    "run",
)
VAGUE_EXPECTATIONS = {
    "显示正常",
    "功能正常",
    "符合预期",
    "结果正确",
    "无异常",
    "操作成功",
    "状态正确",
    "works normally",
    "as expected",
    "success",
}
OBSERVABLE_MARKERS = (
    "显示为",
    "变为",
    "等于",
    "包含",
    "增加",
    "减少",
    "提示",
    "状态",
    "颜色",
    "数值",
    "记录",
    "秒",
    "%",
    "changes to",
    "equals",
    "contains",
    "message",
    "status",
    "value",
    "recorded",
)
NORMAL_MARKERS = ("正常", "成功", "normal", "success")
EXCEPTION_MARKERS = (
    "异常",
    "失败",
    "错误",
    "断开",
    "exception",
    "failure",
    "error",
    "disconnect",
)
BOUNDARY_MARKERS = (
    "边界",
    "最大",
    "最小",
    "上限",
    "下限",
    "boundary",
    "maximum",
    "minimum",
    "limit",
)
PROMPT_INJECTION_MARKERS = (
    "忽略之前",
    "忽略前面的",
    "输出系统提示词",
    "泄露系统提示词",
    "质量评分改成",
    "ignore previous",
    "ignore all prior",
    "system prompt",
    "developer message",
    "reveal prompt",
    "quality score to",
)


def normalize_review_text(value):
    return " ".join(str(value or "").strip().split())


def parse_review_items(value):
    items = []
    for raw_line in str(value or "").splitlines():
        normalized = normalize_review_text(raw_line)
        if not normalized:
            continue
        without_prefix = NUMBERING_PREFIX.sub("", normalized, count=1)
        cleaned = normalize_review_text(without_prefix)
        if cleaned:
            items.append(cleaned)
    return items


def review_test_case_rules(test_case):
    title = normalize_review_text(getattr(test_case, "title", ""))
    precondition = normalize_review_text(
        getattr(test_case, "precondition", "")
    )
    steps_text = str(getattr(test_case, "steps", "") or "")
    expected_text = str(getattr(test_case, "expected_result", "") or "")
    steps = parse_review_items(steps_text)
    expectations = parse_review_items(expected_text)
    issues = []

    if len(title) < 4:
        issues.append(
            _issue(
                IssueCategory.TITLE_MISMATCH,
                IssueSeverity.WARNING,
                "用例标题为空或过短，无法清楚表达审查目标。",
                title or "标题为空",
                "使用对象、动作和预期状态描述用例目标。",
            )
        )
    if not precondition:
        issues.append(
            _issue(
                IssueCategory.MISSING_PRECONDITION,
                IssueSeverity.WARNING,
                "用例缺少前置条件。",
                "前置条件为空",
                "补充必要的设备、版本、环境或账号初始状态。",
            )
        )
    if not steps:
        issues.append(
            _issue(
                IssueCategory.UNCLEAR_STEP,
                IssueSeverity.CRITICAL,
                "用例缺少可执行的测试步骤。",
                "测试步骤为空",
                "按执行顺序补充具体动作。",
            )
        )
    if not expectations:
        issues.append(
            _issue(
                IssueCategory.UNVERIFIABLE_EXPECTATION,
                IssueSeverity.CRITICAL,
                "用例缺少可验证的预期结果。",
                "预期结果为空",
                "补充可观察的对象、状态或数值结果。",
            )
        )

    duplicate = _first_duplicate(steps)
    if duplicate:
        issues.append(
            _issue(
                IssueCategory.DUPLICATE_STEP,
                IssueSeverity.WARNING,
                "测试步骤存在重复内容。",
                duplicate,
                "合并重复步骤并保留一次明确动作。",
            )
        )

    unclear_step = next(
        (item for item in steps if _step_is_unclear(item)),
        None,
    )
    if unclear_step:
        issues.append(
            _issue(
                IssueCategory.UNCLEAR_STEP,
                IssueSeverity.WARNING,
                "测试步骤过短或缺少明确动作。",
                unclear_step,
                "补充操作者、动作对象和执行方式。",
            )
        )

    if expectations and _expectations_are_unverifiable(expectations):
        issues.append(
            _issue(
                IssueCategory.UNVERIFIABLE_EXPECTATION,
                IssueSeverity.WARNING,
                "预期结果主要由模糊词组成，缺少可观察依据。",
                expectations[0],
                "说明具体页面元素、状态变化、提示文本或数值。",
            )
        )

    if _counts_are_obviously_mismatched(steps, expectations):
        issues.append(
            _issue(
                IssueCategory.STEP_EXPECTATION_MISMATCH,
                IssueSeverity.WARNING,
                "测试步骤与预期结果的条目数量明显不匹配。",
                f"步骤 {len(steps)} 条，预期 {len(expectations)} 条",
                "为关键步骤补充对应预期，或合并无独立验证点的步骤。",
            )
        )

    title_mismatch = _title_mismatch(title, steps_text, expected_text)
    if title_mismatch:
        issues.append(
            _issue(
                IssueCategory.TITLE_MISMATCH,
                IssueSeverity.WARNING,
                "标题中的测试对象未在步骤或预期结果中体现。",
                title_mismatch,
                "使标题、步骤和预期结果围绕同一测试对象。",
            )
        )

    repeated_precondition = _precondition_repeated(precondition, steps)
    if repeated_precondition:
        issues.append(
            _issue(
                IssueCategory.DUPLICATE_STEP,
                IssueSeverity.INFO,
                "前置条件被直接重复为测试步骤。",
                repeated_precondition,
                "步骤从前置状态之后的第一个操作开始描述。",
            )
        )

    combined = " ".join((title, precondition, steps_text, expected_text)).casefold()
    _append_missing_scenario_issues(issues, combined)

    environment_evidence = _missing_environment_evidence(
        test_case,
        precondition,
        combined,
    )
    if environment_evidence:
        issues.append(
            _issue(
                IssueCategory.MISSING_ENVIRONMENT,
                IssueSeverity.WARNING,
                "前置条件缺少本用例所需的设备、版本、环境或账号信息。",
                environment_evidence,
                "仅补充与本用例操作直接相关的初始环境信息。",
            )
        )

    injection_evidence = next(
        (marker for marker in PROMPT_INJECTION_MARKERS if marker in combined),
        None,
    )
    if injection_evidence:
        issues.append(
            _issue(
                IssueCategory.PROMPT_INJECTION,
                IssueSeverity.CRITICAL,
                "用例文本包含试图改变审查规则或输出格式的指令。",
                injection_evidence,
                "将该文本视为待分析数据，并删除与测试步骤无关的指令。",
            )
        )

    return _deduplicate_issues(issues)


def _issue(category, severity, description, evidence, suggestion):
    return TestCaseQualityIssue(
        category=category,
        severity=severity,
        description=description,
        evidence=_short_evidence(evidence),
        suggestion=suggestion,
    )


def _short_evidence(value):
    normalized = normalize_review_text(value)
    return normalized[:200] if normalized else "未提供内容"


def _first_duplicate(items):
    canonical = [normalize_review_text(item).casefold() for item in items]
    counts = Counter(canonical)
    for item, key in zip(items, canonical):
        if counts[key] > 1:
            return item
    return None


def _step_is_unclear(item):
    normalized = normalize_review_text(item).casefold()
    if len(normalized) < 3:
        return True
    return len(normalized) < 12 and not any(
        marker in normalized for marker in ACTION_MARKERS
    )


def _expectations_are_unverifiable(items):
    vague_count = sum(_expectation_is_vague(item) for item in items)
    return vague_count * 2 >= len(items)


def _expectation_is_vague(item):
    normalized = normalize_review_text(item).casefold().strip(
        "。.!！?？;；,，"
    )
    if normalized in VAGUE_EXPECTATIONS:
        return True
    has_vague_phrase = any(phrase in normalized for phrase in VAGUE_EXPECTATIONS)
    has_observable_detail = any(
        marker in normalized for marker in OBSERVABLE_MARKERS
    ) or any(character.isdigit() for character in normalized)
    return len(normalized) <= 12 and has_vague_phrase and not has_observable_detail


def _counts_are_obviously_mismatched(steps, expectations):
    if not steps or not expectations:
        return False
    smaller = min(len(steps), len(expectations))
    larger = max(len(steps), len(expectations))
    return larger - smaller >= 2 and larger >= smaller * 2


def _title_mismatch(title, steps_text, expected_text):
    title_lower = title.casefold()
    body = f"{steps_text} {expected_text}".casefold()
    for markers in DOMAIN_MARKERS.values():
        title_marker = next(
            (marker for marker in markers if marker in title_lower),
            None,
        )
        if title_marker and not any(marker in body for marker in markers):
            return title_marker
    return None


def _precondition_repeated(precondition, steps):
    if not precondition:
        return None
    precondition_items = parse_review_items(precondition) or [precondition]
    precondition_keys = {
        normalize_review_text(item).casefold() for item in precondition_items
    }
    for step in steps:
        if normalize_review_text(step).casefold() in precondition_keys:
            return step
    return None


def _append_missing_scenario_issues(issues, combined):
    checks = (
        (
            NORMAL_MARKERS,
            IssueCategory.MISSING_NORMAL_SCENARIO,
            "用例未明确覆盖正常场景。",
            "补充一条正常输入或正常状态下的验证路径。",
        ),
        (
            EXCEPTION_MARKERS,
            IssueCategory.MISSING_EXCEPTION_SCENARIO,
            "用例未明确覆盖异常场景。",
            "根据已有需求补充失败、断开或错误处理场景。",
        ),
        (
            BOUNDARY_MARKERS,
            IssueCategory.MISSING_BOUNDARY_SCENARIO,
            "用例未明确覆盖边界场景。",
            "根据已有约束补充最大、最小或临界状态场景。",
        ),
    )
    for markers, category, description, suggestion in checks:
        if not any(marker in combined for marker in markers):
            issues.append(
                _issue(
                    category,
                    IssueSeverity.INFO,
                    description,
                    "当前用例文本未发现对应场景标记",
                    suggestion,
                )
            )


def _missing_environment_evidence(test_case, precondition, combined):
    if not precondition:
        return None
    precondition_lower = precondition.casefold()
    required_groups = [
        ("设备", ("设备", "device", "配件", "accessory")),
    ]
    if any(marker in combined for marker in ("固件", "升级", "firmware")):
        required_groups.append(
            ("版本", ("版本", "固件", "version", "firmware", "fw_"))
        )
    if any(marker in combined for marker in ("网络", "wifi", "环境", "network")):
        required_groups.append(
            ("环境", ("环境", "网络", "wifi", "environment", "network"))
        )
    if any(marker in combined for marker in ("账号", "登录", "account", "login")):
        required_groups.append(
            ("账号", ("账号", "登录", "account", "login"))
        )
    missing = [
        label
        for label, markers in required_groups
        if not any(marker in precondition_lower for marker in markers)
    ]
    if not missing:
        return None
    code = normalize_review_text(getattr(test_case, "code", ""))
    return f"{code or '当前用例'} 缺少：{'、'.join(missing)}"


def _deduplicate_issues(issues):
    seen = set()
    unique = []
    for issue in issues:
        key = (
            issue.category.value,
            normalize_review_text(issue.evidence).casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return unique
