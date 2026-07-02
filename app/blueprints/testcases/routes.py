from flask import Blueprint, render_template


bp = Blueprint("testcases", __name__, url_prefix="/testcases")


@bp.get("/")
def index():
    columns = ["用例标题", "模块", "优先级", "类型"]
    rows = [
        ["Sample playback checklist", "播放", "P1", "Checklist"],
        ["Mock microphone capture checklist", "录音", "P2", "Checklist"],
        ["Demo Bluetooth reconnect checklist", "连接", "P1", "Checklist"],
    ]
    return render_template(
        "module_list.html",
        page_title="Checklist 用例管理",
        page_description="管理模拟 checklist 用例，后续可补充步骤、预期结果和导入导出。",
        action_label="新建用例",
        columns=columns,
        rows=rows,
    )
