"""Basic ReEDS parser tests using r2x-core 0.1.1 API.

These tests verify basic parser instantiation and configuration using
a minimal test data set.
"""

from r2x_reeds.config import ReEDSConfig


def test_config_get_file_mapping_path(example_reeds_config: ReEDSConfig):
    """Test ReEDSConfig.file_mapping_path() returns valid path."""
    path = example_reeds_config.file_mapping_path

    assert path.exists()
    assert path.name == "file_mapping.json"
    assert "r2x_reeds" in str(path)
