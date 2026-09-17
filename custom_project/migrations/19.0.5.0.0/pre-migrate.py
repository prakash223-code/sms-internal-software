"""
Pre-migration: back up existing software_used Many2one FK values before
the field becomes Many2many, then drop the old integer column so Odoo
creates the new relation table cleanly instead of attempting an in-place
conversion.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'account_analytic_line'
          AND column_name = 'software_used'
    """)
    if not cr.fetchone():
        _logger.warning("pre-migrate: software_used column not found — skipping.")
        return

    _logger.info("pre-migrate: backing up software_used FK values (m2o -> m2m).")

    cr.execute("""
        CREATE TABLE IF NOT EXISTS __software_used_m2o_backup AS
        SELECT id AS line_id, software_used AS software_id
        FROM account_analytic_line
        WHERE software_used IS NOT NULL
    """)

    cr.execute("SELECT COUNT(*) FROM __software_used_m2o_backup")
    count = cr.fetchone()[0]
    _logger.info("pre-migrate: backed up %s line(s).", count)

    cr.execute("ALTER TABLE account_analytic_line DROP COLUMN software_used")
    _logger.info("pre-migrate: old m2o column dropped.")