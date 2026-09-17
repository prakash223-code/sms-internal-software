"""
Post-migration for the Char -> Many2one step.

Production's software_used data contains comma/ampersand-separated combo
strings (e.g. "Ansys Fluent,LibreOffice Impress") that cannot be restored
into a single-value Many2one field. Rather than lossy-guessing one value
per line here, we deliberately leave software_used empty at this stage
and keep the raw-text backup table alive — the 19.0.5.0.0 migration
(Many2one -> Many2many) reads the SAME backup table and does proper
splitting + restoration into the new multi-select relation table.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("SELECT to_regclass('__software_used_backup')")
    if not cr.fetchone()[0]:
        _logger.warning("post-migrate (4.0.0): backup table not found — nothing to do.")
        return

    cr.execute("SELECT COUNT(*) FROM __software_used_backup")
    count = cr.fetchone()[0]
    _logger.info(
        "post-migrate (4.0.0): leaving software_used empty for %s line(s) — "
        "raw text preserved in __software_used_backup for proper splitting "
        "during the 19.0.5.0.0 (many2many) migration.",
        count,
    )
    # Intentionally NOT dropping __software_used_backup here — the next
    # migration step needs it.