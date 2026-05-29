# Implementation Plan: Add "Federal Tub" Shipping Method

## Goal

Add a third shipping method, `Federal Tub`, alongside the existing `Box` and `Individual` options. The value must be selectable in the unit edit form, persisted to the `units.shipping_method` column, and round-trip through the list/detail templates and the label tool.

## Where shipping methods live today

- **DB column** — `ibp/models.py:201`
  `shipping_method = Column(Enum("Box", "Individual", name="shipping_enum"))` on the `Unit` model.
- **Form choices** — `ibp/flask_forms.py:79-81`
  `SelectField` with `choices=[('', ''), ('Box', 'Box'), ('Individual', 'Individual')]` in the `Unit` form.
- **Form ↔ model glue** — `flask_forms.py:99` (`shipping_method.data = model.shipping_method or ''`) and `models.py:219` (`self.shipping_method = form.shipping_method.data or None`).
- **Templates** — rendered via `render.field(form.shipping_method)` in `templates/view_unit.html:50`; displayed as plain text in `templates/list_units.html:28`. No hardcoded option lists in templates.
- **JSON endpoint** — `ibp/views.py:243` exposes `unit_shipping_method` in the `/request_info/<id>` payload (falls back to `"N/A"` when no unit).
- **DYMO XML label** — `ibp/templates/request_label.xml:103` renders `{{ unit and unit.shipping_method or 'N/A' }}` inside a `TextObject` with `<TextFitMode>AlwaysFit</TextFitMode>`, so longer text auto-shrinks within its bounds.
- **Tools** — `tools/label.py:135` renders `unit_shipping_method` onto a Pillow/CUPS label as free text via `fit_text`; `tools/migrate.py:52` copies the column verbatim from a legacy DB.
- **Alembic** — only `alembic/versions/b21034d4ccfa_initial.py` exists, with empty `upgrade()`/`downgrade()`. It is a placeholder head; the schema was built via `db.create_all()`. `alembic_version` in `data.db` is set to `b21034d4ccfa`. `alembic/env.py` configures `render_as_batch=True`, so batch operations work on SQLite.
- **Actual DB schema** — verified via `sqlite3 data.db ".schema units"`:
  - `shipping_method VARCHAR(10)` (length 10 — derived from `len("Individual")`).
  - `CONSTRAINT ck_units_shipping_enum CHECK (shipping_method IN ('Box', 'Individual'))` **is present and enforced by SQLite**. Adding `"Federal Tub"` without dropping this check will fail at INSERT/UPDATE time.
  - `"Federal Tub"` is 11 characters, so the column width also needs to grow to ≥ 11. SQLite ignores VARCHAR length, but a future Postgres deploy would not — fix it in the migration regardless.
- **`build/`** — stale copy of the package; ignore, do not edit.

No other call sites compare `shipping_method` to literal `"Box"`/`"Individual"`, so behavior is purely presentational / pass-through.

## Steps

1. **Update the model enum** — `ibp/models.py:201`
   Change to `Column(Enum("Box", "Individual", "Federal Tub", name="shipping_enum"))`.

2. **Update the form choices** — `ibp/flask_forms.py:81`
   Add `('Federal Tub', 'Federal Tub')` to the `choices` list.

3. **Write an Alembic migration** — new file under `alembic/versions/`, `down_revision = 'b21034d4ccfa'`.
   - Generate with `alembic revision -m "add federal tub shipping method"` (do NOT use `--autogenerate`: target metadata reflects the post-change models, so autogen would produce nothing useful here and the initial revision left the table out of migration history).
   - SQLite does enforce the `CHECK` constraint and does not support `ALTER TYPE` / dropping a named CHECK in place. Use `op.batch_alter_table("units")` (env already has `render_as_batch=True`) to recreate the table:
     ```python
     with op.batch_alter_table("units") as batch:
         batch.alter_column(
             "shipping_method",
             existing_type=sa.Enum("Box", "Individual", name="shipping_enum"),
             type_=sa.Enum("Box", "Individual", "Federal Tub", name="shipping_enum"),
             existing_nullable=True,
         )
     ```
     Batch mode will copy the table, drop the old `ck_units_shipping_enum`, and emit a new CHECK covering all three values, while also widening the column to length 11.
   - `downgrade()` reverses to the two-value enum. Guard the data first, before the batch alter, using the standard Alembic pattern:
     ```python
     bind = op.get_bind()
     count = bind.execute(
         sa.text("SELECT COUNT(*) FROM units WHERE shipping_method = :v"),
         {"v": "Federal Tub"},
     ).scalar()
     if count:
         raise RuntimeError(
             f"Cannot downgrade: {count} unit(s) still use 'Federal Tub'."
         )
     ```
     Then run the symmetric `batch_alter_table` back to the two-value enum, with `existing_type=sa.Enum("Box", "Individual", "Federal Tub", name="shipping_enum")` and `type_=sa.Enum("Box", "Individual", name="shipping_enum")`.

4. **Verify templates need no change**
   - `view_unit.html` renders the select via `render.field`, so the new option appears automatically once the form changes.
   - `list_units.html` prints `unit.shipping_method` as text — already covers the new value.

5. **Verify both label rendering paths** — no code changes expected, but both must be exercised:
   - **Server-rendered DYMO XML** — `ibp/templates/request_label.xml:103`. Already wrapped in `<TextFitMode>AlwaysFit</TextFitMode>`, so the longer string should auto-shrink, but confirm in an actual print preview.
   - **Pillow/CUPS standalone label** — `tools/label.py:135`. Free text drawn via `fit_text`, which scales automatically; sanity-check via a generated PNG.

6. **Manual verification checklist**
   - `alembic upgrade head` runs cleanly on a copy of `data.db`. Primary check: `.schema units` shows the new CHECK constraint listing all three allowed values. Secondary sanity check: column rendered as `VARCHAR(11)` (useful but not the success criterion — SQLite ignores the length).
   - Direct DB-level smoke test on the upgraded copy (the CHECK rewrite is the highest-risk part of this change):
     - `UPDATE units SET shipping_method = 'Federal Tub' WHERE autoid = <id>;` commits without raising a CHECK violation.
     - `UPDATE units SET shipping_method = NULL WHERE autoid = <id>;` also commits.
     - For completeness, `UPDATE units SET shipping_method = 'Bogus';` should still fail — confirms the new CHECK is actually enforced and not silently dropped.
   - Edit a unit in the dev server, select `Federal Tub`, save, reload — value persists and renders on `list_units` and `view_unit`.
   - Existing units with `Box` / `Individual` still load and save unchanged.
   - Edit a unit, leave shipping method blank, save — verify it round-trips as blank (form's `('', '')` choice → `Unit.update_from_form` writes `NULL`, which the CHECK permits; an empty string would violate it, so this is a real regression surface).
   - `GET /request_info/<autoid>` for a request whose unit uses `Federal Tub` returns `"unit_shipping_method": "Federal Tub"`.
   - Render the server-side DYMO XML label (`request_label.xml`) for that same request and confirm the text fits.
   - Render a `tools/label.py` label for the same request and confirm the text fits.
   - `alembic downgrade -1` then `upgrade head` round-trips; downgrade refuses to run if any unit still uses `Federal Tub`.

## Out of scope

- Renaming the enum, normalizing to a lookup table, or changing how the label tool formats the method.
- Backfilling any existing units to the new value.
- Changes to `build/` (stale build artifact) or `tools/migrate.py` (one-shot legacy importer; the source DB has no `Federal Tub` rows to migrate).
