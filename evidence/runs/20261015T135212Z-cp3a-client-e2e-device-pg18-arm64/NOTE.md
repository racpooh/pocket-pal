# NOTE

Invalid run: the backend did not start — pixeltable_pgserver returned before Postgres accepted connections (cold start), so psql failed. Fixed by retrying in dev_server.py/local_pg.py; see the next cp3a-client-e2e-device run.
