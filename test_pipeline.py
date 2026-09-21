import json
import hashlib
import hmac

from fastapi.testclient import TestClient
from services.outbound import is_retryable_response, retry_backoff_seconds

from main import app


SCENARIOS = [
    (
        "VALIDATED clean payload",
        {"customer_id": "CID-9982", "email_address": "carlo@rebyuwer.com", "stock_count": 150},
        200,
        "validated",
    ),
    (
        "HEALED key and type corruption",
        {"client_num": "CID-2026", "user_email": "test@gmail.com", "qty_on_hand": "45"},
        200,
        "healed",
    ),
    (
        "REJECTED missing identity fields",
        {"qty_on_hand": 120},
        422,
        "rejected",
    ),
    (
        "UNCERTAIN low-confidence field",
        {
            "customer_id": "CID-7711",
            "email_address": "admin@legisarc.net",
            "xyz_random_field_99": 30,
        },
        202,
        "uncertain",
    ),
]


def run_system_diagnostic_tests() -> None:
    assert is_retryable_response(None)
    assert is_retryable_response(408)
    assert is_retryable_response(429)
    assert is_retryable_response(500)
    assert not is_retryable_response(400)
    assert not is_retryable_response(422)
    assert retry_backoff_seconds()[0] == 0
    print("[PASS] Retry policy classification and backoff schedule")
    print("========== STARTING HEALPIPE INTERNAL PIPELINE TESTING ==========")
    with TestClient(app) as client:
        bridge_response = client.post(
            "/v1/bridges",
            json={
                "bridge_name": "Pipeline Contract Test",
                "source_platform": "Test webhook",
                "target_endpoint_url": "https://example.invalid/healpipe-test",
            },
        )
        bridge_response.raise_for_status()
        bridge = bridge_response.json()
        bridge_id = bridge["bridge_id"]
        signature_secret = bridge["signature_secret"]
        proposed = client.post(
            f"/v1/bridges/{bridge_id}/mappings",
            json={"source_field": "client_num", "destination_field": "customer_id"},
        )
        assert proposed.status_code == 201, proposed.text
        assert proposed.json()["status"] == "proposed"
        approved = client.post(f"/v1/mappings/{proposed.json()['mapping_id']}/approve")
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "active"
        for name, payload, expected_status, expected_state in SCENARIOS:
            raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
            signature = hmac.new(signature_secret.encode(), raw_body, hashlib.sha256).hexdigest()
            response = client.post(
                "/v1/webhooks/receive",
                params={"bridge_id": bridge_id},
                json=payload,
                headers={"X-Webhook-Signature": f"sha256={signature}"},
            )
            body = response.json()
            assert response.status_code == expected_status, (name, body)
            assert body["status"] == expected_state, (name, body)

            if expected_state == "healed":
                assert body["payload"]["stock_count"] == 45
                assert body["key_mappings"] == {
                    "client_num": "customer_id",
                    "user_email": "email_address",
                    "qty_on_hand": "stock_count",
                }
                audit = client.get(
                    f"/v1/webhooks/events/{body['event_id']}/audit",
                    params={"bridge_id": bridge_id},
                )
                assert audit.status_code == 200, audit.text
                assert audit.json()["mapping_versions"]["client_num"] == 1

            print(f"[PASS] {name}: HTTP {response.status_code}")
            print(json.dumps(body, indent=2))

        account_a = client.post("/v1/accounts", json={"name": "Isolation Test A"}).json()
        account_b = client.post("/v1/accounts", json={"name": "Isolation Test B"}).json()
        key_a = client.post(
            f"/v1/accounts/{account_a['account_id']}/api-keys",
            json={"role": "admin", "scopes": ["bridges:write", "bridges:read", "mappings:read"]},
        ).json()["api_key"]
        key_b = client.post(
            f"/v1/accounts/{account_b['account_id']}/api-keys",
            json={"role": "admin", "scopes": ["bridges:write", "bridges:read", "mappings:read"]},
        ).json()["api_key"]
        bridge_a = client.post(
            "/v1/bridges",
            headers={"X-API-Key": key_a},
            json={"bridge_name": "Account A", "source_platform": "Test", "target_endpoint_url": "https://example.invalid/a"},
        ).json()
        bridge_b = client.post(
            "/v1/bridges",
            headers={"X-API-Key": key_b},
            json={"bridge_name": "Account B", "source_platform": "Test", "target_endpoint_url": "https://example.invalid/b"},
        ).json()
        visible_to_a = client.get("/v1/bridges", headers={"X-API-Key": key_a}).json()
        assert {item["bridge_id"] for item in visible_to_a} == {bridge_a["bridge_id"]}
        cross_account = client.get(
            f"/v1/bridges/{bridge_b['bridge_id']}/mappings",
            headers={"X-API-Key": key_a},
        )
        assert cross_account.status_code == 404
        print("[PASS] Account isolation: cross-account bridge access denied")

    print("========== SYSTEM DIAGNOSTIC COMPLETED: ALL TESTS PASSED ==========")


if __name__ == "__main__":
    run_system_diagnostic_tests()
