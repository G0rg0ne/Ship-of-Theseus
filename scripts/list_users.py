#!/usr/bin/env python3
"""
List users in the Ship of Theseus PostgreSQL database.
Run from repo root. Requires backend .env (or env vars) and psycopg2.

From WSL with Docker: ensure POSTGRES host is localhost and port 5432.
Example: DATABASE_URL=postgresql://postgres:postgres@localhost:5432/shipoftheseus
"""
import os
import sys

# Load .env from project root (parent of scripts/)
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(repo_root, ".env")
if os.path.isfile(env_path):
    from dotenv import load_dotenv
    load_dotenv(env_path)

# Use sync URL for psycopg2 (replace asyncpg with nothing or psycopg2)
database_url = os.environ.get("DATABASE_URL", "").strip()
if not database_url:
    print("DATABASE_URL not set. Set it in .env or environment.", file=sys.stderr)
    sys.exit(1)
# Support asyncpg URL from config: convert to sync for this script
if "asyncpg" in database_url:
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
elif database_url.startswith("postgresql://"):
    pass
else:
    print("DATABASE_URL must be postgresql://... or postgresql+asyncpg://...", file=sys.stderr)
    sys.exit(1)

# When running from host (WSL), Docker exposes postgres on localhost
# If your .env uses host "postgres", override: LIST_USERS_HOST=localhost
host_override = os.environ.get("LIST_USERS_HOST")
if host_override:
    from urllib.parse import urlparse, urlunparse
    p = urlparse(database_url)
    netloc = f"{p.username}:{p.password}@{host_override}:{p.port or 5432}" if p.username else f"{host_override}:{p.port or 5432}"
    database_url = urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))

def main():
    try:
        import psycopg2
    except ImportError:
        print("Install psycopg2: pip install psycopg2-binary", file=sys.stderr)
        sys.exit(1)

    try:
        conn = psycopg2.connect(database_url)
    except Exception as e:
        print(f"Cannot connect to database: {e}", file=sys.stderr)
        print("From WSL, ensure containers are up and use host localhost (e.g. LIST_USERS_HOST=localhost).", file=sys.stderr)
        sys.exit(1)

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, username, email, is_active, created_at
            FROM users
            ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()
        if not rows:
            print("No users in database.")
            return
        print(f"{'ID':<38} {'USERNAME':<20} {'EMAIL':<30} {'ACTIVE':<6} CREATED_AT")
        print("-" * 110)
        for row in rows:
            uid, username, email, is_active, created_at = row
            print(f"{str(uid):<38} {username:<20} {email:<30} {str(is_active):<6} {created_at}")
        print(f"\nTotal: {len(rows)} user(s)")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
