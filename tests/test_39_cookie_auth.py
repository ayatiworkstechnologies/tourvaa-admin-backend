from fastapi import Response

from app.routers.auth import ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, _clear_auth_cookies, _set_auth_cookies


def test_auth_cookies_are_httponly_and_refresh_token_is_not_serialized():
    response = Response()
    payload = _set_auth_cookies(response, {"access_token": "access.jwt", "_refresh_token": "refresh.jwt"})
    cookies = response.headers.getlist("set-cookie")

    assert len(cookies) == 2
    assert any(cookie.startswith(f"{ACCESS_COOKIE_NAME}=access.jwt") and "HttpOnly" in cookie and "Path=/" in cookie for cookie in cookies)
    assert any(cookie.startswith(f"{REFRESH_COOKIE_NAME}=refresh.jwt") and "HttpOnly" in cookie and "Path=/api/auth" in cookie for cookie in cookies)
    assert all("SameSite=lax" in cookie for cookie in cookies)
    assert "_refresh_token" not in payload


def test_logout_expires_both_auth_cookies():
    response = Response()
    _clear_auth_cookies(response)
    cookies = response.headers.getlist("set-cookie")

    assert len(cookies) == 2
    assert any(cookie.startswith(f'{ACCESS_COOKIE_NAME}=""') and "Max-Age=0" in cookie for cookie in cookies)
    assert any(cookie.startswith(f'{REFRESH_COOKIE_NAME}=""') and "Max-Age=0" in cookie for cookie in cookies)


def test_cookie_only_transport_does_not_expose_access_token_in_json():
    response = Response()
    payload = _set_auth_cookies(response, {"access_token": "access.jwt", "_refresh_token": "refresh.jwt", "token_type": "bearer"}, expose_access_token=False)

    assert "access_token" not in payload
    assert "token_type" not in payload
    assert any(cookie.startswith(f"{ACCESS_COOKIE_NAME}=access.jwt") for cookie in response.headers.getlist("set-cookie"))
