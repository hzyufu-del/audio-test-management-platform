from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user
from sqlalchemy.exc import OperationalError

from app.extensions import db
from app.models import User


bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        try:
            user = User.query.filter_by(email=email).first()
        except OperationalError:
            flash("本地数据库尚未初始化，请先运行 README 中的 init-db 命令。", "warning")
            return render_template("auth/login.html")

        if user and user.check_password(password):
            login_user(user)
            flash("已登录到 demo 平台。", "success")
            return redirect(url_for("dashboard.index"))

        flash("登录信息无效，请使用 demo 账号或先注册。", "danger")

    return render_template("auth/login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("请填写用户名、邮箱和密码。", "warning")
            return render_template("auth/register.html")

        try:
            existing_user = User.query.filter_by(email=email).first()
        except OperationalError:
            flash("本地数据库尚未初始化，请先运行 README 中的 init-db 命令。", "warning")
            return render_template("auth/register.html")

        if existing_user:
            flash("该邮箱已被 demo 用户使用。", "warning")
            return render_template("auth/register.html")

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("注册成功，请登录。", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    flash("已退出登录。", "info")
    return redirect(url_for("dashboard.index"))
