from flask import Blueprint, render_template


bp = Blueprint("versions", __name__, url_prefix="/versions")


@bp.get("/")
def index():
    columns = ["关联项目", "版本名称", "阶段", "状态"]
    rows = [
        ["Demo Audio Earbuds", "demo_build_alpha", "功能验证", "测试中"],
        ["Sample Speaker Lab", "sample_build_beta", "回归验证", "计划中"],
        ["Mock Headset Suite", "mock_release_candidate", "发布前验证", "待归档"],
    ]
    return render_template(
        "module_list.html",
        page_title="版本管理",
        page_description="跟踪 mock 版本和测试阶段，后续可关联测试计划和执行结果。",
        action_label="新建版本",
        columns=columns,
        rows=rows,
    )
