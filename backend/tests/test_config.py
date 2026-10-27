from app.core.config import Settings


def test_sqlalchemy_url_tcp() -> None:
    s = Settings(db_host="localhost", db_port=5433, db_user="u", db_password="p", db_name="d")
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@localhost:5433/d"


def test_sqlalchemy_url_cloud_sql_socket() -> None:
    s = Settings(
        db_host="/cloudsql/proj:europe-central2:inst", db_user="u", db_password="p", db_name="d"
    )
    assert s.sqlalchemy_url == (
        "postgresql+psycopg://u:p@/d?host=%2Fcloudsql%2Fproj%3Aeurope-central2%3Ainst"
    )


def test_database_url_overrides_parts() -> None:
    s = Settings(database_url="postgresql+psycopg://x:y@h/z", db_host="ignored")
    assert s.sqlalchemy_url == "postgresql+psycopg://x:y@h/z"
