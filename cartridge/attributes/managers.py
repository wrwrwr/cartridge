from django.db import models


class PolymorphicQuerySet(models.query.QuerySet):
    def iterator(self):
        for obj in super(PolymorphicQuerySet, self).iterator():
            yield obj.content_type.get_object_for_this_type(id=obj.id)


class PolymorphicManager(models.Manager):
    def get_query_set(self):
        return PolymorphicQuerySet(self.model)
