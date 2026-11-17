from rest_framework.permissions import BasePermission


def capability(codename: str) -> type[BasePermission]:
    """DRF permission class requiring an ETqa capability, e.g. capability("manage_collections")."""

    class HasCapability(BasePermission):
        message = "You do not have permission to perform this action."

        def has_permission(self, request, view) -> bool:
            user = request.user
            return bool(user and user.is_authenticated and user.has_perm(f"access.{codename}"))

    HasCapability.__name__ = f"Has_{codename}"
    return HasCapability
