from flask import Blueprint, render_template


bp = Blueprint("executions", __name__, url_prefix="/executions")


@bp.get("/")
def index():
    columns = ["用例", "版本", "执行人", "结果"]
    rows = [
        ["Sample playback checklist", "demo_build_alpha", "demo_tester", "Pass"],
        ["Mock microphone capture checklist", "demo_build_alpha", "sample_user", "Blocked"],
        ["Demo Bluetooth reconnect checklist", "sample_build_beta", "mock_reviewer", "Not Run"],
    ]
    return render_template(
        "module_list.html",
        page_title="执行记录",
        page_description="记录模拟用例执行结果，后续可扩展批量执行和结果统计。",
        action_label="新增执行记录",
        columns=columns,
        rows=rows,
    )
