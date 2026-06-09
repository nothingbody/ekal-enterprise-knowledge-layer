"""Tests for SQL injection safety validation in text_to_sql_service."""
import pytest

from app.services.text_to_sql_service import _validate_sql_safety


def test_valid_select():
    _validate_sql_safety("SELECT * FROM users LIMIT 10")


def test_valid_select_with_trailing_semicolon():
    _validate_sql_safety("SELECT id, name FROM users;")


def test_valid_with_cte():
    _validate_sql_safety("WITH cte AS (SELECT 1) SELECT * FROM cte")


def test_reject_insert():
    with pytest.raises(ValueError, match="只允许"):
        _validate_sql_safety("INSERT INTO users VALUES (1, 'a')")


def test_reject_drop():
    with pytest.raises(ValueError, match="只允许"):
        _validate_sql_safety("DROP TABLE users")


def test_reject_delete():
    with pytest.raises(ValueError, match="只允许"):
        _validate_sql_safety("DELETE FROM users")


def test_reject_multi_statement():
    with pytest.raises(ValueError, match="多条"):
        _validate_sql_safety("SELECT 1; DROP TABLE users")


def test_reject_multi_statement_with_comment():
    with pytest.raises(ValueError, match="多条"):
        _validate_sql_safety("SELECT 1; -- innocent comment\nDROP TABLE users")


def test_reject_update_in_select():
    with pytest.raises(ValueError, match="多条"):
        _validate_sql_safety("SELECT * FROM users; UPDATE users SET name='x'")


def test_comment_stripping():
    _validate_sql_safety("SELECT * FROM users -- just a comment")


def test_block_comment_stripping():
    _validate_sql_safety("SELECT /* columns */ * FROM users LIMIT 5")


def test_reject_hidden_drop_in_comment():
    """DROP hidden after comment removal, but semicolon still caught."""
    with pytest.raises(ValueError):
        _validate_sql_safety("SELECT 1; /* safe */ DROP TABLE x")


# ---------------------------------------------------------------------------
# Extended edge-case tests
# ---------------------------------------------------------------------------

def test_reject_insert_into():
    with pytest.raises(ValueError):
        _validate_sql_safety("SELECT * INTO new_table FROM users")


def test_reject_create_table_as_select():
    with pytest.raises(ValueError, match="只允许"):
        _validate_sql_safety("CREATE TABLE tmp AS SELECT * FROM users")


def test_reject_cte_with_delete():
    """CTE containing a DELETE should be blocked by recursive token check."""
    with pytest.raises(ValueError):
        _validate_sql_safety(
            "WITH del AS (DELETE FROM users RETURNING *) SELECT * FROM del"
        )


def test_reject_truncate():
    with pytest.raises(ValueError):
        _validate_sql_safety("TRUNCATE TABLE users")


def test_reject_grant():
    with pytest.raises(ValueError):
        _validate_sql_safety("GRANT ALL ON users TO public")


def test_reject_exec():
    with pytest.raises(ValueError):
        _validate_sql_safety("EXEC sp_executesql N'SELECT 1'")


def test_reject_copy():
    with pytest.raises(ValueError):
        _validate_sql_safety("COPY users TO '/tmp/users.csv'")


def test_reject_load_data():
    with pytest.raises(ValueError):
        _validate_sql_safety("LOAD DATA INFILE '/tmp/data.csv' INTO TABLE users")


def test_reject_null_byte():
    with pytest.raises(ValueError, match="控制字符"):
        _validate_sql_safety("SELECT * FROM users\x00; DROP TABLE users")


def test_valid_subquery():
    _validate_sql_safety(
        "SELECT * FROM (SELECT id, name FROM users WHERE active = 1) t LIMIT 10"
    )


def test_valid_cte_select():
    _validate_sql_safety(
        "WITH recent AS (SELECT * FROM orders WHERE date > '2024-01-01') "
        "SELECT * FROM recent LIMIT 50"
    )


def test_valid_aggregate():
    _validate_sql_safety(
        "SELECT department, COUNT(*) as cnt FROM employees GROUP BY department LIMIT 20"
    )


def test_unicode_whitespace_does_not_bypass():
    """Unicode non-breaking space should not bypass keyword detection."""
    # \u00a0 is non-breaking space
    with pytest.raises(ValueError):
        _validate_sql_safety("SELECT 1;\u00a0DROP\u00a0TABLE\u00a0users")


def test_reject_select_into_outfile():
    with pytest.raises(ValueError):
        _validate_sql_safety("SELECT * FROM users INTO OUTFILE '/tmp/dump.csv'")


def test_reject_sql_too_long():
    long_sql = "SELECT " + "a, " * 2000 + "b FROM t"
    with pytest.raises(ValueError, match="过长"):
        _validate_sql_safety(long_sql)


def test_reject_alter():
    with pytest.raises(ValueError):
        _validate_sql_safety("ALTER TABLE users ADD COLUMN evil TEXT")


def test_reject_pragma():
    with pytest.raises(ValueError):
        _validate_sql_safety("PRAGMA table_info(users)")


# ---------------------------------------------------------------------------
# SQL extraction from LLM response
# ---------------------------------------------------------------------------
from app.services.text_to_sql_service import _extract_sql_from_response


def test_extract_sql_code_block():
    resp = "Here is the query:\n```sql\nSELECT * FROM users LIMIT 10\n```\nDone."
    assert _extract_sql_from_response(resp) == "SELECT * FROM users LIMIT 10"


def test_extract_sql_generic_code_block():
    resp = "```\nSELECT 1\n```"
    assert _extract_sql_from_response(resp) == "SELECT 1"


def test_extract_sql_no_code_block():
    resp = "SELECT id FROM orders WHERE status = 'active'"
    result = _extract_sql_from_response(resp)
    assert "SELECT" in result
    assert "orders" in result


def test_extract_sql_unclosed_code_block():
    resp = "```sql\nSELECT * FROM t"
    result = _extract_sql_from_response(resp)
    assert "SELECT" in result
