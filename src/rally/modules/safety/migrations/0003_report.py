"""M6 gains `report` (S12, PRD §12.5, FR-14).

The four categories are AGENTS.md §9 **G-13**'s proposal and are not yet confirmed
by the client. `invitation_id` is a plain integer, never a relation to M5's table
(AGENTS.md §3.1). Nothing here is readable by a player: M6 publishes no way to read
a report back.
"""

import rally.core.clock
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('safety', '0002_v_block_pairs'),
    ]

    operations = [
        migrations.CreateModel(
            name='Report',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reporter_account_id', models.BigIntegerField(db_index=True)),
                ('reported_account_id', models.BigIntegerField(db_index=True)),
                ('category', models.CharField(choices=[('harassment', 'Harassment'), ('fake_profile', 'Fake profile'), ('inappropriate_content', 'Inappropriate content'), ('other', 'Other')], max_length=32)),
                ('details', models.TextField(blank=True, default='')),
                ('invitation_id', models.BigIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=rally.core.clock.now, editable=False)),
            ],
            options={
                'db_table': 'report',
                'ordering': ['-created_at'],
                'constraints': [models.CheckConstraint(condition=models.Q(('reporter_account_id', models.F('reported_account_id')), _negated=True), name='report_not_self')],
            },
        ),
    ]
