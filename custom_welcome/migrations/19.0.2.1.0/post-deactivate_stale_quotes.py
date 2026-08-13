# -*- coding: utf-8 -*-
"""
Migration: 19.0.2.1.0  — post
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Deactivates legacy English motivation quotes that have kural_number = 0.

Background
----------
The original welcome.quote CSV contained 30 English motivation quotes with
kural_number=0.  When the CSV was replaced with 1330 Thirukkural entries, the
old rows were NOT deleted because Odoo's CSV import only touches rows matched
by their id (xml_id).  The old rows had different ids so they were left in the
table as active records.

Effect
------
Because the model orders by kural_number asc, id asc, the 30 stale rows
(kural_number=0) sort *before* kural #1 and were assigned indices 0-29 in
the daily rotation pool of 1360 quotes.  After kural #1330 exhausted the
Thirukkural range (indices 30-1359), indices 1330-1359 wrapped back to the
stale English quotes — exactly the bug reported.

Fix
---
Set active=false on every row with kural_number=0.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute(
        "UPDATE welcome_quote SET active = false WHERE kural_number = 0"
    )
    count = cr.rowcount
    if count:
        _logger.info(
            "custom_welcome migration 19.0.2.1.0: "
            "deactivated %d stale motivation quote(s) (kural_number=0).",
            count,
        )
