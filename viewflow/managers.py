from django.db import models
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.query import QuerySet
from django.db.models.constants import LOOKUP_SEP


def _get_related_path(model, base_model):
    """
    Return path suitable for select related for sublcass
    """
    ancestry = []

    if model._meta.proxy:
        for parent in model._meta.get_parent_list():
            if not parent._meta.proxy:
                model = parent
                break

    parent = model._meta.get_ancestor_link(base_model)
    while parent is not None:
        ancestry.insert(0, parent.related.get_accessor_name())
        parent = parent.related.parent_model._meta.get_ancestor_link(base_model)

    return LOOKUP_SEP.join(ancestry)


def _get_sub_obj(obj, query):
    rel, _, query = query.partition(LOOKUP_SEP)

    try:
        node = getattr(obj, rel)
    except ObjectDoesNotExist:
        return None

    if query:
        return _get_sub_obj(node, query)
    else:
        return node


class ProcessQuerySet(QuerySet):
    def coerce_for(self, flow_classes):
        self._coerced = True

        related = [_get_related_path(flow_cls.process_cls, self.model)
                   for flow_cls in flow_classes]

        return self.filter(flow_cls__in=flow_classes).select_related(*related)

    def _clone(self, klass=None, setup=False, **kwargs):
        try:
            kwargs.update({'_coerced': self._coerced})
        except AttributeError:
            pass
        return super(ProcessQuerySet, self)._clone(klass, setup, **kwargs)

    def iterator(self):
        """
        Coerce queryset results to process subclasses depends onf flow_cls.process_cls
        """
        base_itererator = super(ProcessQuerySet, self).iterator()
        if getattr(self, '_coerced', False):
            for process in base_itererator:
                related = _get_related_path(process.flow_cls.process_cls, self.model)
                if related:
                    process = _get_sub_obj(process, related)
                if process and not isinstance(process, process.flow_cls.process_cls):
                    # Cource proxy classes
                    process.__class__ = process.flow_cls.process_cls
                yield process
        else:
            for process in base_itererator:
                yield process


class ProcessManager(models.Manager):
    def get_queryset(self):
        return ProcessQuerySet(self.model)

    def coerce_for(self, flow_classes):
        return self.get_queryset().coerce_for(flow_classes)


class TaskQuerySet(QuerySet):
    def coerce_for(self, flow_classes):
        self._coerced = True

        related = [_get_related_path(flow_cls.task_cls, self.model)
                   for flow_cls in flow_classes] + ['process']

        return self.filter(process__flow_cls__in=flow_classes).select_related(*related)

    def user_queue(self, user, flow_cls=None):
        """
        List of tasks permitted for user
        """
        queryset = self.filter(flow_task_type='HUMAN')

        if flow_cls is not None:
            queryset = queryset.filter(process__flow_cls=flow_cls)

        if not user.is_superuser:
            has_permission = Q(owner_permission__in=user.get_all_permissions()) \
                | Q(owner_permission__isnull=True) \
                | Q(owner=user)

            queryset = queryset.filter(has_permission)

        return queryset

    def _clone(self, klass=None, setup=False, **kwargs):
        try:
            kwargs.update({'_coerced': self._coerced})
        except AttributeError:
            pass
        return super(TaskQuerySet, self)._clone(klass, setup, **kwargs)

    def iterator(self):
        """
        Coerce queryset results to process subclasses depends onf flow_cls.task_cls
        """
        base_itererator = super(TaskQuerySet, self).iterator()
        if getattr(self, '_coerced', False):
            for task in base_itererator:
                related = _get_related_path(task.process.flow_cls.task_cls, self.model)
                if related:
                    task = _get_sub_obj(task, related)
                if task and not isinstance(task, task.process.flow_cls.task_cls):
                    # Cource proxy classes
                    task.__class__ = task.process.flow_cls.task_cls
                yield task
        else:
            for task in base_itererator:
                yield task


class TaskManager(models.Manager):
    def get_queryset(self):
        return TaskQuerySet(self.model)

    def coerce_for(self, flow_classes):
        return self.get_queryset().coerce_for(flow_classes)

    def user_queue(self, user, flow_cls=None):
        return self.get_queryset().user_queue(user, flow_cls)
