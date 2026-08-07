"""Bundled application handler for the mlrisk fixture.

Injected weakness (moderate, individually remediable):
  * certificate validation disabled on an outbound call to an internal service

This is the cloud-side code analogue of the TLS weakness carried by the
on-premises ``ans-review`` fixture.  It appears nowhere in the synthesised
CloudFormation template, so no infrastructure scanner on the cloud path can
observe it.
"""
import json
import os

import requests

INVENTORY_URL = os.environ.get("INVENTORY_URL", "https://inventory.internal/items")
REQUEST_TIMEOUT_S = 5


def handler(event, context):
    item_id = (event or {}).get("itemId")
    if not item_id:
        return {"statusCode": 400, "body": json.dumps({"error": "itemId required"})}

    # WEAKNESS: the internal endpoint presents a private CA certificate, and
    # validation was switched off rather than the CA being trusted.
    response = requests.get(
        f"{INVENTORY_URL}/{item_id}",
        timeout=REQUEST_TIMEOUT_S,
        verify=False,
    )
    response.raise_for_status()

    return {"statusCode": 200, "body": json.dumps(response.json())}
