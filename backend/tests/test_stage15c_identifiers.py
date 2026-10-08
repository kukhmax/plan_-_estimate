"""Stage 15C — Polish identifiers of the executor profile: NIP, bank account (NRB), postal code, e-mail, phone."""

import pytest

from app.domain.rules import polish_identifiers as ids

# Real, published identifiers: PKN Orlen NIP and the NBP sample account (valid checksums).
VALID_NIP = "7740001454"
VALID_NRB = "61109010140000071219812874"


def make_nip(first_nine: str) -> str:
    control = sum(int(d) * w for d, w in zip(first_nine, ids.NIP_WEIGHTS, strict=True)) % 11
    assert control != 10, "pick other digits"
    return first_nine + str(control)


@pytest.mark.parametrize(
    "raw",
    ["7740001454", "774-000-14-54", "774 000 14 54", "PL7740001454", "pl 774-000-14-54", "  7740001454  ", "774.000.14.54"],
)
def test_one_nip_in_every_usual_writing(raw):
    assert ids.normalize_nip(raw) == VALID_NIP


@pytest.mark.parametrize(
    "raw",
    ["1234567890", "7740001455", "774000145", "77400014545", "abcdefghij", "774-000-14-5X", "0000000000x", "77400 01454 0"],
)
def test_a_wrong_nip_is_refused_with_its_code(raw):
    with pytest.raises(ValueError, match="NIP_INVALID"):
        ids.normalize_nip(raw)


def test_a_generated_nip_has_the_right_control_digit_and_one_off_digit_is_caught():
    nip = make_nip("526025099")
    assert ids.normalize_nip(nip) == nip
    flipped = nip[:-1] + str((int(nip[-1]) + 1) % 10)
    with pytest.raises(ValueError, match="NIP_INVALID"):
        ids.normalize_nip(flipped)
    swapped = nip[1] + nip[0] + nip[2:]
    if swapped != nip:
        with pytest.raises(ValueError):
            ids.normalize_nip(swapped)


def test_a_remainder_of_ten_is_never_a_valid_nip():
    # find nine digits whose weighted sum is 10 mod 11: no control digit exists for them
    candidate = next(n for n in (f"{i:09d}" for i in range(10**6)) if sum(int(d) * w for d, w in zip(n, ids.NIP_WEIGHTS, strict=True)) % 11 == 10)
    for control in "0123456789":
        assert not ids.nip_checksum_ok(candidate + control)


@pytest.mark.parametrize("empty", [None, "", "   ", "\t\n"])
def test_nothing_given_is_none_for_every_optional_field(empty):
    for normalize in (ids.normalize_nip, ids.normalize_bank_account, ids.normalize_postal_code, ids.normalize_email, ids.normalize_phone):
        assert normalize(empty) is None


def test_nip_is_shown_in_the_usual_grouping():
    assert ids.format_nip(VALID_NIP) == "774-000-14-54"


@pytest.mark.parametrize(
    "raw",
    ["61109010140000071219812874", "61 1090 1014 0000 0712 1981 2874", "PL61109010140000071219812874", "pl 61 1090 1014 0000 0712 1981 2874"],
)
def test_one_account_in_every_usual_writing(raw):
    assert ids.normalize_bank_account(raw) == VALID_NRB


@pytest.mark.parametrize(
    "raw",
    ["61109010140000071219812875", "6110901014000007121981287", "611090101400000712198128744", "abcdefghijklmnopqrstuvwxyz", "DE61109010140000071219812874", "00000000000000000000000000"],
)
def test_a_wrong_account_is_refused(raw):
    with pytest.raises(ValueError, match="BANK_ACCOUNT_INVALID"):
        ids.normalize_bank_account(raw)


def test_account_grouping():
    assert ids.format_bank_account(VALID_NRB) == "61 1090 1014 0000 0712 1981 2874"


@pytest.mark.parametrize(("raw", "expected"), [("30001", "30-001"), ("30-001", "30-001"), (" 30 001 ", "30-001"), ("00-000", "00-000")])
def test_postal_codes(raw, expected):
    assert ids.normalize_postal_code(raw) == expected


@pytest.mark.parametrize("raw", ["3000", "300011", "30-0011", "ab-cde", "30/001", "３００-０１"])
def test_a_wrong_postal_code_is_refused(raw):
    with pytest.raises(ValueError, match="POSTAL_CODE_INVALID"):
        ids.normalize_postal_code(raw)


@pytest.mark.parametrize(("raw", "expected"), [("jan@example.pl", "jan@example.pl"), ("Jan.Kowalski@Example.PL", "Jan.Kowalski@example.pl"), (" a+b@x-y.co.uk ", "a+b@x-y.co.uk")])
def test_emails(raw, expected):
    assert ids.normalize_email(raw) == expected


@pytest.mark.parametrize("raw", ["jan", "jan@", "@example.pl", "jan@example", "jan@@example.pl", "ja n@example.pl", "jan@exa..mple.pl", "a@b.c", "<jan>@example.pl", "jan@example.pl,x@y.pl", "jan@example.pl;x"])
def test_a_wrong_email_is_refused(raw):
    with pytest.raises(ValueError, match="EMAIL_INVALID"):
        ids.normalize_email(raw)


@pytest.mark.parametrize("raw", ["+48 600 100 200", "600-100-200", "(12) 345 67 89", "600100200", "+48600100200", "12.345.67.89"])
def test_phones_in_the_usual_writings(raw):
    assert ids.normalize_phone(raw) == " ".join(raw.split())


@pytest.mark.parametrize("raw", ["600", "abc", "+48 600 abc 200", "123456", "tel. 600100200", "600100200; drop table"])
def test_a_wrong_phone_is_refused(raw):
    with pytest.raises(ValueError, match="PHONE_INVALID"):
        ids.normalize_phone(raw)
