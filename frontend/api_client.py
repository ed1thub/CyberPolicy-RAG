"""HTTP client for the CyberPolicy-RAG backend API."""

import os
from typing import Any

import requests

_BASE_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
_TIMEOUT = 15  # seconds


class ApiClient:
    """Thin requests wrapper for the backend REST API.

    All methods return None on network / connection errors.
    Methods that hit protected endpoints return None on HTTP 4xx/5xx unless
    the caller needs the error body (e.g. chat, which returns the full
    response dict so the frontend can display blocked / no-source answers).
    """

    def __init__(self, base_url: str = _BASE_URL) -> None:
        self.base_url = base_url

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def login(self, username: str, password: str) -> dict[str, Any] | None:
        """POST /auth/login with form-encoded credentials.

        Returns ``{"access_token": ..., "token_type": "bearer"}`` on success,
        ``None`` on bad credentials or network error.
        """
        try:
            response = requests.post(
                f"{self.base_url}/auth/login",
                data={"username": username, "password": password},
                timeout=_TIMEOUT,
            )
            return response.json() if response.ok else None
        except requests.RequestException:
            return None

    def get_me(self, token: str) -> dict[str, Any] | None:
        """GET /auth/me — current user's username and role.

        Returns ``{"username": ..., "role": ...}`` or None on failure.
        """
        try:
            response = requests.get(
                f"{self.base_url}/auth/me",
                headers=self._auth_headers(token),
                timeout=_TIMEOUT,
            )
            return response.json() if response.ok else None
        except requests.RequestException:
            return None

    def chat(self, question: str, token: str) -> dict[str, Any] | None:
        """POST /chat/query — send a question and return the full response dict.

        Returns the JSON body for any HTTP status so the frontend can display
        blocked / no-source responses as well as valid answers.
        Returns None only on network / connection error.
        """
        try:
            response = requests.post(
                f"{self.base_url}/chat/query",
                json={"question": question},
                headers=self._auth_headers(token),
                timeout=_TIMEOUT,
            )
            return response.json()
        except requests.RequestException:
            return None

    def upload_document(
        self,
        file_bytes: bytes,
        filename: str,
        title: str,
        sensitivity_level: str,
        allowed_roles: str,
        token: str,
    ) -> dict[str, Any] | None:
        """POST /documents/upload — multipart form upload.

        Returns the JSON response body (success or error detail) on any HTTP
        response, None only on network / connection error.
        Do NOT include Content-Type in headers — requests sets the multipart
        boundary automatically.
        """
        try:
            response = requests.post(
                f"{self.base_url}/documents/upload",
                files={"file": (filename, file_bytes, "application/octet-stream")},
                data={
                    "title": title,
                    "sensitivity_level": sensitivity_level,
                    "allowed_roles": allowed_roles,
                },
                headers=self._auth_headers(token),
                timeout=_TIMEOUT,
            )
            return response.json()
        except requests.RequestException:
            return None

    def get_audit_logs(self, token: str) -> list[dict[str, Any]] | None:
        """GET /audit/logs — all audit log entries.

        Returns a list of log dicts on success, None on failure.
        """
        try:
            response = requests.get(
                f"{self.base_url}/audit/logs",
                headers=self._auth_headers(token),
                timeout=_TIMEOUT,
            )
            return response.json() if response.ok else None
        except requests.RequestException:
            return None

    def health(self) -> bool:
        """GET /health — returns True if backend is reachable."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.ok
        except requests.RequestException:
            return False
