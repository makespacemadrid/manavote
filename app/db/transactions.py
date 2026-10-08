"""Write transactions for use cases that already own commit/rollback."""
from contextlib import contextmanager


@contextmanager
def write_transaction(connection):
    # Reserve SQLite's writer before reading state and budget; two callers must
    # not both compute a transition from the same pre-commit snapshot.
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    finally:
        if connection.in_transaction:
            connection.rollback()
