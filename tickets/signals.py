from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Ticket


@receiver(post_save, sender=Ticket)
def update_ticket_embedding(sender, instance, **kwargs):
    from .embeddings import upsert_ticket_embedding
    upsert_ticket_embedding(instance.id, instance.title, instance.summary)
