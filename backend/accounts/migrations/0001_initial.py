from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial=True
    dependencies=[('auth','0012_alter_user_first_name_max_length')]
    operations=[
        migrations.CreateModel(name='LoginCode',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('email',models.EmailField(db_index=True,max_length=254)),('code_hash',models.CharField(max_length=64)),
            ('expires_at',models.DateTimeField()),('attempts',models.PositiveSmallIntegerField(default=0)),
            ('used_at',models.DateTimeField(blank=True,null=True)),('created_at',models.DateTimeField(auto_now_add=True)),
        ]),
        migrations.CreateModel(name='AppSession',fields=[
            ('id',models.BigAutoField(auto_created=True,primary_key=True,serialize=False,verbose_name='ID')),
            ('token_hash',models.CharField(db_index=True,max_length=64,unique=True)),('expires_at',models.DateTimeField(db_index=True)),
            ('revoked_at',models.DateTimeField(blank=True,null=True)),('created_at',models.DateTimeField(auto_now_add=True)),
            ('user',models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,related_name='app_sessions',to='auth.user')),
        ]),
    ]
