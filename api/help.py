"""Help panel: private, opt-in referrals to free assistance. General information, not legal advice.

Shown only to the signed-in user (never in the feed, to roommates, on Clearday Home, or to the model).
Triggers come from the user's own data: a tight bill ahead, an overdue utility bill, two or more
overdraft fees in 30 days, or a known debt collector's charge. Reasons are generic sentences that never
quote merchants, amounts or labels. No referral fees, no paid placement; nothing is shared with anyone.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from api import forecast, sky
from api.session import CurrentUser

DISCLAIMER = "General information, not legal advice"
OVERDRAFT_LIMIT = 2
KNOWN_COLLECTORS = ("portfolio recovery", "midland credit", "lvnv", "encore capital", "cavalry portfolio")

# Names and sites from the docs/03 list. Confirm each site's current details before the demo.
RESOURCES: list[dict[str, str]] = [
    {
        "name": "NC 211",
        "help": "Dial 2-1-1 to find rent and utility assistance near you.",
        "url": "https://www.211nc.org",
        "topic": "rent_utilities",
    },
    {
        "name": "Legal Aid of North Carolina",
        "help": "Free civil legal help for people who qualify, including housing and debt.",
        "url": "https://www.legalaidnc.org",
        "topic": "legal",
    },
    {
        "name": "LawHelpNC",
        "help": "Plain-language legal information and links to free legal help in North Carolina.",
        "url": "https://www.lawhelpnc.org",
        "topic": "legal",
    },
    {
        "name": "North Carolina Pro Bono Resource Center",
        "help": "Connects people with volunteer attorneys.",
        "url": "https://www.ncprobono.org",
        "topic": "legal",
    },
    {
        "name": "NC energy bill assistance",
        "help": "State programs that help eligible households with heating and cooling bills.",
        "url": "https://www.ncdhhs.gov/divisions/social-services/energy-assistance",
        "topic": "rent_utilities",
    },
    {
        "name": "VITA free tax preparation",
        "help": "Free tax help for people who qualify; refunds can ease a tight month.",
        "url": "https://www.irs.gov/vita",
        "topic": "money",
    },
    {
        "name": "CFPB complaint portal",
        "help": "Report a problem with a bank, lender or debt collector.",
        "url": "https://www.consumerfinance.gov/complaint/",
        "topic": "money",
    },
]


def trigger_reasons(
    *, tight_bills: int, overdue_utilities: int, overdraft_fees: int, collector_charges: int
) -> list[str]:
    """Generic, private reasons for the panel. Pure: counts in, sentences out."""
    reasons = []
    if tight_bills:
        reasons.append("Your forecast shows a bill coming up that may be hard to cover.")
    if overdue_utilities:
        reasons.append("A utility bill looks past due.")
    if overdraft_fees >= OVERDRAFT_LIMIT:
        reasons.append("Your account had overdraft fees more than once this month.")
    if collector_charges:
        reasons.append("A charge from a debt collector showed up.")
    return reasons


def _counts(conn, user: CurrentUser) -> dict[str, int]:
    today = sky.today()
    since = today - dt.timedelta(days=30)
    tight = sum(1 for b in forecast.build_forecast(conn, user)["bills"] if b["weather"] == "tight")
    overdue = sum(
        1 for b in sky.personal_bills(conn, user.user_id) if b.category == "utilities" and b.due_on < today
    )
    (overdrafts,) = conn.execute(
        """SELECT count(*) FROM transactions WHERE user_id = %s AND occurred_at::date >= %s
             AND status = 'posted' AND merchant ILIKE '%%overdraft%%'""",
        (user.user_id, since),
    ).fetchone()
    (collectors,) = conn.execute(
        """SELECT count(*) FROM transactions WHERE user_id = %s AND occurred_at::date >= %s
             AND lower(merchant) ILIKE ANY(%s)""",
        (user.user_id, since, [f"%{c}%" for c in KNOWN_COLLECTORS]),
    ).fetchone()
    return {
        "tight_bills": tight,
        "overdue_utilities": overdue,
        "overdraft_fees": int(overdrafts),
        "collector_charges": int(collectors),
    }


def panel(conn, user: CurrentUser) -> dict[str, Any]:
    reasons = trigger_reasons(**_counts(conn, user))
    return {
        "triggered": bool(reasons),
        "reasons": reasons,
        "resources": RESOURCES if reasons else [],
        "disclaimer": DISCLAIMER,
        "private_note": "Only you can see this. Nothing is shared with anyone.",
    }
