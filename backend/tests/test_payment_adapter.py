import unittest
from urllib.parse import parse_qs, urlparse

from app.payment_adapter import YouPIMerchantAdapter, create_upi_intent


class PaymentAdapterTests(unittest.TestCase):
    def test_intent_binds_payee_amount_currency_and_reference(self):
        intent = create_upi_intent(
            payee_upi="student.name@okaxis", payee_name="A Student", amount_paise=50000, reference="ON123ABC"
        )
        parsed = urlparse(intent)
        fields = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "upi")
        self.assertEqual(fields["pa"], ["student.name@okaxis"])
        self.assertEqual(fields["pn"], ["A Student"])
        self.assertEqual(fields["am"], ["500.00"])
        self.assertEqual(fields["cu"], ["INR"])
        self.assertEqual(fields["tr"], ["ON123ABC"])

    def test_invalid_vpa_is_rejected(self):
        with self.assertRaises(ValueError):
            create_upi_intent(payee_upi="not-a-vpa", payee_name="Student", amount_paise=50000, reference="ON123")

    def test_youpi_merchant_adapter_refuses_student_transfer(self):
        with self.assertRaises(NotImplementedError):
            YouPIMerchantAdapter().create_exchange_payment(payee_upi="student@bank", amount_paise=50000)


if __name__ == "__main__":
    unittest.main()
