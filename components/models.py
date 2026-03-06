from django.db import models


class Component(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "components"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        db_table = "languages"
        ordering = ["name"]

    def __str__(self):
        return self.name
