from tests.helpers.users import UserRoutes


class TestCreateDemo:
    async def test_creates_demo_user(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.demo()
        assert resp.status_code == 200
        body = resp.json()
        assert body["user"]["is_demo"] is True
        assert len(body["trips"]) >= 1

    async def test_sets_session_cookie(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.demo()
        uid = resp.json()["user"]["id"]
        user_resp = await user_routes.current()
        assert user_resp.status_code == 200
        assert user_resp.json()["id"] == uid


class TestDeleteDemo:
    async def test_deletes_demo_user(self, user_routes: UserRoutes) -> None:
        await user_routes.demo()
        resp = await user_routes.delete_demo()
        assert resp.status_code == 204
        # Session cleared - user endpoint returns 401
        user_resp = await user_routes.current()
        assert user_resp.status_code == 401

    async def test_rejects_unauthenticated(self, user_routes: UserRoutes) -> None:
        resp = await user_routes.delete_demo()
        assert resp.status_code == 401
