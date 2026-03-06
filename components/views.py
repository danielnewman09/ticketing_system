from django.db.models import Count
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView
from .models import Component
from .forms import ComponentForm


class ComponentListView(ListView):
    model = Component
    template_name = "components/component_list.html"
    context_object_name = "components"

    def get_queryset(self):
        return super().get_queryset().annotate(ticket_count=Count("tickets"))


class ComponentDetailView(DetailView):
    model = Component
    template_name = "components/component_detail.html"
    context_object_name = "component"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tickets"] = self.object.tickets.order_by("id")
        return context


class ComponentCreateView(CreateView):
    model = Component
    form_class = ComponentForm
    template_name = "components/component_form.html"
    success_url = reverse_lazy("component_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Component"
        return context
