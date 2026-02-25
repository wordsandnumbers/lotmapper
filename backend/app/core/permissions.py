from functools import wraps
from typing import Callable, List
from fastapi import HTTPException, status


class Roles:
    ADMIN = "admin"
    REVIEWER = "reviewer"


def require_roles(allowed_roles: List[str]):
    """Decorator to check if user has required role."""

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get current_user from kwargs (injected by Depends)
            current_user = kwargs.get("current_user")
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )
            if current_user.role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions",
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_admin(func: Callable):
    """Shortcut decorator to require admin role."""
    return require_roles([Roles.ADMIN])(func)
