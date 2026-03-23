# sync/management/commands/setup_default_tags.py
from django.core.management.base import BaseCommand
from sync.models import Tag

class Command(BaseCommand):
    help = 'Create default tags for calendar sync'

    DEFAULT_TAGS = [
        {'name': 'PM', 'color_hex': '#4CAF50', 'google_color_id': 10},
        {'name': 'Repair', 'color_hex': '#F44336', 'google_color_id': 11},
        {'name': 'Installation', 'color_hex': '#2196F3', 'google_color_id': 9},
        {'name': 'Inspection', 'color_hex': '#FFEB3B', 'google_color_id': 5},
    ]

    def handle(self, *args, **options):
        for tag_data in self.DEFAULT_TAGS:
            tag, created = Tag.objects.get_or_create(
                name=tag_data['name'],
                defaults={
                    'color_hex': tag_data['color_hex'],
                    'google_color_id': tag_data['google_color_id']
                }
            )
            status = 'Created' if created else 'Already exists'
            self.stdout.write(f"{status}: {tag.name}")

        self.stdout.write(self.style.SUCCESS('Default tags setup complete'))
