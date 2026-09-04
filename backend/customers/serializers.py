from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            'id', 'external_customer_id', 'company_name', 'customer_type', 'brand',
            'city', 'state', 'last_date_received', 'date_created', 'primary_contact',
            'email', 'updated_at',
        ]
