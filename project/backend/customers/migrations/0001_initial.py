from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial=True
    dependencies=[('auth','0012_alter_user_first_name_max_length')]
    operations=[
        migrations.CreateModel(name='CustomerImport',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('filename',models.CharField(max_length=255)),
            ('imported_at',models.DateTimeField(auto_now_add=True)),('row_count',models.PositiveIntegerField(default=0)),
            ('imported_by',models.ForeignKey(null=True,on_delete=django.db.models.deletion.SET_NULL,to='auth.user')),
        ]),
        migrations.CreateModel(name='Customer',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('external_customer_id',models.CharField(blank=True,db_index=True,max_length=150)),
            ('company_name',models.CharField(db_index=True,max_length=300)),('email',models.EmailField(blank=True,db_index=True,max_length=254)),('updated_at',models.DateTimeField(auto_now=True)),
            ('source_import',models.ForeignKey(null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='customers',to='customers.customerimport')),
        ], options={'ordering':['company_name','email']}),
        migrations.AddConstraint(model_name='customer',constraint=models.UniqueConstraint(fields=('company_name','email'),name='unique_customer_company_email')),
    ]
