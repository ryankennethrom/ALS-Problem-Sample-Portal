import uuid
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial=True
    dependencies=[('auth','0012_alter_user_first_name_max_length')]
    operations=[
        migrations.CreateModel(name='ProblemSample',fields=[
            ('id',models.UUIDField(default=uuid.uuid4,editable=False,primary_key=True,serialize=False)),
            ('source_id',models.CharField(blank=True,db_index=True,help_text='ID from legacy/exported system',max_length=100)),
            ('lab',models.CharField(blank=True,db_index=True,max_length=150)),('status',models.CharField(blank=True,db_index=True,max_length=80)),
            ('als_tracking_number',models.CharField(blank=True,db_index=True,max_length=150)),('problem_sample_count',models.PositiveIntegerField(blank=True,null=True)),
            ('brand',models.CharField(blank=True,max_length=200)),('distributor',models.CharField(blank=True,db_index=True,max_length=250)),
            ('end_user',models.CharField(blank=True,db_index=True,max_length=250)),('date_received',models.DateField(blank=True,db_index=True,null=True)),
            ('problem_type',models.CharField(blank=True,db_index=True,max_length=250)),('issue_description',models.TextField(blank=True)),
            ('client_contact_email',models.EmailField(blank=True,db_index=True,max_length=254)),('courier',models.CharField(blank=True,max_length=150)),
            ('courier_tracking_number',models.CharField(blank=True,db_index=True,max_length=200)),('notify',models.BooleanField(default=False)),
            ('email_confirmation',models.BooleanField(default=False)),('legacy_created_by',models.CharField(blank=True,max_length=200)),
            ('legacy_modified_by',models.CharField(blank=True,max_length=200)),('created_at',models.DateTimeField(auto_now_add=True)),('modified_at',models.DateTimeField(auto_now=True)),
            ('created_by',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='problem_samples_created',to='auth.user')),
            ('modified_by',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,related_name='problem_samples_modified',to='auth.user')),
        ], options={'ordering':['-date_received','-created_at']}),
        migrations.CreateModel(name='ProblemComment',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('body',models.TextField()),
            ('legacy_author',models.CharField(blank=True,max_length=200)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('author',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to='auth.user')),
            ('problem',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='comments',to='problem_samples.problemsample')),
        ], options={'ordering':['created_at']}),
        migrations.CreateModel(name='ProblemImage',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),('image',models.ImageField(blank=True,upload_to='problem-images/%Y/%m/')),
            ('original_name',models.CharField(blank=True,max_length=255)),('uploaded_at',models.DateTimeField(auto_now_add=True)),
            ('problem',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='images',to='problem_samples.problemsample')),
            ('uploaded_by',models.ForeignKey(blank=True,null=True,on_delete=django.db.models.deletion.SET_NULL,to='auth.user')),
        ]),
    ]
