from flask import Blueprint, render_template


bp = Blueprint("logs", __name__, url_prefix="/logs")


@bp.get("/")
def index():
    columns = ["文件名", "分类", "上传人", "说明"]
    rows = [
        ["sample_audio_check.log", "播放", "demo_tester", "仅用于展示的模拟 log"],
        ["mock_bluetooth_trace.txt", "连接", "sample_user", "仅包含 mock 文本"],
        ["demo_noise_scan.log", "录音", "mock_reviewer", "后续可扩展解析入口"],
    ]
    return render_template(
        "module_list.html",
        page_title="模拟 Log 管理",
        page_description="管理模拟 log 文件元信息，后续可增加上传、解析和关联缺陷。",
        action_label="上传模拟 Log",
        columns=columns,
        rows=rows,
    )
