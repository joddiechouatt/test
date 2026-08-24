This directory is empty by default (git can't track an empty folder, so
this file is what keeps it present in the repo).

`app.py` no longer reads anything from here — every topic (featured or
free-text search) runs the pipeline live now, per-session, and nothing is
persisted to disk from the app itself.

Two things can still populate this directory locally:

- `python run_pipeline.py "<topic>"` (see the root README) writes
  `data/<topic-slug>.json` here — a standalone CLI convenience for
  inspecting a full pipeline run's output on disk, unrelated to what the
  running app reads.
- `analyzer.py`'s per-article disk cache lives at `data/.cache/`, created
  on demand and gitignored.
