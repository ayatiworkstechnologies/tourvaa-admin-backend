from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.permissions import Permission, RolePermission
from app.models.users import User, UserRole
from app.models.suppliers import Supplier

bearer_scheme = HTTPBearer(auto_error=False)
ACCESS_COOKIE_NAME = "tourvaa_access"

SUPPLIER_APPROVAL_ERROR = {
    "success": False,
    "code": "SUPPLIER_APPROVAL_REQUIRED",
    "message": "Your supplier account must be approved before using this feature.",
}

PENDING_SUPPLIER_SAFE_API_PREFIXES = (
    "/api/auth/",
    "/api/dashboard/me",
    "/api/dashboard/summary",
    "/api/suppliers/me",
    "/api/supplier/messages",
    "/api/notifications",
    "/api/profile",
    "/api/private-documents/supplier/",
)


ACTION_TO_DOTTED = {
    "view": "view",
    "create": "create",
    "update": "edit",
    "delete": "delete",
}

DOTTED_TO_ACTION = {
    "view": "view",
    "create": "create",
    "edit": "update",
    "update": "update",
    "delete": "delete",
}

MODULE_ALIASES = {
    # email module is seeded as "email" in MODULES but granular permissions use "email_templates"
    "email": "email_templates",
    "email_templates": "email",
    # resellers is an alias for agents (legacy MODULES entry)
    "resellers": "agents",
    "agents": "resellers",
    # activity_logs in legacy slugs vs audit naming
    "audit_logs": "activity_logs",
    "activity_logs": "audit_logs",
}


def expand_permission_slugs(permission_slugs: tuple[str, ...]):
    expanded = set(permission_slugs)

    for slug in permission_slugs:
        if "." in slug:
            module, action = slug.split(".", 1)
            legacy_action = DOTTED_TO_ACTION.get(action)
            legacy_module = MODULE_ALIASES.get(module, module)

            if legacy_action:
                expanded.add(f"{legacy_action}-{legacy_module}")
            continue

        if "-" in slug:
            action, module = slug.split("-", 1)
            dotted_action = ACTION_TO_DOTTED.get(action)
            dotted_module = MODULE_ALIASES.get(module, module)

            if dotted_action:
                expanded.add(f"{dotted_module}.{dotted_action}")

    return list(expanded)


def get_user_role_ids(user: User):
    role_ids = {user.role_id} if user.role_id else set()
    role_ids.update(user_role.role_id for user_role in user.user_roles)
    return [role_id for role_id in role_ids if role_id]


def _decode_token(token: str) -> dict:
    """
    Decode a JWT using the portal-specific secret.
    Reads the unverified 'portal' claim first to select the correct secret,
    then performs a full verified decode with that secret.
    """
    try:
        unverified = jwt.get_unverified_claims(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    portal = unverified.get("portal")
    secret = settings.get_portal_secret(portal) if portal else settings.JWT_SECRET_KEY

    try:
        return jwt.decode(token, secret, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        # If the portal-specific secret fails and portal was set, also reject immediately.
        # If no portal claim, try the main secret (backwards compat for old tokens).
        if portal:
            raise HTTPException(status_code=401, detail="Invalid token")
        raise HTTPException(status_code=401, detail="Invalid token")


def _request_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str:
    if credentials and credentials.scheme.lower() == "bearer" and credentials.credentials:
        return credentials.credentials
    token = request.cookies.get(ACCESS_COOKIE_NAME, "")
    if not token:
        raise HTTPException(status_code=401, detail="Authorization token missing")
    return token


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    token = _request_token(request, credentials)
    payload = _decode_token(token)
    if payload.get("token_type") not in {None, "access"}:
        raise HTTPException(status_code=401, detail="Invalid access token")

    user_id = payload.get("user_id")
    token_version = payload.get("token_version")
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid user")

    if token_version is None or token_version != user.token_version:
        raise HTTPException(status_code=401, detail="Token has expired")

    if user.account_status != "ACTIVE" or not user.is_active:
        raise HTTPException(status_code=403, detail="User is not approved")

    if user.role and not user.role.is_active:
        raise HTTPException(status_code=403, detail="Role is inactive")

    return user


def _is_supplier(user: User) -> bool:
    return user.user_type == "SUPPLIER" or "supplier" in ((user.role.slug if user.role else "") or "").lower()


def ensure_approved_supplier(db: Session, user: User) -> Supplier:
    if not _is_supplier(user):
        raise HTTPException(status_code=403, detail="This endpoint requires a supplier account")
    if not user.email_verified or not user.email_verified_at:
        raise HTTPException(status_code=403, detail=SUPPLIER_APPROVAL_ERROR)
    if user.account_status != "ACTIVE" or not user.is_active:
        raise HTTPException(status_code=403, detail=SUPPLIER_APPROVAL_ERROR)
    supplier = db.query(Supplier).filter(Supplier.user_id == user.id).first()
    if not supplier or (supplier.approval_status or "").upper() != "APPROVED":
        raise HTTPException(status_code=403, detail=SUPPLIER_APPROVAL_ERROR)
    return supplier


def require_approved_supplier(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Supplier:
    """Authenticate and return the approved supplier profile for operational APIs."""
    return ensure_approved_supplier(db, current_user)


def get_token_user_including_inactive(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    payload = _decode_token(_request_token(request, credentials))
    if payload.get("token_type") not in {None, "access"}:
        raise HTTPException(status_code=401, detail="Invalid access token")
    user = db.query(User).filter(User.id == payload.get("user_id")).first()
    if not user or payload.get("token_version") != user.token_version:
        raise HTTPException(status_code=401, detail="Session invalidated")
    return user

def require_portal(expected_portal: str):
    """Dependency that additionally enforces the token's portal claim matches the expected portal."""
    def dependency(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
        db: Session = Depends(get_db),
    ):
        token = _request_token(request, credentials)
        payload = _decode_token(token)
        if payload.get("token_type") not in {None, "access"}:
            raise HTTPException(status_code=401, detail="Invalid access token")
        portal = payload.get("portal", "")

        if portal != expected_portal:
            raise HTTPException(
                status_code=403,
                detail=f"This endpoint requires a {expected_portal} token. Use the correct portal login."
            )

        user_id = payload.get("user_id")
        token_version = payload.get("token_version")
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            raise HTTPException(status_code=401, detail="Invalid user")
        if token_version is None or token_version != user.token_version:
            raise HTTPException(status_code=401, detail="Token has expired")
        if user.account_status != "ACTIVE" or not user.is_active:
            raise HTTPException(status_code=403, detail="User is not approved")
        if user.role and not user.role.is_active:
            raise HTTPException(status_code=403, detail="Role is inactive")

        return user

    return dependency

def require_permission(permission_slug: str):
    return require_any_permission(permission_slug)


def require_any_permission(*permission_slugs: str):
    def dependency(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if _is_supplier(current_user) and not request.url.path.startswith(PENDING_SUPPLIER_SAFE_API_PREFIXES):
            ensure_approved_supplier(db, current_user)

        role_ids = get_user_role_ids(current_user)
        allowed_slugs = expand_permission_slugs(permission_slugs)

        if not role_ids:
            raise HTTPException(status_code=403, detail="Role is required")

        allowed = (
            db.query(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id.in_(role_ids))
            .filter(Permission.slug.in_(allowed_slugs))
            .filter(Permission.is_active == True)
            .first()
        )

        if not allowed:
            raise HTTPException(status_code=403, detail="Permission denied")

        return current_user

    return dependency
