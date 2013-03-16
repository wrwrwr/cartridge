from django.db import models


class PolymorphicQuerySet(models.query.QuerySet):
    def iterator(self):
        for obj in super(PolymorphicQuerySet, self).iterator():
            yield obj.as_content_type()


class PolymorphicManager(models.Manager):
    def get_query_set(self):
        return PolymorphicQuerySet(self.model)
