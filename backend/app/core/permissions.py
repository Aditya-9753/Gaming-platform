"""Permission validation and RBAC policy enforcement."""

from typing import Iterable, Set, Union
from app.core.constants import PermissionCode, UserRole


def has_permission(
    granted_permissions: Iterable[str],
    required_permission: Union[str, PermissionCode],
) -> bool:
    """Verify if the granted permission set includes the required permission."""
    required_code = (
        required_permission.value
        if isinstance(required_permission, PermissionCode)
        else required_permission
    )
    return required_code in set(granted_permissions)


def check_role_permission(
    role_name: str,
    granted_permissions: Set[str],
    required_permission: Union[str, PermissionCode],
) -> bool:
    """Verify role and granular permission.

    SUPERADMIN bypasses granular checks and always has permission.
    """
    if role_name.upper() == UserRole.SUPERADMIN.value:
        return True
    return has_permission(granted_permissions, required_permission)
