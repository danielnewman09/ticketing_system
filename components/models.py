from django.db import models


class Component(models.Model):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    language = models.ForeignKey(
        "Language",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="environment_components",
    )

    class Meta:
        db_table = "components"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "parent"], name="unique_component_name_per_parent"
            ),
        ]

    def __str__(self):
        return self.name


class Language(models.Model):
    name = models.CharField(max_length=100, unique=True)
    version = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = "languages"
        ordering = ["name"]

    def __str__(self):
        if self.version:
            return f"{self.name} {self.version}"
        return self.name


class BuildSystem(models.Model):
    language = models.ForeignKey(
        Language, on_delete=models.CASCADE, related_name="build_systems"
    )
    name = models.CharField(max_length=100)
    config_file = models.CharField(max_length=255)
    version = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = "build_systems"
        ordering = ["name"]

    def __str__(self):
        return self.name


class TestFramework(models.Model):
    language = models.ForeignKey(
        Language, on_delete=models.CASCADE, related_name="test_frameworks"
    )
    name = models.CharField(max_length=100)
    config_file = models.CharField(max_length=255)
    test_discovery_path = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "test_frameworks"
        ordering = ["name"]

    def __str__(self):
        return self.name


class DependencyManager(models.Model):
    language = models.ForeignKey(
        Language, on_delete=models.CASCADE, related_name="dependency_managers"
    )
    name = models.CharField(max_length=100)
    manifest_file = models.CharField(max_length=255)
    lock_file = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "dependency_managers"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Dependency(models.Model):
    manager = models.ForeignKey(
        DependencyManager, on_delete=models.CASCADE, related_name="dependencies"
    )
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=100, blank=True)
    is_dev = models.BooleanField(default=False)

    class Meta:
        db_table = "dependencies"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["manager", "name"], name="unique_dependency_per_manager"
            ),
        ]

    def __str__(self):
        if self.version:
            return f"{self.name}=={self.version}"
        return self.name
