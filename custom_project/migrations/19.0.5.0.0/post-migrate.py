"""
Post-migration: read the ORIGINAL raw free-text software_used values
(preserved by 19.0.4.0.0's pre-migrate, deliberately not consumed by its
post-migrate), split each on ',' and '&' into individual software
mentions, map known spelling/casing variants to one canonical name via
ALIAS_MAP, resolve/create project.software records, and insert rows into
the new account_analytic_line_software_rel relation table — potentially
several rows per original timesheet line.
"""
import logging
import re

_logger = logging.getLogger(__name__)

# Map any raw (lowercased, trimmed) variant to its canonical display name.
# Add more entries here if further variants turn up during verification.
ALIAS_MAP = {
    'ansys fluent': 'Ansys Fluent',
    'ansys meshing': 'Ansys Meshing',
    'ansys spaceclaim': 'Ansys SpaceClaim',
    'spaceclaim': 'Ansys SpaceClaim',
    'libreoffice impress': 'LibreOffice Impress',
}

SPLIT_RE = re.compile(r'[,&]')


def _canonical_name(raw_piece):
    cleaned = raw_piece.strip()
    if not cleaned:
        return None
    key = cleaned.lower()
    return ALIAS_MAP.get(key, cleaned)  # fall back to trimmed original if unmapped


def migrate(cr, version):
    if not version:
        return

    cr.execute("SELECT to_regclass('__software_used_backup')")
    if not cr.fetchone()[0]:
        _logger.warning("post-migrate (5.0.0): raw-text backup table not found — nothing to restore.")
        return

    cr.execute("SELECT to_regclass('account_analytic_line_software_rel')")
    if not cr.fetchone()[0]:
        _logger.error(
            "post-migrate (5.0.0): relation table account_analytic_line_software_rel "
            "does not exist — aborting restore."
        )
        return

    cr.execute("SELECT line_id, old_value FROM __software_used_backup")
    rows = cr.fetchall()
    _logger.info("post-migrate (5.0.0): processing %s raw timesheet line value(s).", len(rows))

    name_to_id = {}
    unmapped_seen = set()

    def _get_or_create_software(name):
        key = name.lower()
        if key in name_to_id:
            return name_to_id[key]
        cr.execute("SELECT id FROM project_software WHERE lower(name) = %s LIMIT 1", (key,))
        existing = cr.fetchone()
        if existing:
            software_id = existing[0]
        else:
            cr.execute("""
                INSERT INTO project_software (name, active, create_date, write_date)
                VALUES (%s, TRUE, NOW(), NOW())
                RETURNING id
            """, (name,))
            software_id = cr.fetchone()[0]
            _logger.info("post-migrate (5.0.0): created project.software '%s' (id=%s)", name, software_id)
        name_to_id[key] = software_id
        return software_id

    link_count = 0

    for line_id, old_value in rows:
        if not old_value:
            continue
        pieces = [p for p in SPLIT_RE.split(old_value) if p.strip()]
        software_ids_for_line = set()
        for piece in pieces:
            canonical = _canonical_name(piece)
            if not canonical:
                continue
            if canonical.lower() not in ALIAS_MAP.values():
                unmapped_seen.add(canonical)
            software_id = _get_or_create_software(canonical)
            software_ids_for_line.add(software_id)

        for software_id in software_ids_for_line:
            cr.execute("""
                INSERT INTO account_analytic_line_software_rel (line_id, software_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
            """, (line_id, software_id))
            link_count += 1

    _logger.info(
        "post-migrate (5.0.0): done. %s line(s) processed, %s relation row(s) "
        "inserted, %s distinct project.software record(s) resolved.",
        len(rows), link_count, len(name_to_id),
    )
    if unmapped_seen:
        _logger.warning(
            "post-migrate (5.0.0): the following names had NO alias-map entry "
            "and were used as-is (verify these are correct, not typos): %s",
            sorted(unmapped_seen),
        )

    cr.execute("DROP TABLE IF EXISTS __software_used_backup")
    _logger.info("post-migrate (5.0.0): dropped raw-text backup table.")