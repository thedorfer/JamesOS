from __future__ import annotations
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location("project_cleanup",Path(__file__).parents[1]/"scripts/project_cleanup.py")
cleanup=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=cleanup;SPEC.loader.exec_module(cleanup)

class ProjectCleanupTests(unittest.TestCase):
    def repo(self):
        temporary=tempfile.TemporaryDirectory();root=Path(temporary.name)/"repo";root.mkdir();(root/".git").mkdir();return temporary,root
    def test_dry_run_default_and_byte_count(self):
        temp,root=self.repo()
        try:
            cache=root/"pkg/__pycache__";cache.mkdir(parents=True);(cache/"a.pyc").write_bytes(b"12345")
            result=cleanup.CleanupAudit(root,tracked=set()).clean();self.assertTrue(result["dry_run"]);self.assertEqual(result["planned_bytes"],5)
            self.assertTrue(cache.exists());self.assertEqual(result["removed_paths"],[])
        finally:temp.cleanup()
    def test_confirmed_cache_removal_and_empty_parent_preserved(self):
        temp,root=self.repo()
        try:
            cache=root/"pkg/__pycache__";cache.mkdir(parents=True);(cache/"a.pyc").write_bytes(b"123")
            result=cleanup.CleanupAudit(root,tracked=set()).clean(confirm=True);self.assertFalse(cache.exists());self.assertTrue((root/"pkg").is_dir())
            self.assertEqual(result["reclaimed_bytes"],3)
        finally:temp.cleanup()
    def test_tracked_file_protects_cache_directory(self):
        temp,root=self.repo()
        try:
            cache=root/"pkg/__pycache__";cache.mkdir(parents=True);(cache/"tracked.pyc").write_bytes(b"x")
            audit=cleanup.CleanupAudit(root,tracked={"pkg/__pycache__/tracked.pyc"});candidate=audit.scan()[0]
            self.assertTrue(candidate.tracked);self.assertEqual(candidate.recommended_action,"keep");audit.clean(confirm=True);self.assertTrue(cache.exists())
        finally:temp.cleanup()
    def test_git_venv_and_jamesosdata_are_never_traversed(self):
        temp,root=self.repo()
        try:
            for name in (".git",".venv","JamesOSData","Profiles","Secrets"):
                path=root/name/"__pycache__";path.mkdir(parents=True,exist_ok=True);(path/"x.pyc").write_bytes(b"private")
            self.assertEqual(cleanup.CleanupAudit(root,tracked=set()).scan(),[])
        finally:temp.cleanup()
    def test_symlink_escape_is_unsafe_and_not_removed(self):
        temp,root=self.repo()
        try:
            outside=Path(temp.name)/"outside";outside.mkdir();(outside/"data").write_text("keep");(root/"__pycache__").symlink_to(outside,target_is_directory=True)
            result=cleanup.CleanupAudit(root,tracked=set()).clean(confirm=True);self.assertEqual(result["exit_code"],2);self.assertTrue((outside/"data").exists())
        finally:temp.cleanup()
    def test_outside_repository_and_unknown_file_protection(self):
        temp,root=self.repo()
        try:
            audit=cleanup.CleanupAudit(root,tracked=set());outside=Path(temp.name)/"outside.txt";outside.write_text("keep")
            self.assertFalse(cleanup._inside(root,outside));unknown=root/"important.custom";unknown.write_text("keep")
            audit.clean(confirm=True);self.assertTrue(unknown.exists());self.assertTrue(outside.exists())
        finally:temp.cleanup()
    def test_generated_recognition_and_manual_log_action(self):
        temp,root=self.repo()
        try:
            (root/".pytest_cache").mkdir();(root/"run.log").write_text("log");items=cleanup.CleanupAudit(root,tracked=set()).scan();by={x.category:x for x in items}
            self.assertEqual(by["cache_directory"].recommended_action,"safe automatic cleanup");self.assertEqual(by["local_log"].recommended_action,"move to JamesOSData")
        finally:temp.cleanup()
    def test_empty_directory_is_manual_review_only(self):
        temp,root=self.repo()
        try:
            empty=root/"empty";empty.mkdir();item=next(x for x in cleanup.CleanupAudit(root,tracked=set()).scan() if x.path=="empty")
            self.assertEqual(item.category,"empty_directory");self.assertEqual(item.recommended_action,"manual review");cleanup.CleanupAudit(root,tracked=set()).clean(confirm=True);self.assertTrue(empty.exists())
        finally:temp.cleanup()
    def test_no_external_calls_or_jamesosdata_access(self):
        source=(Path(__file__).parents[1]/"scripts/project_cleanup.py").read_text()
        for term in ("requests","httpx","urlopen","shell=True","git clean"):self.assertNotIn(term,source)
        temp,root=self.repo()
        try:
            protected=root/"JamesOSData";protected.mkdir();marker=protected/"marker";marker.write_text("same")
            cleanup.CleanupAudit(root,tracked=set()).clean(confirm=True);self.assertEqual(marker.read_text(),"same")
        finally:temp.cleanup()

if __name__=="__main__":unittest.main()
