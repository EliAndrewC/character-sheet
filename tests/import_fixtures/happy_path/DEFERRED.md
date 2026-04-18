# Deferred happy-path fixtures

One happy-path format listed in design.md §13.1 is **not** generated:

- `happy_sxw.sxw` - pre-fork OpenOffice Writer. Two reasons it's not here:
  1. No pure-Python library can write `.sxw`.
  2. Modern LibreOffice has dropped the `.sxw` export filter, so
     `soffice --headless --convert-to sxw` fails.

  The `.sxw` extractor code path will still be written in Phase 3
  (`odfpy` can read `.sxw` - or at least tries to). If a player provides
  a real `.sxw` character sheet we drop it in here and add a fixture-
  backed test at that time.

`happy_legacy_doc.doc` used to live on this list but is now generated
by `regenerate_happy_path.py` via LibreOffice headless. In a fresh
container, run:

    sudo apt-get update
    sudo apt-get install -y --no-install-recommends libreoffice-core libreoffice-writer

before running the regenerator if you want the `.doc` fixture refreshed.
Without LibreOffice, the regenerator logs a skip line and the existing
committed `.doc` remains unchanged.
