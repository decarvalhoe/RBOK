import os

# Ensure a deterministic but non-default secret key is available during tests
# so that the configuration validation passes.
os.environ.setdefault("REALISONS_SECRET_KEY", "test-secret-key")
