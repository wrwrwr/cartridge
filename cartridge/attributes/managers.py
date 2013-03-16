from django.db import models


class AttributeValueQuerySet(models.query.QuerySet):
    def iterator(self):
        for obj in super(AttributeValueQuerySet, self).iterator():
            yield obj.as_value_type()


class AttributeValueManager(models.Manager):
    def get_query_set(self):
        return AttributeValueQuerySet(self.model)
