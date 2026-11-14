def test_application_imports_and_exposes_core_routes():
    from app.main import app
    paths = {route.path for route in app.routes}
    assert "/api/health" in paths
    assert "/api/messages" in paths
    assert "/api/oauth/gmail/start" in paths
    assert "/api/drafts/{draft_id}/send" in paths
    assert "/api/settings" in paths
