from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.views import generic

from viewflow import flow
from viewflow.models import Process, Task


def _get_model_subclasses(models):
    """
    TODO Support for proxy subclasses
    """
    subclasses = set()

    for model in models:
        if model._meta.proxy:
            for parent in model._meta.get_parent_list():
                if not parent._meta.proxy:
                    model = parent
                    break
        subclasses.add(model)

    return subclasses


class FlowSiteMixin(object):
    flow_site = None

    @property
    def flow_cls(self):
        return self.flow_site.flow_cls

    def render_to_response(self, context, **response_kwargs):
        response_kwargs.setdefault('current_app', self.flow_cls._meta.namespace)
        return super(FlowSiteMixin, self).render_to_response(context, **response_kwargs)


class LoginView(generic.FormView):
    view_site = None
    form_class = AuthenticationForm
    template_name = 'viewflow/login.html'

    def get_success_url(self):
        return reverse('viewflow_site:index', current_app=self.view_site.app_name)

    def form_valid(self, form):
        auth_login(self.request, form.get_user())
        return HttpResponseRedirect(self.get_success_url())


class LogoutView(generic.View):
    view_site = None

    def get_success_url(self):
        return reverse('viewflow_site:login', current_app=self.view_site.app_name)

    def get(self, request, *args, **kwargs):
        auth_logout(request)
        return HttpResponseRedirect(self.get_success_url())


class AllProcessListView(generic.ListView):
    """
    All process instances list available for current user
    """
    view_site = None
    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'process_list'

    def get_template_names(self):
        return 'viewflow/site_index.html'

    def get_queryset(self):
        return Process.objects \
            .coerce_for(self.view_site.flow_sites) \
            .order_by('-created')


class AllTaskListView(generic.ListView):
    """
    All tasks from all processes assigned to current user
    """
    view_site = None
    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'task_list'

    def get_template_names(self):
        return 'viewflow/site_tasks.html'

    def get_queryset(self):
        return Task.objects \
            .coerce_for(self.view_site.flow_sites) \
            .filter(owner=self.request.user,
                    status=Task.STATUS.ASSIGNED) \
            .order_by('-created')


class AllQueueListView(generic.ListView):
    """
    All unassigned tasks available for current user
    """
    view_site = None
    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'queue'

    def get_template_names(self):
        return 'viewflow/site_queue.html'

    def get_queryset(self):
        queryset = Task.objects \
            .coerce_for(self.view_site.flow_sites) \
            .user_queue(self.request.user) \
            .filter(status=Task.STATUS.NEW) \
            .order_by('-created')

        return queryset


class ProcessListView(FlowSiteMixin, generic.ListView):
    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'process_list'

    def get_template_names(self):
        return ('{}/flow/index.html'.format(self.flow_cls._meta.app_label),
                'viewflow/flow/index.html')

    def available_start_actions(self):
        """
        Return list of start flow actions data available for the user
        """

        actions = []
        for node in self.flow_cls._meta.nodes():
            if isinstance(node, flow.Start) and node.has_perm(self.request.user):
                node_url = reverse(
                    'viewflow:{}'.format(node.name),
                    current_app=self.flow_cls._meta.namespace)

                actions.append((node_url, node.name))

        return actions

    def get_context_data(self, **kwargs):
        context = super(ProcessListView, self).get_context_data(**kwargs)
        context['start_actions'] = self.available_start_actions()
        context['flow_cls'] = self.flow_cls
        return context

    def get_queryset(self):
        return self.flow_cls.process_cls.objects \
            .filter(flow_cls=self.flow_cls) \
            .order_by('-created')


class ProcessDetailView(FlowSiteMixin, generic.DetailView):
    """
    Details for process
    """
    context_object_name = 'process'
    pk_url_kwarg = 'process_pk'

    def get_template_names(self):
        return ('{}/flow/process.html'.format(self.flow_cls._meta.app_label),
                'viewflow/flow/process.html')

    def get_context_data(self, **kwargs):
        context = super(ProcessDetailView, self).get_context_data(**kwargs)
        context['flow_cls'] = self.flow_cls
        context['task_list'] = context['process'].task_set.all().order_by('created')
        return context

    def get_queryset(self):
        return self.flow_cls.process_cls._default_manager.all()


class TaskListView(FlowSiteMixin, generic.ListView):
    """
    List of specific Flow tasks assigned to current user
    """
    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'task_list'

    def get_template_names(self):
        return ('{}/flow/task_list.html'.format(self.flow_cls._meta.app_label),
                'viewflow/flow/task_list.html')

    def get_context_data(self, **kwargs):
        context = super(TaskListView, self).get_context_data(**kwargs)
        context['flow_cls'] = self.flow_cls
        return context

    def get_queryset(self):
        return self.flow_cls.task_cls.objects \
            .filter(process__flow_cls=self.flow_cls,
                    owner=self.request.user,
                    status=self.flow_cls.task_cls.STATUS.ASSIGNED) \
            .order_by('-created')


class QueueListView(FlowSiteMixin, generic.ListView):
    """
    List of specific Flow unassigned tasks available for current user
    """
    paginate_by = 15
    paginate_orphans = 5
    context_object_name = 'queue'

    def get_template_names(self):
        return ('{}/flow/queue.html'.format(self.flow_cls._meta.app_label),
                'viewflow/flow/queue.html')

    def get_context_data(self, **kwargs):
        context = super(QueueListView, self).get_context_data(**kwargs)
        context['flow_cls'] = self.flow_cls
        return context

    def get_queryset(self):
        queryset = self.flow_cls.task_cls.objects.user_queue(self.request.user, flow_cls=self.flow_cls) \
            .filter(status=self.flow_cls.task_cls.STATUS.NEW).order_by('-created')

        return queryset
