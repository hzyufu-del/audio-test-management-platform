from app import create_app


def test_dashboard_homepage_is_accessible():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})

    with app.test_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Dashboard" in response.get_data(as_text=True)
