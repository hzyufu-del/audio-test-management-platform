from flask import Blueprint, render_template


bp = Blueprint("defects", __name__, url_prefix="/defects")


@bp.get("/")
def index():
    columns = ["缺陷标题", "严重级别", "状态", "关联版本"]
    rows = [
        ["Mock playback interruption issue", "High", "Open", "demo_build_alpha"],
        ["Sample recording noise observation", "Medium", "In Review", "demo_build_alpha"],
        ["Demo reconnect timeout note", "Low", "Deferred", "sample_build_beta"],
    ]
    return render_template(
        "module_list.html",
        page_title="缺陷管理",
        page_description="维护模拟缺陷记录，不使用任何真实缺陷编号或内部信息。",
        action_label="新建缺陷",
        columns=columns,
        rows=rows,
    )
