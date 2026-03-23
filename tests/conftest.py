import pytest
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

@pytest.fixture(scope='session')
def django_db_setup():
    pass

@pytest.fixture
def encryption_key():
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()
