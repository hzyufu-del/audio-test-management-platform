from flask import Blueprint, render_template


bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    stats = [
        {"label": "项目数", "value": 3, "hint": "mock projects"},
        {"label": "用例数", "value": 24, "hint": "sample checklist cases"},
        {"label": "已执行数", "value": 18, "hint": "demo execution records"},
        {"label": "缺陷数", "value": 5, "hint": "mock defect records"},
    ]

    recent_items = [
        {"module": "项目", "text": "Demo Audio Earbuds 测试项目已创建"},
        {"module": "用例", "text": "Sample ANC checklist 等待补充步骤"},
        {"module": "Log", "text": "sample_audio_check.log 已加入占位列表"},
    ]

    return render_template("dashboard/index.html", stats=stats, recent_items=recent_items)
