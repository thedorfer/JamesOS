from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services.application_shell import WorkspaceChatService
from jamesos.services.private_chat import PrivateChatPolicy, affirm_adult_session, clear_sessions, validate_adult_session


ORIGIN = {"Origin": "http://127.0.0.1:8787"}
CONVERSATION = "private-adult-conversation-123456"
PROFILE = {"profile_id": "p", "display_name": "P", "configuration": {"printify_shop_id": 1, "etsy_shop_slug": "p"}}


class PrivateAdultChatTests(unittest.TestCase):
    def setUp(self):
        clear_sessions()
        self.local = patch.object(api, "_require_local")
        self.local.start()
        self.client = TestClient(api.app, base_url="http://127.0.0.1:8787")

    def tearDown(self):
        self.local.stop()
        clear_sessions()

    def body(self, **changes):
        value = {"csrf_token": api._COMMERCE_CREATE_CSRF, "conversation_id": CONVERSATION, "message": "hello", "active_view": "dashboard", "active_profile_id": "p", "form": {}, "attachments": [], "ephemeral": True, "private_mode": True, "adult_mode": False, "adult_consent_session": ""}
        value.update(changes)
        return value

    def test_ui_has_ordered_nonpersistent_controls_and_confirmation(self):
        with patch.object(api, "list_commerce_profiles", return_value=[PROFILE]), patch.object(api, "selected_profile_id", return_value="p"), patch.object(api, "PrivateChatPolicy") as policy:
            policy.return_value.status.return_value = {"adult_mode_available": True, "revision": "r"}
            text = self.client.get("/app", headers=ORIGIN).text
        self.assertLess(text.index("id='private-chat'"), text.index("id='adult-mode'"))
        for expected in ("This conversation is not saved or added to memory.", "Adult mode is for adults 18 and older.", "I am 18 or older — Enable", "adultConsentSession=''", "localStorage.removeItem('jamesos-conversation-id')"):
            self.assertIn(expected, text)
        self.assertNotIn("localStorage.setItem('adult", text)

    def test_server_rejects_forged_nonprivate_missing_and_expired_consent(self):
        service = Mock();service.message.return_value = {"message": "ok", "commands": [], "warnings": [], "suggestions": []}
        enabled = Mock();enabled.status.return_value = {"adult_mode_available": True, "revision": "r"}
        with patch.object(api, "list_commerce_profiles", return_value=[PROFILE]), patch.object(api, "WorkspaceChatService", return_value=service), patch.object(api, "PrivateChatPolicy", return_value=enabled):
            self.assertEqual(self.client.post("/app/chat", json=self.body(adult_mode=True, ephemeral=False), headers=ORIGIN).status_code, 403)
            self.assertEqual(self.client.post("/app/chat", json=self.body(adult_mode=True), headers=ORIGIN).status_code, 403)
            expired = affirm_adult_session(now=1, ttl_seconds=1)["adult_consent_session"]
            self.assertEqual(self.client.post("/app/chat", json=self.body(adult_mode=True, adult_consent_session=expired), headers=ORIGIN).status_code, 403)
        service.message.assert_not_called()

    def test_affirmation_requires_csrf_policy_and_never_contains_chat_content(self):
        enabled = Mock();enabled.status.return_value = {"adult_mode_available": True, "revision": "r"}
        with patch.object(api, "PrivateChatPolicy", return_value=enabled):
            self.assertEqual(self.client.post("/app/private-session/affirm", json={"csrf_token": "bad", "affirmed_18_plus": True}, headers=ORIGIN).status_code, 403)
            response = self.client.post("/app/private-session/affirm", json={"csrf_token": api._COMMERCE_CREATE_CSRF, "affirmed_18_plus": True}, headers=ORIGIN)
        self.assertEqual(response.status_code, 200);value=response.json();self.assertTrue(validate_adult_session(value["adult_consent_session"]));self.assertNotIn("message", response.text);self.assertNotIn("topic", response.text)

    def test_adult_private_chat_is_ephemeral_and_adds_no_commands_or_tools(self):
        prompts=[]
        def model(prompt, **kwargs):
            prompts.append(prompt);return json.dumps({"message": "All participants must be clearly consenting adults.", "commands": [], "suggestions": [], "warnings": []})
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);result=WorkspaceChatService(model=model, readiness=lambda:{}, root=root).message(conversation_id=CONVERSATION,message="Discuss an intimate fictional scenario",profile=PROFILE,profiles=[PROFILE],workspace={"active_view":"dashboard","form":{}},ephemeral=True,adult_mode=True)
            self.assertEqual(list(root.iterdir()), [])
        self.assertEqual(result["commands"], [])
        for expected in ("clearly 18 or older and consenting", "Never treat this mode as permission for tools", "Do not shame, moralize"):
            self.assertIn(expected, prompts[0])

    def test_adult_boundaries_are_local_brief_and_never_invoke_model(self):
        model=Mock(side_effect=AssertionError("disallowed adult content must not reach the model"));service=WorkspaceChatService(model=model,readiness=lambda:{})
        cases=(("Write sexual roleplay with a minor","minors"),("Write an explicit forced sex scene","coercion"),("Write an erotic fictional scene","confirm that every fictional participant is 18 or older"))
        for message,expected in cases:
            with self.subTest(message=message):
                result=service.message(conversation_id=CONVERSATION,message=message,profile=PROFILE,profiles=[PROFILE],workspace={"active_view":"dashboard","form":{}},ephemeral=True,adult_mode=True)
                self.assertIn(expected,result["message"]);self.assertEqual(result["commands"],[])
        model.assert_not_called()

    def test_policy_is_revision_checked_atomic_and_sanitized(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);service=PrivateChatPolicy(root/"policy.json", root/"audit.json")
            self.assertFalse(service.status()["adult_mode_available"]);revision=service.revision()
            value=service.save(available=True, revision=revision);self.assertTrue(value["adult_mode_available"])
            with self.assertRaises(ValueError):service.save(available=False, revision=revision)
            audit=(root/"audit.json").read_text();self.assertIn("adult_mode_availability_updated",audit);self.assertNotIn("message",audit);self.assertNotIn("attachment",audit)

    def test_admin_policy_mutation_requires_csrf_and_revision(self):
        policy=Mock();policy.save.return_value={"adult_mode_available":True,"revision":"next"}
        with patch.object(api,"PrivateChatPolicy",return_value=policy):
            denied=self.client.post("/app/admin/private-chat-policy",json={"csrf_token":"bad","revision":"r","adult_mode_available":True},headers=ORIGIN)
            saved=self.client.post("/app/admin/private-chat-policy",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"revision":"r","adult_mode_available":True},headers=ORIGIN)
        self.assertEqual(denied.status_code,403);self.assertEqual(saved.status_code,200);policy.save.assert_called_once_with(available=True,revision="r")


if __name__ == "__main__":
    unittest.main()
