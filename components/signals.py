from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Component, Language


@receiver(post_save, sender=Language)
def create_environment_component(sender, instance, created, **kwargs):
    if not created:
        return
    root, _ = Component.objects.get_or_create(
        name="Environment", parent=None
    )
    Component.objects.get_or_create(
        name=f"Environment: {instance.name}",
        parent=root,
        defaults={"language": instance},
    )
