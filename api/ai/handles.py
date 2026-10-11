"""Per-request handles: the only names and references the model ever sees.

People become placeholders ("You" for the signed-in user, "Person A", "Person B", ... for roommates in
user-ID order) and purchases become "purchase_1", "purchase_2", ... in the order a tool returned them.
Handles live for one request and map back to database keys here, server-side. Anything the model sends
that is not an issued handle is rejected: a raw app ID, a database key, a Nessie ID or a real name.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field

from api.anomalies import Anomaly

ME = "You"
RAW_ID = re.compile(r"^(?:[a-z]{1,5}_\d+|\d+|[0-9a-f]{20,})$", re.IGNORECASE)


class HandleError(Exception):
    """The model referenced something that is not a handle issued in this request."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason  # an audit code, never the offending value


@dataclass(frozen=True)
class Purchase:
    txn_id: int
    merchant: str
    amount_cents: int
    date: str


@dataclass
class Handles:
    me_id: int
    me_name: str
    others: dict[str, tuple[int, str]] = field(default_factory=dict)  # "Person A" -> (user_id, real name)
    purchases: dict[str, Purchase] = field(default_factory=dict)
    anomalies: dict[str, Anomaly] = field(default_factory=dict)  # "anomaly_1" -> an unusual charge

    @classmethod
    def for_household(cls, me_id: int, members: list[tuple[int, str]]) -> Handles:
        """`members` is every current household member as (user_id, display_name)."""
        me_name = next((name for uid, name in members if uid == me_id), "")
        others = sorted((uid, name) for uid, name in members if uid != me_id)
        letters = string.ascii_uppercase
        return cls(
            me_id=me_id,
            me_name=me_name,
            others={f"Person {letters[i]}": member for i, member in enumerate(others[: len(letters)])},
        )

    def people(self) -> list[str]:
        return [ME, *self.others]

    def person(self, handle: object) -> int:
        """The user ID behind a person handle."""
        if handle == ME:
            return self.me_id
        if isinstance(handle, str) and handle in self.others:
            return self.others[handle][0]
        raise HandleError(self._why(handle))

    def name(self, user_id: int) -> str:
        if user_id == self.me_id:
            return self.me_name
        return next(name for uid, name in self.others.values() if uid == user_id)

    def add_purchase(self, purchase: Purchase) -> str:
        handle = f"purchase_{len(self.purchases) + 1}"
        self.purchases[handle] = purchase
        return handle

    def purchase(self, handle: object) -> Purchase:
        if isinstance(handle, str) and handle in self.purchases:
            return self.purchases[handle]
        raise HandleError(self._why(handle))

    def add_anomalies(self, found: list[Anomaly]) -> None:
        self.anomalies = {f"anomaly_{i}": a for i, a in enumerate(found, 1)}

    def anomaly(self, handle: object) -> Anomaly:
        if isinstance(handle, str) and handle in self.anomalies:
            return self.anomalies[handle]
        raise HandleError(self._why(handle))

    def _why(self, value: object) -> str:
        return "raw_id" if isinstance(value, str | int) and RAW_ID.match(str(value)) else "unknown_handle"

    def _names(self) -> list[tuple[str, str]]:
        """(real name, placeholder), longest name first so "Ann Marie" wins over "Ann"."""
        pairs = [(name, handle) for handle, (_, name) in self.others.items()]
        if self.me_name:
            pairs.append((self.me_name, ME))
        return sorted(pairs, key=lambda p: -len(p[0]))

    def redact(self, text: str) -> str:
        """Real household names in `text` replaced by placeholders, before the model sees it."""
        for name, handle in self._names():
            text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", handle, text, flags=re.IGNORECASE)
        return text

    def restore(self, text: str) -> str:
        """Placeholders in model text replaced by real names, for the signed-in user only."""
        for handle, (_, name) in sorted(self.others.items(), key=lambda p: -len(p[0])):
            text = re.sub(rf"(?<!\w){re.escape(handle)}(?!\w)", name, text)
        return text

    def named_in(self, text: str) -> list[int]:
        """Roommates whose real name appears in `text` (the template fallback's parser)."""
        return [
            uid
            for uid, name in self.others.values()
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, flags=re.IGNORECASE)
        ]
