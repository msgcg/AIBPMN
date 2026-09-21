import datetime
from django.db import migrations
from django.contrib.auth.hashers import make_password

def create_or_promote_root_user(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        user = User.objects.get(username='max')
        user.is_staff = True
        user.is_superuser = True
        user.password = make_password('Admin2026!Bpmn')
        user.last_login = user.last_login or now
        user.save()
    except User.DoesNotExist:
        User.objects.create(
            username='max',
            email='admin@aibpmn.local',
            password=make_password('Admin2026!Bpmn'),
            is_staff=True,
            is_superuser=True,
            is_active=True,
            date_joined=now,
            last_login=now
        )

def revert_root_user(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('architect', '0002_project_user_knowledgebasefile'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(create_or_promote_root_user, revert_root_user),
    ]

