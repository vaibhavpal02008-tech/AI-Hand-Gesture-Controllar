import io
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from server_backend import create_app


class ServerBackendTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = create_app(Path(self.temporary_directory.name))
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        session = self.client.get("/api/session").get_json()
        self.csrf = {"X-CSRF-Token": session["csrfToken"]}

    def tearDown(self):
        self.temporary_directory.cleanup()

    def create_account(self, email="person@example.test"):
        response = self.client.post(
            "/api/auth/signup",
            json={"name": "Test Person", "email": email, "password": "MyCustomPassword-2026!"},
            headers=self.csrf,
        )
        self.assertEqual(response.status_code, 201)
        verify_path = urlparse(response.get_json()["verificationUrl"]).path
        self.assertEqual(self.client.get(verify_path).status_code, 302)
        response = self.client.post(
            "/api/auth/login",
            json={"email": email, "password": "MyCustomPassword-2026!"},
            headers=self.csrf,
        )
        self.assertEqual(response.status_code, 200)
        self.csrf = {"X-CSRF-Token": response.get_json()["csrfToken"]}

    def test_account_verification_and_password_reset(self):
        response = self.client.post(
            "/api/auth/signup",
            json={"name": "Test Person", "email": "person@example.test", "password": "MyCustomPassword-2026!"},
            headers=self.csrf,
        )
        self.assertEqual(response.status_code, 201)
        verify_path = urlparse(response.get_json()["verificationUrl"]).path
        self.assertEqual(self.client.get(verify_path).status_code, 302)
        reset = self.client.post(
            "/api/auth/forgot", json={"email": "person@example.test"}, headers=self.csrf
        ).get_json()
        reset_token = urlparse(reset["resetUrl"]).path.rsplit("/", 1)[-1]
        changed = self.client.post(
            "/api/auth/reset",
            json={"token": reset_token, "password": "AnotherCustomPassword-2026!"},
            headers=self.csrf,
        )
        self.assertEqual(changed.status_code, 200)
        login = self.client.post(
            "/api/auth/login",
            json={"email": "person@example.test", "password": "AnotherCustomPassword-2026!"},
            headers=self.csrf,
        )
        self.assertEqual(login.status_code, 200)

    def test_note_ownership_upload_and_share_revocation(self):
        self.create_account()
        response = self.client.post(
            "/api/notes",
            json={"title": "Lab note", "body": "Private", "folder": "Science", "tags": ["lab"], "visibility": "link"},
            headers=self.csrf,
        )
        self.assertEqual(response.status_code, 201)
        note = response.get_json()["note"]
        upload = self.client.post(
            f"/api/notes/{note['id']}/attachments",
            data={"files": (io.BytesIO(b"%PDF-1.4\n%%EOF"), "lab.pdf")},
            headers=self.csrf,
            content_type="multipart/form-data",
        )
        self.assertEqual(upload.status_code, 200)
        attachment_url = upload.get_json()["note"]["attachments"][0]["url"]
        self.assertEqual(self.client.get(attachment_url).status_code, 200)

        token = note["shareUrl"].rsplit("/", 1)[-1]
        self.assertEqual(self.client.get(f"/api/shared/{token}").status_code, 200)
        self.assertIn(b"<iframe", self.client.get(f"/s/{token}").data)
        self.client.post(
            f"/api/notes/{note['id']}/share", json={"visibility": "private"}, headers=self.csrf
        )
        self.assertEqual(self.client.get(f"/api/shared/{token}").status_code, 404)

        other = self.app.test_client()
        other_session = other.get("/api/session").get_json()
        other_csrf = {"X-CSRF-Token": other_session["csrfToken"]}
        other_signup = other.post(
            "/api/auth/signup",
            json={"name": "Other Person", "email": "other@example.test", "password": "MyCustomPassword-2026!"},
            headers=other_csrf,
        )
        other_verify_path = urlparse(other_signup.get_json()["verificationUrl"]).path
        self.assertEqual(other.get(other_verify_path).status_code, 302)
        other_login = other.post(
            "/api/auth/login",
            json={"email": "other@example.test", "password": "MyCustomPassword-2026!"},
            headers=other_csrf,
        )
        self.assertEqual(other_login.status_code, 200)
        other_csrf = {"X-CSRF-Token": other_login.get_json()["csrfToken"]}
        self.assertEqual(other.get("/api/notes").get_json()["notes"], [])
        forbidden = other.patch(
            f"/api/notes/{note['id']}",
            json={"title": "Not allowed", "body": "Cross-account write"},
            headers=other_csrf,
        )
        self.assertEqual(forbidden.status_code, 404)

    def test_upload_rejects_invalid_pdf_and_csrf(self):
        self.create_account()
        note = self.client.post(
            "/api/notes", json={"title": "File note", "body": "Test"}, headers=self.csrf
        ).get_json()["note"]
        invalid = self.client.post(
            f"/api/notes/{note['id']}/attachments",
            data={"files": (io.BytesIO(b"not a PDF"), "fake.pdf")},
            headers=self.csrf,
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid.status_code, 415)
        missing_csrf = self.client.post("/api/notes", json={"title": "No token", "body": "blocked"})
        self.assertEqual(missing_csrf.status_code, 400)


if __name__ == "__main__":
    unittest.main()
