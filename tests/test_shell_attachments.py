from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from unittest.mock import Mock

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services import shell_attachments as attachments


CONVERSATION="conversation-12345678901234567890"
ORIGIN={"Origin":"http://127.0.0.1:8787"}


class ShellAttachmentTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.root=Path(self.temporary.name)/"private"
        self.root_patch=patch.object(attachments,"ROOT",self.root);self.root_patch.start()
        self.local_patch=patch.object(api,"_require_local");self.local_patch.start()
        self.client=TestClient(api.app,base_url="http://127.0.0.1:8787")

    def tearDown(self):
        self.local_patch.stop();self.root_patch.stop();self.temporary.cleanup()

    def upload(self,name="note.txt",data=b"safe note",mime="text/plain",csrf=api._COMMERCE_CREATE_CSRF,origin=ORIGIN,conversation=CONVERSATION):
        return self.client.post("/app/attachments",data={"csrf_token":csrf,"conversation_id":conversation},files={"file":(name,data,mime)},headers=origin)

    def test_csrf_origin_and_access_policy_are_required(self):
        self.assertEqual(self.upload(csrf="bad").status_code,403)
        self.assertEqual(self.upload(origin={"Origin":"https://evil.example"}).status_code,403)
        with patch.object(api,"_require_local",side_effect=__import__("fastapi").HTTPException(403,"denied")):
            self.assertEqual(self.upload().status_code,403)

    def test_generated_private_names_sanitized_response_and_no_execution(self):
        marker=Path(self.temporary.name)/"executed"
        response=self.upload("../../note.txt",f"safe text; touch {marker}".encode())
        self.assertEqual(response.status_code,200,response.text);value=response.json()
        self.assertEqual(value["filename"],"note.txt");self.assertNotIn(str(self.root),response.text);self.assertFalse(marker.exists())
        stored=self.root/CONVERSATION/value["attachment_id"]
        self.assertTrue(stored.is_file());self.assertNotEqual(stored.name,value["filename"]);self.assertTrue(stored.resolve().is_relative_to(self.root.resolve()))

    def test_size_type_script_archive_and_signature_rejections(self):
        cases=(
            ("large.txt",b"x"*(attachments.MAX_BYTES+1),"text/plain"),
            ("run.sh",b"echo unsafe","text/x-shellscript"),
            ("fake.txt",b"#!/bin/sh\necho unsafe","text/plain"),
            ("archive.txt",b"PK\x03\x04payload","text/plain"),
            ("fake.pdf",b"not a pdf","application/pdf"),
            ("fake.png",b"not a png","image/png"),
        )
        for name,data,mime in cases:
            with self.subTest(name=name):self.assertEqual(self.upload(name,data,mime).status_code,422)

    def test_conversation_ownership_unknown_ids_and_metadata_tampering_rejected(self):
        item=self.upload().json();profile={"profile_id":"x","display_name":"X","configuration":{"printify_shop_id":1,"printify_shop_title":"X","etsy_shop_slug":"x"}}
        service=__import__("unittest.mock").mock.Mock();service.message.return_value={"message":"ok","commands":[],"warnings":[],"suggestions":[]}
        body={"csrf_token":api._COMMERCE_CREATE_CSRF,"conversation_id":CONVERSATION,"message":"hello","active_view":"dashboard","active_profile_id":"x","form":{},"attachments":[item]}
        with patch.object(api,"list_commerce_profiles",return_value=[profile]),patch.object(api,"WorkspaceChatService",return_value=service):
            self.assertEqual(self.client.post("/app/chat",json=body,headers=ORIGIN).status_code,200)
            for bad in ([{"attachment_id":"unknown-attachment-identifier"}], [{**item,"filename":"tampered.txt"}],):
                body["attachments"]=bad;self.assertEqual(self.client.post("/app/chat",json=body,headers=ORIGIN).status_code,422)
            body["conversation_id"]="different-conversation-1234567890";body["attachments"]=[item]
            self.assertEqual(self.client.post("/app/chat",json=body,headers=ORIGIN).status_code,422)

    def test_user_removal_and_expiry_preserve_referenced_attachments(self):
        pending=self.upload("pending.txt").json();referenced=self.upload("referenced.txt").json()
        refs=Path(self.temporary.name)/"refs";refs.mkdir();(refs/"conversation.json").write_text(json.dumps({"attachment_ids":[referenced["attachment_id"]]}))
        self.assertTrue(attachments.delete_pending_attachment(CONVERSATION,pending["attachment_id"],roots=(refs,)))
        self.assertFalse((self.root/CONVERSATION/pending["attachment_id"]).exists())
        self.assertFalse(attachments.delete_pending_attachment(CONVERSATION,referenced["attachment_id"],roots=(refs,)))
        orphan=self.upload("orphan.txt").json()
        result=attachments.cleanup_expired_orphans(now=time.time()+10,ttl_seconds=0,roots=(refs,))
        self.assertEqual(result,{"removed":1,"preserved":1});self.assertTrue((self.root/CONVERSATION/referenced["attachment_id"]).exists());self.assertFalse((self.root/CONVERSATION/orphan["attachment_id"]).exists())

    def test_delete_endpoint_removes_only_owned_unreferenced_pending_upload(self):
        item=self.upload("remove-me.txt").json()
        response=self.client.request("DELETE",f"/app/attachments/{item['attachment_id']}",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"conversation_id":CONVERSATION},headers=ORIGIN)
        self.assertEqual(response.status_code,200);self.assertEqual(response.json(),{"removed":True});self.assertFalse((self.root/CONVERSATION/item["attachment_id"]).exists())
        self.assertEqual(self.client.request("DELETE",f"/app/attachments/{item['attachment_id']}",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"conversation_id":"different-conversation-1234567890"},headers=ORIGIN).status_code,422)

    def test_text_attachment_end_to_end_processing_receipt_and_model_context(self):
        token="JAMESOS-FILE-CHECK-20260718";item=self.upload("check.txt",token.encode(),"text/plain").json();prompts=[]
        def model(prompt,**kwargs):prompts.append(prompt);return json.dumps({"message":token,"commands":[],"suggestions":[],"warnings":[]})
        profile={"profile_id":"x","display_name":"X","configuration":{"printify_shop_id":1,"printify_shop_title":"X","etsy_shop_slug":"x"}}
        values={"csrf_token":api._COMMERCE_CREATE_CSRF,"conversation_id":CONVERSATION,"message":"Read the attached token","active_view":"dashboard","active_profile_id":"x","selected_job_id":"","form":{},"attachments":[item]}
        conversation_root=Path(self.temporary.name)/"conversations";provider=Mock(side_effect=AssertionError("attachments cannot contact providers"))
        with patch.object(api,"list_commerce_profiles",return_value=[profile]),patch("jamesos.services.application_shell.ask_ollama",side_effect=model),patch("jamesos.services.application_shell.ROOT",conversation_root):
            response=self.client.post("/app/chat",json=values,headers=ORIGIN)
        self.assertEqual(response.status_code,200,response.text);body=response.json();self.assertEqual(body["message"],token);self.assertEqual(body["commands"],[]);self.assertEqual(len(body["attachment_receipts"]),1)
        receipt=body["attachment_receipts"][0];self.assertEqual(receipt["filename"],"check.txt");self.assertEqual(receipt["content_type"],"text/plain");self.assertEqual(receipt["byte_count"],len(token));self.assertEqual(receipt["ingestion_state"],"processed");self.assertEqual(receipt["processing_method"],"utf8_text_extraction");self.assertEqual(receipt["extracted_character_count"],len(token))
        self.assertIn(token,prompts[0]);self.assertNotIn(str(self.root),response.text);self.assertTrue((self.root/CONVERSATION/item["attachment_id"]).is_file());provider.assert_not_called()


if __name__=="__main__":unittest.main()
