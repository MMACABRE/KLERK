from .base import *  # noqa: F403

# Test-only value. It is not a secret and is never used outside the test run.
SECRET_KEY = "test-only-not-a-secret"  # nosec B105
DEBUG = False
