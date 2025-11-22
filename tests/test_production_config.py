import unittest
import os
import json
from pathlib import Path
from app.config import load_config, get_project_root, CONFIG_FILE
from app.models import Config

class TestProductionConfig(unittest.TestCase):
    def setUp(self):
        # Backup existing config if present
        self.config_path = get_project_root() / CONFIG_FILE
        self.backup_config = None
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                self.backup_config = json.load(f)
                
    def tearDown(self):
        # Restore config
        if self.backup_config:
            with open(self.config_path, 'w') as f:
                json.dump(self.backup_config, f, indent=2)
        elif self.config_path.exists():
            os.remove(self.config_path)

    def test_directory_creation(self):
        """Test that critical directories are created on config load"""
        # Remove directories to test creation
        root = get_project_root()
        for d in ["logs", "temp", "input", "offsets"]:
            path = root / d
            if path.exists():
                # Only remove if empty to be safe, otherwise skip
                try:
                    os.rmdir(path)
                except OSError:
                    pass
                    
        load_config()
        
        for d in ["logs", "temp", "input", "offsets"]:
            self.assertTrue((root / d).exists(), f"Directory {d} was not created")

    def test_env_override(self):
        """Test that environment variables override config file"""
        os.environ['AWS_S3_BUCKET'] = 'test-bucket-env'
        config = load_config()
        self.assertEqual(config.s3_bucket, 'test-bucket-env')
        del os.environ['AWS_S3_BUCKET']

    def test_absolute_paths(self):
        """Test that project root is absolute"""
        root = get_project_root()
        self.assertTrue(root.is_absolute())
        self.assertTrue((root / "app").exists())

if __name__ == '__main__':
    unittest.main()
