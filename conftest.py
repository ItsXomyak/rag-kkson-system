"""Pytest configuration."""


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests that need the embedding model (~2GB)")
