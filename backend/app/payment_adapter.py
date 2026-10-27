from urllib.parse import urlencode
import re


VPA_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,253}@[A-Za-z0-9][A-Za-z0-9.-]{1,63}$")


def create_upi_intent(*, payee_upi: str, payee_name: str, amount_paise: int, reference: str) -> str:
    """Build a user-confirmed UPI intent. This does not move or verify funds."""
    if not VPA_PATTERN.fullmatch(payee_upi.strip()):
        raise ValueError("Enter a valid UPI ID")
    if amount_paise <= 0:
        raise ValueError("Payment amount must be positive")
    fields = {
        "pa": payee_upi.strip(),
        "pn": payee_name.strip()[:80],
        "am": f"{amount_paise // 100}.{amount_paise % 100:02d}",
        "cu": "INR",
        "tn": f"ONPay exchange {reference}"[:80],
        "tr": reference,
    }
    return "upi://pay?" + urlencode(fields)


class YouPIMerchantAdapter:
    """Boundary for merchant checkout; deliberately cannot pay an arbitrary student VPA."""

    def create_exchange_payment(self, **_kwargs):
        raise NotImplementedError(
            "YouPI-PG is documented as a merchant collection checkout and cannot be used "
            "to route an arbitrary student-to-student payment."
        )
