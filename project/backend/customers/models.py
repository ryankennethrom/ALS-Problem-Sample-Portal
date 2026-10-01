from django.db import models
from django.contrib.auth.models import User


class CustomerImport(models.Model):
    filename = models.CharField(max_length=255)
    imported_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    imported_at = models.DateTimeField(auto_now_add=True)
    row_count = models.PositiveIntegerField(default=0)


class Customer(models.Model):
    # CoyId from the ALS customer export. It is kept as text because external
    # identifiers should not be treated as arithmetic values.
    external_customer_id = models.CharField(max_length=150, blank=True, db_index=True)
    company_name = models.CharField(max_length=300, db_index=True)
    customer_type = models.CharField(max_length=100, blank=True, db_index=True)
    brand = models.CharField(max_length=200, blank=True, db_index=True)
    city = models.CharField(max_length=150, blank=True, db_index=True)
    state = models.CharField(max_length=150, blank=True, db_index=True)
    last_date_received = models.DateField(null=True, blank=True, db_index=True)
    date_created = models.DateField(null=True, blank=True)
    primary_contact = models.CharField(max_length=250, blank=True)
    email = models.EmailField(blank=True, db_index=True)
    source_import = models.ForeignKey(CustomerImport, null=True, on_delete=models.SET_NULL, related_name='customers')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['company_name', 'email']

    def __str__(self):
        return self.company_name
