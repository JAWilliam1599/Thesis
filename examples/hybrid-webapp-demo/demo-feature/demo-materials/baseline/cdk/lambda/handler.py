"""Backend API for the hybrid guestbook demo.

Runs inside the VPC (private-isolated subnets) and reaches the on-prem
PostgreSQL database over the Tailscale subnet route. Credentials are read from
AWS Secrets Manager at cold start — nothing sensitive is baked into the code or
the environment.

Routes (via API Gateway):
  GET  /guestbook  -> list the most recent entries
  POST /guestbook  -> add an entry  {"name": "...", "message": "..."}
"""
import json
import os

import boto3
import psycopg2
import psycopg2.extras

_secrets_client = boto3.client("secretsmanager")
_db_config = None


def _load_db_config():
    """Fetch and cache DB connection details from Secrets Manager."""
    global _db_config
    if _db_config is None:
        secret_arn = os.environ["DB_SECRET_ARN"]
        raw = _secrets_client.get_secret_value(SecretId=secret_arn)["SecretString"]
        secret = json.loads(raw)
        _db_config = {
            "host": secret.get("host") or os.environ["DB_HOST"],
            "port": int(secret.get("port", 5432)),
            "dbname": secret.get("dbname") or os.environ["DB_NAME"],
            "user": secret["username"],
            "password": secret["password"],
        }
    return _db_config


def _connect():
    cfg = _load_db_config()
    return psycopg2.connect(connect_timeout=5, **cfg)


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }


def _list_entries():
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, name, message, created_at "
                "FROM guestbook ORDER BY created_at DESC LIMIT 50"
            )
            return cur.fetchall()


def _add_entry(name, message):
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO guestbook (name, message) VALUES (%s, %s) "
                "RETURNING id, name, message, created_at",
                (name, message),
            )
            row = cur.fetchone()
        conn.commit()
        return row


def handler(event, _context):
    method = event.get("httpMethod", "GET")
    try:
        if method == "GET":
            return _response(200, {"entries": _list_entries()})

        if method == "POST":
            payload = json.loads(event.get("body") or "{}")
            name = (payload.get("name") or "").strip()
            message = (payload.get("message") or "").strip()
            if not name or not message:
                return _response(400, {"error": "name and message are required"})
            return _response(201, {"entry": _add_entry(name[:80], message[:500])})

        return _response(405, {"error": f"method {method} not allowed"})
    except psycopg2.Error as exc:
        return _response(502, {"error": "database error", "detail": str(exc)})
    except Exception as exc:  # noqa: BLE001 - surface config errors to the caller
        return _response(500, {"error": "internal error", "detail": str(exc)})
