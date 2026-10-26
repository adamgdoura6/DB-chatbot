"""Simulated chat: canned replies, used while no database is connected (or WEBAPP_MODE=simulated).

Lets the page be designed and demoed without a database or an agent run.
"""

import itertools
import random
import time
import uuid
from typing import Iterator, Optional

# In rotation: a confirmed answer, an answer resting on a guess, a schema answer.
CANNED = [
    {
        "text": "€184,230 net revenue in Munich last quarter, from 1,912 paid orders.",
        "sql": "SELECT sum(o.amount - coalesce(r.refunded, 0)) / 100.0\nFROM public.orders o\n"
               "JOIN public.stores s ON s.id = o.store_id\nLEFT JOIN public.refunds r ON r.order_id = o.id\n"
               "WHERE s.city = 'Munich' AND o.paid_at >= date '2026-07-01' AND o.paid_at < date '2026-10-01'",
        "tables": ["public.orders", "public.refunds", "public.stores"],
        "note": "amount is in EUR cents, confirmed by your data owner on 2026-10-02.",
    },
    {
        "text": "You have 4,318 active customers: accounts with a paid order in the last 90 days, "
                "excluding test accounts.",
        "sql": "SELECT count(DISTINCT a.id)\nFROM public.accounts a\nJOIN public.orders o ON o.account_id = a.id\n"
               "WHERE o.paid_at >= now() - interval '90 days' AND NOT a.is_test",
        "tables": ["public.accounts", "public.orders"],
        "note": "\"Active\" is a guess based on order activity, not confirmed. Tell me if you define it differently.",
    },
    {
        "text": "Invoices live in billing.invoices, one row per invoice. The PDF links are in billing.invoice_files.",
        "sql": None,
        "tables": ["billing.invoices", "billing.invoice_files"],
        "note": None,
    },
]
_replies = itertools.cycle(CANNED)


def chat(message: str, conversation: Optional[str]) -> Iterator[dict]:
    reply = next(_replies)
    yield {"type": "conversation", "id": conversation or str(uuid.uuid4())}
    time.sleep(random.uniform(0.9, 1.6))  # "thinking"
    words = reply["text"].split(" ")
    for i, word in enumerate(words):
        yield {"type": "text", "text": word + (" " if i < len(words) - 1 else "")}
        time.sleep(random.uniform(0.04, 0.09))
    yield {"type": "details", "sql": reply["sql"], "tables": reply["tables"], "note": reply["note"]}
