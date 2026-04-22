from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name='WorkerProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('max_morning_shift_hours', models.DecimalField(decimal_places=2, default=7.5, max_digits=4)),
                ('max_afternoon_shift_hours', models.DecimalField(decimal_places=2, default=7.0, max_digits=4)),
                ('max_break_minutes', models.PositiveIntegerField(default=30)),
                ('works_monday', models.BooleanField(default=True)),
                ('works_tuesday', models.BooleanField(default=True)),
                ('works_wednesday', models.BooleanField(default=True)),
                ('works_thursday', models.BooleanField(default=True)),
                ('works_friday', models.BooleanField(default=True)),
                ('works_saturday', models.BooleanField(default=False)),
                ('works_sunday', models.BooleanField(default=False)),
                ('vacation_days_per_year', models.PositiveIntegerField(default=30)),
                ('vacation_days_used', models.PositiveIntegerField(default=0)),
                ('send_shift_limit_email', models.BooleanField(default=True)),
                ('send_break_limit_email', models.BooleanField(default=True)),
                ('send_monthly_report_email', models.BooleanField(default=True)),
                ('monthly_report_day', models.PositiveIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='worker_profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Perfil laboral', 'verbose_name_plural': 'Perfiles laborales'},
        ),
        migrations.CreateModel(
            name='MedicalLeave',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField(blank=True, null=True)),
                ('reason', models.TextField(blank=True)),
                ('document', models.ImageField(blank=True, null=True, upload_to='medical_leaves/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='medical_leaves', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Baja médica', 'verbose_name_plural': 'Bajas médicas', 'ordering': ['-start_date']},
        ),
        migrations.CreateModel(
            name='VacationPeriod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('notes', models.TextField(blank=True)),
                ('approved', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='vacation_periods', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': 'Período de vacaciones', 'verbose_name_plural': 'Períodos de vacaciones', 'ordering': ['-start_date']},
        ),
    ]
