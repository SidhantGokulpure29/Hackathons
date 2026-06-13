# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Task catalogue for the pull request review environment."""

from __future__ import annotations

from typing import Any


REVIEW_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["findings", "overall_summary", "confidence", "test_plan"],
    "properties": {
        "findings": {
            "type": "array",
            "description": "List of review findings sorted by importance.",
            "items": {
                "type": "object",
                "required": ["file", "severity", "category", "title", "explanation", "suggested_fix"],
                "properties": {
                    "file": {"type": "string"},
                    "severity": {"type": "string"},
                    "category": {"type": "string"},
                    "title": {"type": "string"},
                    "explanation": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
            },
        },
        "overall_summary": {"type": "string"},
        "confidence": {"type": "number"},
        "test_plan": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


REVIEW_TASKS: list[dict[str, Any]] = [
    {
        "id": "easy-auth-token-leak",
        "title": "Authentication Helper Cleanup",
        "difficulty": "easy",
        "scenario": (
            "A platform team merged a small auth helper refactor for an internal admin API. "
            "The PR claims it only simplifies logging and token validation."
        ),
        "pull_request_summary": (
            "Refactors token validation in the admin API authentication middleware."
        ),
        "changed_files": ["api/auth.py"],
        "diff_text": """diff --git a/api/auth.py b/api/auth.py
index b31e5c2..e4db61b 100644
--- a/api/auth.py
+++ b/api/auth.py
@@ -1,13 +1,15 @@
 import os
-from hmac import compare_digest
 import logging
 
 logger = logging.getLogger(__name__)
 
 def is_request_authorized(provided_token: str) -> bool:
-    expected_token = os.getenv("ADMIN_API_TOKEN", "")
-    return compare_digest(provided_token, expected_token)
+    expected_token = os.getenv("ADMIN_API_TOKEN", "")
+    return provided_token == expected_token
 
 def log_failed_attempt(username: str, provided_token: str) -> None:
-    logger.warning("admin login failed for user=%s", username)
+    logger.warning(
+        "admin login failed user=%s token=%s",
+        username,
+        provided_token,
+    )
""",
        "expected_findings": [
            {
                "id": "timing-safe-comparison",
                "file": "api/auth.py",
                "severity": "high",
                "category": "security",
                "match_keywords": ["compare_digest", "timing", "token comparison", "constant time"],
                "explanation_keywords": ["timing", "bruteforce", "token", "leak"],
                "suggested_fix_keywords": ["compare_digest", "constant-time"],
            },
            {
                "id": "secret-in-logs",
                "file": "api/auth.py",
                "severity": "critical",
                "category": "security",
                "match_keywords": ["log", "token", "secret", "credential"],
                "explanation_keywords": ["token", "logs", "secret", "credential"],
                "suggested_fix_keywords": ["remove", "redact", "mask"],
            },
        ],
        "summary_keywords": ["secrets", "authentication", "timing"],
        "test_keywords": [
            "assert tokens are not logged",
            "compare_digest",
            "constant-time comparison",
        ],
    },
    {
        "id": "medium-billing-idempotency",
        "title": "Billing Retry Resilience",
        "difficulty": "medium",
        "scenario": (
            "The billing team added retry support for subscription renewals after seeing flaky "
            "payment gateway timeouts. The PR touched payment orchestration and webhook handling."
        ),
        "pull_request_summary": (
            "Adds retry logic to recurring billing and simplifies webhook status handling."
        ),
        "changed_files": ["billing/service.py", "billing/webhooks.py"],
        "diff_text": """diff --git a/billing/service.py b/billing/service.py
index 4bcb36a..69f40c2 100644
--- a/billing/service.py
+++ b/billing/service.py
@@ -48,14 +48,18 @@ def charge_subscription(customer_id: str, amount_cents: int) -> dict:
-    payment = gateway.charge(customer_id=customer_id, amount_cents=amount_cents)
-    db.record_charge(payment["id"], customer_id, amount_cents)
-    return payment
+    for _ in range(3):
+        payment = gateway.charge(customer_id=customer_id, amount_cents=amount_cents)
+        db.record_charge(payment["id"], customer_id, amount_cents)
+    return payment
 
diff --git a/billing/webhooks.py b/billing/webhooks.py
index 932acdf..1b6f44a 100644
--- a/billing/webhooks.py
+++ b/billing/webhooks.py
@@ -10,9 +10,8 @@ def handle_gateway_event(payload: dict) -> None:
-    if payload["status"] == "succeeded":
-        db.mark_invoice_paid(payload["invoice_id"])
-    elif payload["status"] == "failed":
-        db.mark_invoice_failed(payload["invoice_id"])
+    if payload["status"] != "failed":
+        db.mark_invoice_paid(payload["invoice_id"])
""",
        "expected_findings": [
            {
                "id": "duplicate-charges",
                "file": "billing/service.py",
                "severity": "critical",
                "category": "logic",
                "match_keywords": ["duplicate", "charge", "idempotency", "retry"],
                "explanation_keywords": ["three times", "multiple charges", "retry"],
                "suggested_fix_keywords": ["idempotency key", "break", "retry only on failure"],
            },
            {
                "id": "webhook-paid-on-pending",
                "file": "billing/webhooks.py",
                "severity": "high",
                "category": "logic",
                "match_keywords": ["pending", "paid", "status", "webhook"],
                "explanation_keywords": ["non-failed", "pending", "refunded", "paid"],
                "suggested_fix_keywords": ["explicit status", "succeeded only"],
            },
        ],
        "summary_keywords": ["billing", "idempotency", "invoice"],
        "test_keywords": [
            "retries do not create duplicate charges",
            "pending webhook should not mark invoice paid",
            "refunded webhook should not mark invoice paid",
        ],
    },
    {
        "id": "hard-export-authorization",
        "title": "Customer Data Export Endpoint",
        "difficulty": "hard",
        "scenario": (
            "A data platform team added an endpoint for customer support to export incident data "
            "during escalations. The PR claims it only exposes existing records to authenticated staff."
        ),
        "pull_request_summary": (
            "Adds a support export endpoint and expands returned fields for investigation."
        ),
        "changed_files": ["support/routes.py", "support/serializer.py"],
        "diff_text": """diff --git a/support/routes.py b/support/routes.py
index 40f113d..89ae3de 100644
--- a/support/routes.py
+++ b/support/routes.py
@@ -1,17 +1,16 @@
 from fastapi import APIRouter, Depends
 from .auth import current_user, require_scope
 from .service import export_ticket_bundle
 
 router = APIRouter()
 
 @router.get("/tickets/{ticket_id}/export")
 def export_ticket(ticket_id: str, user=Depends(current_user)):
-    require_scope(user, "support.export")
     bundle = export_ticket_bundle(ticket_id)
     return bundle
 
diff --git a/support/serializer.py b/support/serializer.py
index 658b1f0..31cd7f2 100644
--- a/support/serializer.py
+++ b/support/serializer.py
@@ -8,7 +8,15 @@ def serialize_ticket(ticket: dict) -> dict:
     return {
         "ticket_id": ticket["ticket_id"],
         "subject": ticket["subject"],
-        "customer_email": ticket["customer_email_masked"],
+        "customer_email": ticket["customer_email"],
+        "billing_address": ticket["billing_address"],
+        "session_token": ticket["session_token"],
         "messages": ticket["messages"],
     }
""",
        "expected_findings": [
            {
                "id": "missing-authorization",
                "file": "support/routes.py",
                "severity": "critical",
                "category": "security",
                "match_keywords": ["authorization", "scope", "permission", "access control"],
                "explanation_keywords": ["require_scope", "unauthorized", "export"],
                "suggested_fix_keywords": ["restore require_scope", "enforce support.export"],
            },
            {
                "id": "pii-exposure",
                "file": "support/serializer.py",
                "severity": "critical",
                "category": "privacy",
                "match_keywords": ["pii", "email", "billing address", "sensitive"],
                "explanation_keywords": ["email", "billing address", "masked", "exposure"],
                "suggested_fix_keywords": ["masked", "redact", "minimize"],
            },
            {
                "id": "session-token-exposure",
                "file": "support/serializer.py",
                "severity": "critical",
                "category": "security",
                "match_keywords": ["session token", "token", "credential", "secret"],
                "explanation_keywords": ["session", "token", "account takeover", "credential"],
                "suggested_fix_keywords": ["remove", "redact", "never return token"],
            },
        ],
        "summary_keywords": ["authorization", "pii", "support export"],
        "test_keywords": [
            "forbidden without support.export scope",
            "response does not include session_token",
            "response returns masked email only",
        ],
    },
]


def public_task_view(task: dict[str, Any]) -> dict[str, Any]:
    """Return the observable part of a task."""

    return {
        "task_id": task["id"],
        "title": task["title"],
        "difficulty": task["difficulty"],
        "scenario": task["scenario"],
        "pull_request_summary": task["pull_request_summary"],
        "diff_text": task["diff_text"],
        "changed_files": task["changed_files"],
        "review_schema": REVIEW_OUTPUT_SCHEMA,
    }


def build_reference_review(task: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic reference review payload for grader validation."""

    findings = []
    for issue in task["expected_findings"]:
        findings.append(
            {
                "file": issue["file"],
                "severity": issue["severity"],
                "category": issue["category"],
                "title": issue["match_keywords"][0].title(),
                "explanation": " ".join(issue["explanation_keywords"]),
                "suggested_fix": " ".join(issue["suggested_fix_keywords"]),
            }
        )
    return {
        "findings": findings,
        "overall_summary": " ".join(task["summary_keywords"]),
        "confidence": 0.9,
        "test_plan": task["test_keywords"],
    }
