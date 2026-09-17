"""
Pre-migration: back up the existing free-text software_used values from
account_analytic_line BEFORE the module upgrade changes the column from
Char to a Many2one FK, then DROP the old text column entirely.

Why drop instead of leaving it for the ORM to convert: Odoo's _auto_init
tries to ALTER the existing column in place with
`... USING software_used::integer`, which fails immediately on any real
text value (e.g. "odoo" cannot cast to integer). Dropping the column here
means the ORM instead just CREATEs a fresh integer FK column with no
conversion attempted — clean, and matches the "we're restoring values
ourselves in post-migrate" plan.
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
        _logger.warning(
            "pre-migrate: account_analytic_line.software_used column "
            "not found — skipping backup."
        )
        return

    _logger.info(
        "pre-migrate: backing up account_analytic_line.software_used "
        "free-text values into __software_used_backup before type change."
    )

    cr.execute("""
        CREATE TABLE IF NOT EXISTS __software_used_backup AS
        SELECT id AS line_id, software_used AS old_value
        FROM account_analytic_line
        WHERE software_used IS NOT NULL AND software_used != ''
    """)

    cr.execute("SELECT COUNT(*) FROM __software_used_backup")
    count = cr.fetchone()[0]
    _logger.info("pre-migrate: backed up %s timesheet line(s).", count)

    # Drop the old text column so the ORM creates a fresh integer FK
    # column instead of attempting an in-place USING-cast conversion
    # (which fails on any non-numeric text like "odoo" or "solidworks").
    _logger.info(
        "pre-migrate: dropping old text column account_analytic_line.software_used."
    )
    cr.execute("ALTER TABLE account_analytic_line DROP COLUMN software_used")
    _logger.info("pre-migrate: old column dropped.")