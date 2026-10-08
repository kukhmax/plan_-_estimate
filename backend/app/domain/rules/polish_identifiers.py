"""Polish identifiers and contact data of a document party (Stage 15C): NIP, bank account (NRB), postal code, e-mail, phone.

Deterministic rules only. Every `normalize_*` returns the canonical stored form, or None for an empty input, and raises
`ValueError` with a stable code (`NIP_INVALID`, ...) for a wrong one; the service turns the codes into field errors.
"""

import re

NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)
_EMAIL = re.compile(r"^[^@\s,;<>()\[\]\\\"]+@[^@\s,;<>()\[\]\\\"]+\.[^@\s,;<>()\[\]\\\"]{2,}$")
_PHONE_CHARS = re.compile(r"^[0-9+()\-./\s]+$")


def _digits(raw: str) -> str:
    return re.sub(r"[\s\-.]", "", raw)


def nip_checksum_ok(digits: str) -> bool:
    """The control digit of a Polish NIP: weighted sum of the first nine digits mod 11 (a remainder of 10 is never valid)."""
    if len(digits) != 10 or not digits.isascii() or not digits.isdigit():
        return False
    control = sum(int(d) * w for d, w in zip(digits[:9], NIP_WEIGHTS, strict=True)) % 11
    return control != 10 and control == int(digits[9])


def normalize_nip(raw: str | None) -> str | None:
    """`123-456-78-90`, `PL 1234567890` and `1234567890` are the same NIP; stored as ten digits."""
    if raw is None or not raw.strip():
        return None
    text = raw.strip()
    if text[:2].upper() == "PL":
        text = text[2:]
    digits = _digits(text)
    if not nip_checksum_ok(digits):
        raise ValueError("NIP_INVALID")
    return digits


def format_nip(digits: str) -> str:
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:8]}-{digits[8:]}"


def nrb_checksum_ok(digits: str) -> bool:
    """Polish bank account (NRB, 26 digits): the IBAN check with the country code PL (mod 97 must be 1)."""
    if len(digits) != 26 or not digits.isascii() or not digits.isdigit():
        return False
    return int(digits[2:] + "2521" + digits[:2]) % 97 == 1  # "PL" -> 25 21


def normalize_bank_account(raw: str | None) -> str | None:
    """26 digits, with or without the `PL` prefix and spaces; stored as the 26 digits."""
    if raw is None or not raw.strip():
        return None
    text = raw.strip()
    if text[:2].upper() == "PL":
        text = text[2:]
    digits = _digits(text)
    if not nrb_checksum_ok(digits):
        raise ValueError("BANK_ACCOUNT_INVALID")
    return digits


def format_bank_account(digits: str) -> str:
    return f"{digits[:2]} " + " ".join(digits[i : i + 4] for i in range(2, 26, 4))


def normalize_postal_code(raw: str | None) -> str | None:
    """`30001` and `30-001` are the same code; stored as `30-001`."""
    if raw is None or not raw.strip():
        return None
    digits = re.sub(r"[\s\-]", "", raw.strip())
    if len(digits) != 5 or not digits.isascii() or not digits.isdigit():
        raise ValueError("POSTAL_CODE_INVALID")
    return f"{digits[:2]}-{digits[2:]}"


def normalize_email(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    text = raw.strip()
    if not _EMAIL.match(text) or ".." in text or text.count("@") != 1:
        raise ValueError("EMAIL_INVALID")
    local, domain = text.split("@")
    return f"{local}@{domain.lower()}"


def normalize_phone(raw: str | None) -> str | None:
    """Any usual way of writing a phone number (`+48 600 100 200`, `600-100-200`, `(12) 345 67 89`), at least 7 digits."""
    if raw is None or not raw.strip():
        return None
    text = " ".join(raw.split())
    if not _PHONE_CHARS.match(text) or sum(c.isdigit() for c in text) < 7:
        raise ValueError("PHONE_INVALID")
    return text
