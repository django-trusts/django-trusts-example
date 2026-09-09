"""PostgreSQL settings for the bounded Windows ACL evaluator.

Default example settings stay SQLite. Point this module at PostgreSQL 14+
without changing the existing projects suite.

  DATABASE_URL=postgres://USER:PASS@127.0.0.1:5432/DB \\
    python manage.py test winfs --settings=example.settings_winfs
"""

import os

import dj_database_url

from example.settings import *  # noqa: F403

_DEFAULT = "postgres://winfs:winfs@127.0.0.1:5432/winfs"
_url = os.environ.get("DATABASE_URL") or os.environ.get("WINFS_DATABASE_URL") or _DEFAULT
if not _url.startswith(("postgres://", "postgresql://")):
    _url = os.environ.get("WINFS_DATABASE_URL") or _DEFAULT

DATABASES = {
    "default": dj_database_url.parse(_url, conn_max_age=0),
}
