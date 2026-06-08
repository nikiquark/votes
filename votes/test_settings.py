from .settings import *  # noqa: F401,F403

# Avoid writing to logs/app.log (owned by root in the dev container) during test runs.
LOGGING['handlers']['file'] = {'class': 'logging.NullHandler'}

# LiveServerTestCase (Selenium) serves pages on a local random port under these hosts.
ALLOWED_HOSTS = list(ALLOWED_HOSTS) + ['testserver', 'localhost', '127.0.0.1']
