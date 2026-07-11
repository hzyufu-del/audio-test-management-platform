from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, case, distinct, func
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import Defect, Project, TestCase, TestExecution, Version


RESULTS = ("passed", "failed", "blocked", "skipped")
DEFECT_STATUSES = ("open", "fixed", "closed", "rejected")
SEVERITIES = ("blocker", "critical", "major", "minor")
CURRENT_DEFECT_STATUSES = ("open", "fixed")
CRITICAL_SEVERITIES = ("blocker", "critical")
RANGE_DAYS = {"7d": 7, "30d": 30}


def _percentage(numerator, denominator):
    if not denominator:
        return None
    return round(numerator * 100 / denominator, 1)


def _range_start(range_key, now):
    days = RANGE_DAYS.get(range_key)
    if days is None:
        return None
    start_date = now.date() - timedelta(days=days - 1)
    return datetime.combine(start_date, time.min)


def _day_key(value):
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _execution_scope(project_id, version_id, range_start=None):
    conditions = []
    if project_id is not None:
        conditions.append(Version.project_id == project_id)
    if version_id is not None:
        conditions.append(Version.id == version_id)
    if range_start is not None:
        conditions.append(TestExecution.executed_at >= range_start)
    return conditions


def _version_scope(project_id, version_id):
    conditions = []
    if project_id is not None:
        conditions.append(Version.project_id == project_id)
    if version_id is not None:
        conditions.append(Version.id == version_id)
    return conditions


def _scope_counts(project_id, version_id):
    project_query = db.select(func.count(distinct(Project.id)))
    version_query = db.select(func.count(distinct(Version.id)))
    testcase_query = db.select(func.count(distinct(TestCase.id))).where(
        TestCase.status != "archived"
    )

    if version_id is not None:
        project_query = project_query.join(Version).where(Version.id == version_id)
        version_query = version_query.where(Version.id == version_id)
        testcase_query = testcase_query.where(TestCase.version_id == version_id)
    elif project_id is not None:
        project_query = project_query.where(Project.id == project_id)
        version_query = version_query.where(Version.project_id == project_id)
        testcase_query = testcase_query.join(Version).where(
            Version.project_id == project_id
        )

    row = db.session.execute(
        db.select(
            project_query.scalar_subquery(),
            version_query.scalar_subquery(),
            testcase_query.scalar_subquery(),
        )
    ).one()
    return {"projects": row[0], "versions": row[1], "test_cases": row[2]}


def _execution_summary(project_id, version_id, range_start):
    query = (
        db.select(
            func.count(distinct(TestExecution.id)).label("total"),
            *[
                func.count(
                    distinct(
                        case(
                            (TestExecution.result == result, TestExecution.id),
                        )
                    )
                ).label(result)
                for result in RESULTS
            ],
            func.count(
                distinct(
                    case(
                        (
                            and_(
                                TestExecution.result == "failed",
                                Defect.id.is_not(None),
                            ),
                            TestExecution.id,
                        )
                    )
                )
            ).label("failed_with_defect"),
        )
        .select_from(TestExecution)
        .join(TestCase)
        .join(Version)
        .outerjoin(Defect)
        .where(*_execution_scope(project_id, version_id, range_start))
    )
    row = db.session.execute(query).one()
    by_result = {result: getattr(row, result) for result in RESULTS}
    decisive = by_result["passed"] + by_result["failed"]
    return {
        "total": row.total,
        "by_result": by_result,
        "pass_rate": _percentage(by_result["passed"], decisive),
        "fail_rate": _percentage(by_result["failed"], decisive),
        "failed_with_defect_count": row.failed_with_defect,
        "failed_with_defect_rate": _percentage(
            row.failed_with_defect,
            by_result["failed"],
        ),
    }


def _trend(project_id, version_id, range_key, range_start, now):
    query = (
        db.select(
            func.date(TestExecution.executed_at).label("day"),
            TestExecution.result,
            func.count(TestExecution.id).label("count"),
        )
        .select_from(TestExecution)
        .join(TestCase)
        .join(Version)
        .where(*_execution_scope(project_id, version_id, range_start))
        .group_by(func.date(TestExecution.executed_at), TestExecution.result)
        .order_by(func.date(TestExecution.executed_at))
    )
    rows = db.session.execute(query).all()

    if range_start is not None:
        first_date = range_start.date()
    elif rows:
        first_date = date.fromisoformat(_day_key(rows[0].day))
    else:
        first_date = now.date()

    labels = []
    cursor = first_date
    while cursor <= now.date():
        labels.append(cursor.isoformat())
        cursor += timedelta(days=1)

    counts = {label: {result: 0 for result in RESULTS} for label in labels}
    for row in rows:
        day = _day_key(row.day)
        if day in counts:
            counts[day][row.result] = row.count

    failed = [counts[label]["failed"] for label in labels]
    fail_rate = []
    for label in labels:
        passed = counts[label]["passed"]
        daily_failed = counts[label]["failed"]
        fail_rate.append(_percentage(daily_failed, passed + daily_failed))

    return {
        "labels": labels,
        "failed": failed,
        "fail_rate": fail_rate,
        "show_rate": any(value is not None for value in fail_rate),
        "range_key": range_key,
    }


def _version_quality(project_id, version_id, range_start):
    execution_condition = TestExecution.test_case_id == TestCase.id
    if range_start is not None:
        execution_condition = and_(
            execution_condition,
            TestExecution.executed_at >= range_start,
        )

    query = (
        db.select(
            Version.id.label("version_id"),
            Version.name.label("version_name"),
            Version.code.label("version_code"),
            Project.name.label("project_name"),
            func.count(distinct(TestExecution.id)).label("executions"),
            *[
                func.count(
                    distinct(
                        case(
                            (TestExecution.result == result, TestExecution.id),
                        )
                    )
                ).label(result)
                for result in ("passed", "failed", "blocked")
            ],
        )
        .select_from(Version)
        .join(Project)
        .outerjoin(TestCase, TestCase.version_id == Version.id)
        .outerjoin(TestExecution, execution_condition)
        .where(*_version_scope(project_id, version_id))
        .group_by(Version.id, Version.name, Version.code, Project.name)
    )
    execution_rows = db.session.execute(query).all()

    period_defect_id = (
        Defect.id
        if range_start is None
        else case((Defect.created_at >= range_start, Defect.id))
    )
    defect_query = (
        db.select(
            Version.id.label("version_id"),
            Defect.status,
            Defect.severity,
            func.count(distinct(Defect.id)).label("count"),
            func.count(distinct(period_defect_id)).label("period_count"),
        )
        .select_from(Defect)
        .join(TestExecution)
        .join(TestCase)
        .join(Version)
        .where(*_version_scope(project_id, version_id))
        .group_by(Version.id, Defect.status, Defect.severity)
    )
    defect_rows = db.session.execute(defect_query).all()

    defect_by_version = {}
    status_totals = {status: 0 for status in DEFECT_STATUSES}
    severity_totals = {severity: 0 for severity in SEVERITIES}
    period_total = 0
    for row in defect_rows:
        metrics = defect_by_version.setdefault(
            row.version_id,
            {"open_defects": 0, "critical_risks": 0, "total": 0},
        )
        metrics["total"] += row.count
        period_total += row.period_count
        status_totals[row.status] = status_totals.get(row.status, 0) + row.count
        severity_totals[row.severity] = severity_totals.get(row.severity, 0) + row.count
        if row.status in CURRENT_DEFECT_STATUSES:
            metrics["open_defects"] += row.count
            if row.severity in CRITICAL_SEVERITIES:
                metrics["critical_risks"] += row.count

    quality = []
    for row in execution_rows:
        risks = defect_by_version.get(
            row.version_id,
            {"open_defects": 0, "critical_risks": 0, "total": 0},
        )
        decisive = row.passed + row.failed
        quality.append(
            {
                "version_id": row.version_id,
                "project_name": row.project_name,
                "version_name": row.version_name,
                "version_code": row.version_code,
                "executions": row.executions,
                "passed": row.passed,
                "failed": row.failed,
                "blocked": row.blocked,
                "pass_rate": _percentage(row.passed, decisive),
                "open_defects": risks["open_defects"],
                "critical_risks": risks["critical_risks"],
                "total_defects": risks["total"],
            }
        )

    quality.sort(
        key=lambda row: (
            -row["critical_risks"],
            -row["failed"],
            row["project_name"],
            row["version_name"],
        )
    )
    defect_versions = [
        {
            "label": f'{row["project_name"]} / {row["version_name"]}',
            "count": row["total_defects"],
        }
        for row in quality
        if row["total_defects"]
    ]
    return quality, status_totals, severity_totals, defect_versions, period_total


def _attention_items(project_id, version_id, range_start):
    failed_query = (
        db.select(TestExecution)
        .join(TestCase)
        .join(Version)
        .options(
            joinedload(TestExecution.testcase)
            .joinedload(TestCase.version)
            .joinedload(Version.project)
        )
        .where(
            TestExecution.result.in_(("failed", "blocked")),
            *_execution_scope(project_id, version_id, range_start),
        )
        .order_by(TestExecution.executed_at.desc(), TestExecution.id.desc())
        .limit(5)
    )
    executions = db.session.scalars(failed_query).all()

    defect_query = (
        db.select(Defect)
        .join(TestExecution)
        .join(TestCase)
        .join(Version)
        .options(
            joinedload(Defect.execution)
            .joinedload(TestExecution.testcase)
            .joinedload(TestCase.version)
            .joinedload(Version.project)
        )
        .where(
            Defect.status.in_(CURRENT_DEFECT_STATUSES),
            Defect.severity.in_(CRITICAL_SEVERITIES),
            *_version_scope(project_id, version_id),
        )
        .order_by(Defect.updated_at.desc(), Defect.id.desc())
        .limit(5)
    )
    defects = db.session.scalars(defect_query).all()

    execution_items = []
    for execution in executions:
        testcase = execution.testcase
        execution_items.append(
            {
                "id": execution.id,
                "result": execution.result,
                "test_case_code": execution.test_case_code_snapshot,
                "test_case_title": execution.test_case_title_snapshot,
                "version_name": testcase.version.name,
                "project_name": testcase.version.project.name,
                "executed_at": execution.executed_at,
            }
        )

    defect_items = []
    for defect in defects:
        testcase = defect.execution.testcase
        defect_items.append(
            {
                "id": defect.id,
                "code": defect.code,
                "title": defect.title,
                "severity": defect.severity,
                "status": defect.status,
                "version_name": testcase.version.name,
                "project_name": testcase.version.project.name,
            }
        )
    return {"executions": execution_items, "defects": defect_items}


def build_dashboard(project_id=None, version_id=None, range_key="30d", now=None):
    """Build the Dashboard V1 read model from aggregate queries."""
    now = now or datetime.utcnow()
    range_start = _range_start(range_key, now)

    scope_counts = _scope_counts(project_id, version_id)
    execution = _execution_summary(project_id, version_id, range_start)
    trend = _trend(project_id, version_id, range_key, range_start, now)
    quality, by_status, by_severity, by_version, period_total = _version_quality(
        project_id,
        version_id,
        range_start,
    )
    attention = _attention_items(project_id, version_id, range_start)

    open_count = sum(by_status[status] for status in CURRENT_DEFECT_STATUSES)
    critical_risk_count = sum(row["critical_risks"] for row in quality)
    range_labels = {"7d": "最近 7 天", "30d": "最近 30 天", "all": "全部时间"}

    return {
        "scope": {
            "project_id": project_id,
            "version_id": version_id,
            "range_key": range_key,
            "range_label": range_labels[range_key],
        },
        "scope_counts": scope_counts,
        "execution": execution,
        "trend": trend,
        "defects": {
            "open_count": open_count,
            "critical_risk_count": critical_risk_count,
            "period_new_count": period_total,
            "by_status": by_status,
            "by_severity": by_severity,
            "by_version": by_version,
        },
        "version_quality": quality,
        "attention": attention,
    }
