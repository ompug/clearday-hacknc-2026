"""Help panel: private to the user, appears only on their own triggers, generic reasons, disclaimer."""

from __future__ import annotations

from api import help as help_panel
from api.tests.test_api_contract import _add_card_charges, login
from api.tests.test_api_contract import client as client  # noqa: F401  (fixture)


def test_requires_session(client):  # noqa: F811
    assert client.get("/api/help").status_code == 401


def test_untriggered_panel_is_empty_but_carries_the_disclaimer(client):  # noqa: F811
    login(client)
    body = client.get("/api/help").json()
    assert body["triggered"] is False and body["reasons"] == [] and body["resources"] == []
    assert body["disclaimer"] == "General information, not legal advice"


def test_two_overdraft_fees_trigger_it_for_that_user_only(client, scratch_dsn):  # noqa: F811
    ana, card = client.ids["users"][0], client.ids["card"]
    _add_card_charges(
        scratch_dsn,
        ana,
        card,
        [("Overdraft Fee", "fees", 3500, 3), ("Overdraft Fee", "fees", 3500, 9)],
    )
    login(client)
    res = client.get("/api/help")
    body = res.json()
    assert res.headers["cache-control"] == "private, no-store"
    assert body["triggered"] is True and body["resources"]
    assert any("overdraft" in r for r in body["reasons"])
    assert "Overdraft Fee" not in str(body) and "35" not in " ".join(body["reasons"])  # generic only
    assert all(r["url"].startswith("https://") for r in body["resources"])
    login(client, 1)  # Ben's own data has no overdraft fees
    assert not any("overdraft" in r for r in client.get("/api/help").json()["reasons"])


def test_one_overdraft_fee_does_not_trigger(client, scratch_dsn):  # noqa: F811
    _add_card_charges(
        scratch_dsn, client.ids["users"][0], client.ids["card"], [("Overdraft Fee", "fees", 3500, 3)]
    )
    login(client)
    assert client.get("/api/help").json()["triggered"] is False


def test_trigger_reasons_are_generic_sentences():
    reasons = help_panel.trigger_reasons(
        tight_bills=1, overdue_utilities=1, overdraft_fees=2, collector_charges=1
    )
    assert len(reasons) == 4 and not any(ch.isdigit() or ch == "$" for r in reasons for ch in r)
    assert (
        help_panel.trigger_reasons(tight_bills=0, overdue_utilities=0, overdraft_fees=1, collector_charges=0)
        == []
    )


def test_help_never_reaches_the_feed_or_the_device_payloads():
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    for name in ("realtime.py", "devices.py"):
        assert "help" not in (root / name).read_text().lower().replace("helper", "")
