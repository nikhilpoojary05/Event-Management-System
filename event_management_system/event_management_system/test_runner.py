from django.test.runner import DiscoverRunner
from django.test.utils import override_settings


class FastTestRunner(DiscoverRunner):
    """Test runner with a fast password hasher and a no-op cache.

    The default PBKDF2 hasher is deliberately slow (~0.5s per hash), which
    dominates a suite that creates many users. MD5 is insecure and must never
    be used outside tests. The dummy cache keeps state such as login-failure
    counters from leaking between tests; tests that need a cache override it.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._fast_hasher = override_settings(
            PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
            CACHES={'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}},
        )
        self._fast_hasher.enable()

    def teardown_test_environment(self, **kwargs):
        self._fast_hasher.disable()
        super().teardown_test_environment(**kwargs)
