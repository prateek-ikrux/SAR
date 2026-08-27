from __future__ import annotations

import re
from typing import Any

_NON_DIGITS = re.compile(r"\D+")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def normalize_email(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    return cleaned if _EMAIL_RE.match(cleaned) else None


def normalize_phone(value: Any) -> str | None:
    """Reduce a phone number to its last 10 digits.

    Handles the shapes actually present in the corpus: '8050418310',
    '+91-8050418310', '91 80504 18310', '(080) 5041-8310'.
    """
    if not isinstance(value, (str, int)):
        return None
    digits = _NON_DIGITS.sub("", str(value))
    if len(digits) < 10:
        return None
    return digits[-10:]


def looks_like_email(query: str) -> bool:
    return bool(_EMAIL_RE.match(query.strip()))


def looks_like_phone(query: str) -> bool:
    stripped = query.strip()
    if not stripped:
        return False
    digits = _NON_DIGITS.sub("", stripped)
    # Must be essentially all digits (plus separators) and long enough to be a number.
    return len(digits) >= 10 and len(digits) >= len(stripped) - 4 and not any(c.isalpha() for c in stripped)


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        self._parent.setdefault(key, key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


def collapse(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group hits belonging to the same person.

    Two documents are the same person if they share a normalised email OR a
    normalised phone. Grouping is transitive, so resume A (email X, no phone),
    resume B (email X, phone Y) and resume C (phone Y, no email) collapse into one.

    Input must already be sorted best-score-first. The best-scoring document in
    each group becomes the primary and keeps its score; the rest are attached as
    ``duplicates``.
    """
    if not hits:
        return []

    uf = _UnionFind()
    for hit in hits:
        doc_key = f"doc:{hit['id']}"
        uf.find(doc_key)
        email = normalize_email(hit.get("email"))
        phone = normalize_phone(hit.get("phone"))
        if email:
            uf.union(doc_key, f"email:{email}")
        if phone:
            uf.union(doc_key, f"phone:{phone}")

    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for hit in hits:
        root = uf.find(f"doc:{hit['id']}")
        if root not in groups:
            groups[root] = []
            order.append(root)
        groups[root].append(hit)

    collapsed: list[dict[str, Any]] = []
    for root in order:
        members = groups[root]
        primary = dict(members[0])
        extras = members[1:]
        primary["collapsed"] = bool(extras)
        primary["duplicate_count"] = len(members)
        primary["duplicates"] = [
            {"id": m["id"], "file_name": m.get("file_name"), "score": m.get("score")} for m in extras
        ]
        # A duplicate may carry contact details the primary is missing.
        if not primary.get("email"):
            primary["email"] = next((m.get("email") for m in extras if m.get("email")), None)
        if not primary.get("phone"):
            primary["phone"] = next((m.get("phone") for m in extras if m.get("phone")), None)
        collapsed.append(primary)

    return collapsed


def duplicate_query(email: Any, phone: Any) -> dict[str, Any] | None:
    """Mongo filter matching every profile that belongs to the same person."""
    clauses: list[dict[str, Any]] = []
    normalized_email = normalize_email(email)
    if normalized_email:
        clauses.append({"email": {"$regex": f"^{re.escape(normalized_email)}$", "$options": "i"}})
    normalized_phone = normalize_phone(phone)
    if normalized_phone:
        clauses.append({"phone": {"$regex": f"{re.escape(normalized_phone)}$"}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}
