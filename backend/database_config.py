"""One database for all Tempo records and both MongoDB adapters."""
import os

DATABASE_NAME = 'sports_coach_db'
DATABASE_ENV_NAMES = ('MONGODB_DB_NAME', 'MONGODB_DATABASE', 'MONGODB_WATCH_DATABASE')

def validate_database_name(value=None):
    if value and value.strip() != DATABASE_NAME:
        raise ValueError('Tempo must use sports_coach_db; separate database targets are not supported')
    return DATABASE_NAME

def validate_database_environment():
    for name in DATABASE_ENV_NAMES:
        validate_database_name(os.environ.get(name))
