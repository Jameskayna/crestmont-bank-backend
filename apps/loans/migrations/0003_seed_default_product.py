import uuid

from django.db import migrations


def seed_default_product(apps, schema_editor):
    LoanProduct = apps.get_model("loans", "LoanProduct")
    if not LoanProduct.objects.exists():
        LoanProduct.objects.create(
            id=uuid.uuid4(),
            name="Personal Loan",
            annual_interest_rate_bps=1250,  # 12.50%
            min_amount_cents=100_000,  # $1,000
            max_amount_cents=5_000_000,  # $50,000
            min_term_months=6,
            max_term_months=60,
            is_active=True,
        )


def unseed_default_product(apps, schema_editor):
    LoanProduct = apps.get_model("loans", "LoanProduct")
    LoanProduct.objects.filter(name="Personal Loan").delete()


class Migration(migrations.Migration):
    dependencies = [("loans", "0002_initial")]
    operations = [migrations.RunPython(seed_default_product, unseed_default_product)]
