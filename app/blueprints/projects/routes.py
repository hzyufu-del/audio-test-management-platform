from flask import Blueprint, render_template


bp = Blueprint("projects", __name__, url_prefix="/projects")


@bp.get("/")
def index():
    columns = ["项目名称", "项目代号", "状态", "说明"]
    rows = [
        ["Demo Audio Earbuds", "MOCK-AUDIO-01", "进行中", "模拟真无线耳机测试项目"],
        ["Sample Speaker Lab", "MOCK-AUDIO-02", "计划中", "模拟蓝牙音箱测试项目"],
        ["Mock Headset Suite", "MOCK-AUDIO-03", "归档", "模拟头戴式耳机测试项目"],
    ]
    return render_template(
        "module_list.html",
        page_title="项目管理",
        page_description="维护模拟音频产品测试项目，后续可扩展项目增删改查。",
        action_label="新建项目",
        columns=columns,
        rows=rows,
    )
