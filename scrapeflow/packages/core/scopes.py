"""API key scopes and role defaults."""

from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    SCRAPE_WRITE = "scrape:write"
    AUTOMATION_WRITE = "automation:write"
    JOBS_READ = "jobs:read"
    SCHEDULES_WRITE = "schedules:write"
    EXPORTS_READ = "exports:read"
    KEYS_MANAGE = "keys:manage"
    BILLING_MANAGE = "billing:manage"
    AUDIT_READ = "audit:read"
    ADMIN = "*"


ALL_SCOPES: frozenset[Scope] = frozenset(scope for scope in Scope if scope is not Scope.ADMIN)
MEMBER_SCOPES: frozenset[Scope] = frozenset(
    {
        Scope.SCRAPE_WRITE,
        Scope.AUTOMATION_WRITE,
        Scope.JOBS_READ,
        Scope.SCHEDULES_WRITE,
        Scope.EXPORTS_READ,
    }
)
ADMIN_SCOPES: frozenset[Scope] = frozenset({Scope.ADMIN})


def scopes_for_role(role: str) -> frozenset[str]:
    if role in {"owner", "admin"}:
        return frozenset({Scope.ADMIN.value})
    return frozenset(scope.value for scope in MEMBER_SCOPES)


def default_key_scopes() -> list[str]:
    return [scope.value for scope in sorted(MEMBER_SCOPES, key=lambda item: item.value)]


def validate_scopes(values: list[str]) -> list[str]:
    allowed = {scope.value for scope in Scope}
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"Unknown scopes: {', '.join(unknown)}")
    return sorted(set(values))
