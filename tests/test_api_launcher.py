from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


class ApiLauncherTests(unittest.TestCase):
    def test_direct_launcher_prefers_package_when_pythonpath_already_has_root(self):
        root=Path(__file__).parents[1];environment={**os.environ,"PYTHONPATH":str(root),"JAMESOS_API_IMPORT_CHECK":"1"}
        completed=subprocess.run([sys.executable,str(root/"scripts/api_server.py")],cwd=root,env=environment,capture_output=True,text=True,timeout=30,check=True)
        self.assertEqual(Path(completed.stdout.strip()),root/"jamesos/__init__.py")
        self.assertTrue((root/"scripts/jamesos.py").is_file())


if __name__=="__main__":unittest.main()
