from mcp_lab.task3.redact import StreamRedactor, redact_complete


def test_redacts_email_ssn_and_luhn_cards():
    text = "ping ada@northwind.io ssn 078-05-1120 card 4111 1111 1111 1111 thanks"
    out = redact_complete(text)
    assert "[REDACTED]" in out
    assert "ada@" not in out
    assert "078-05-1120" not in out
    assert "4111" not in out


def test_holds_partial_email_across_chunks():
    r = StreamRedactor()
    joined = r.push("reach me at ada.l") + r.push("ovelace@example.com tomorrow") + r.flush()
    assert "@example.com" not in joined
    assert "[REDACTED]" in joined
