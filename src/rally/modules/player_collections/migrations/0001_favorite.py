"""M8 gains `favorite` (S13, FR-16, ADR-006).

Three columns: the owner, the favorited account, and when it was added. Nothing
about the other player is stored - rule 11, references never copies. Both ids are
plain integers rather than relations, so a favorite outlives the account it points
at and the list can say "No longer available" instead of losing a row (G-06).
"""

import rally.core.clock
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Favorite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('owner_account_id', models.BigIntegerField(db_index=True)),
                ('favorited_account_id', models.BigIntegerField(db_index=True)),
                ('created_at', models.DateTimeField(default=rally.core.clock.now, editable=False)),
            ],
            options={
                'db_table': 'favorite',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['owner_account_id', 'created_at'], name='favorite_owner_idx')],
                'constraints': [models.UniqueConstraint(fields=('owner_account_id', 'favorited_account_id'), name='favorite_once_per_pair'), models.CheckConstraint(condition=models.Q(('owner_account_id', models.F('favorited_account_id')), _negated=True), name='favorite_not_self')],
            },
        ),
    ]
