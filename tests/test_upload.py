#!/usr/bin/env python3

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from upload_manager import BasketballUploader

class TestBasketballUploader:

    @pytest.fixture
    def uploader(self):
        with patch.dict(os.environ, {
            'S3_BUCKET_NAME': 'test-bucket',
            'AWS_REGION': 'us-east-1',
            'AWS_ACCESS_KEY_ID': 'test-key',
            'AWS_SECRET_ACCESS_KEY': 'test-secret'
        }):
            return BasketballUploader(test_mode=True)

    @pytest.fixture
    def sample_video_file(self):
        # Create a temporary video file for testing
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            # Write some fake video data
            f.write(b'fake_mp4_data' * 1000)  # ~13KB file
            temp_path = f.name

        yield temp_path

        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    def test_uploader_initialization(self, uploader):
        """Test that uploader initializes correctly"""
        assert uploader.bucket_name == 'test-bucket'
        assert uploader.aws_region == 'us-east-1'
        assert uploader.test_mode == True
        assert '.mp4' in uploader.supported_formats
        assert '.m4a' in uploader.supported_formats

    def test_validate_video_file_success(self, uploader, sample_video_file):
        """Test video file validation with valid file"""
        result = uploader.validate_video_file(Path(sample_video_file))
        assert result == True

    def test_validate_video_file_not_exists(self, uploader):
        """Test video file validation with non-existent file"""
        result = uploader.validate_video_file(Path('/nonexistent/file.mp4'))
        assert result == False

    def test_validate_video_file_unsupported_format(self, uploader):
        """Test video file validation with unsupported format"""
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            f.write(b'test data')
            temp_path = f.name

        try:
            result = uploader.validate_video_file(Path(temp_path))
            assert result == False
        finally:
            os.unlink(temp_path)

    def test_generate_s3_key(self, uploader, sample_video_file):
        """Test S3 key generation"""
        video_path = Path(sample_video_file)
        s3_key = uploader.generate_s3_key(video_path)

        # Should contain date path and filename
        assert 'basketball_games/' in s3_key
        assert video_path.name in s3_key
        assert len(s3_key.split('/')) >= 4  # basketball_games/YYYY/MM/DD/...

    @patch('boto3.client')
    def test_create_s3_bucket_exists(self, mock_boto_client, uploader):
        """Test S3 bucket creation when bucket already exists"""
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        uploader.s3_client = mock_s3

        # Mock successful head_bucket (bucket exists)
        mock_s3.head_bucket.return_value = {}

        result = uploader.create_s3_bucket_if_not_exists()
        assert result == True
        mock_s3.head_bucket.assert_called_once_with(Bucket='test-bucket')
        mock_s3.create_bucket.assert_not_called()

    @patch('boto3.client')
    def test_upload_with_progress(self, mock_boto_client, uploader, sample_video_file):
        """Test video upload with progress tracking"""
        mock_s3 = Mock()
        mock_boto_client.return_value = mock_s3
        uploader.s3_client = mock_s3

        # Mock successful upload
        mock_s3.upload_file.return_value = None

        result = uploader.upload_with_progress(
            Path(sample_video_file),
            'test/path/video.mp4'
        )

        assert result == True
        mock_s3.upload_file.assert_called_once()
        args = mock_s3.upload_file.call_args
        assert args[0][0] == sample_video_file  # file path
        assert args[0][1] == 'test-bucket'      # bucket name
        assert args[0][2] == 'test/path/video.mp4'  # s3 key

    def test_cleanup_local_file_test_mode(self, uploader, sample_video_file):
        """Test file cleanup in test mode (should not delete)"""
        result = uploader.cleanup_local_file(Path(sample_video_file))

        assert result == True
        assert os.path.exists(sample_video_file)  # File should still exist

    def test_cleanup_local_file_production_mode(self, sample_video_file):
        """Test file cleanup in production mode (should delete)"""
        # Create uploader in production mode
        with patch.dict(os.environ, {
            'S3_BUCKET_NAME': 'test-bucket',
            'AWS_REGION': 'us-east-1',
            'AWS_ACCESS_KEY_ID': 'test-key',
            'AWS_SECRET_ACCESS_KEY': 'test-secret'
        }):
            uploader = BasketballUploader(test_mode=False)

        result = uploader.cleanup_local_file(Path(sample_video_file))

        assert result == True
        assert not os.path.exists(sample_video_file)  # File should be deleted

    def test_scan_directory_no_videos(self, uploader):
        """Test directory scanning with no video files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some non-video files
            Path(temp_dir, 'readme.txt').write_text('test')
            Path(temp_dir, 'image.jpg').write_text('test')

            result = uploader.scan_and_upload_directory(temp_dir)
            assert result == []

    def test_scan_directory_with_videos(self, uploader):
        """Test directory scanning with video files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mock video files
            video1 = Path(temp_dir, 'game1.mp4')
            video2 = Path(temp_dir, 'game2.MP4')
            video1.write_text('fake video data')
            video2.write_text('fake video data')

            # Mock the upload_video method
            with patch.object(uploader, 'upload_video', return_value=True) as mock_upload:
                result = uploader.scan_and_upload_directory(temp_dir)

                assert len(result) == 2
                assert str(video1) in result
                assert str(video2) in result
                assert mock_upload.call_count == 2

if __name__ == '__main__':
    pytest.main([__file__])