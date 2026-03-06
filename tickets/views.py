from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from requirements.models import TicketRequirement
from .models import Ticket
from .forms import TicketForm


class TicketListView(ListView):
    model = Ticket
    template_name = "tickets/ticket_list.html"
    context_object_name = "tickets"
    ordering = ["id"]

    def get(self, request, *args, **kwargs):
        query = request.GET.get("q", "").strip()
        if query:
            from search.embeddings import search_tickets
            results = search_tickets(query)
            return self.render_to_response({
                "tickets": results,
                "search_query": query,
                "is_search": True,
            })
        return super().get(request, *args, **kwargs)


class TicketDetailView(DetailView):
    model = Ticket
    template_name = "tickets/ticket_detail.html"
    context_object_name = "ticket"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ticket = self.object
        context["llrs"] = ticket.low_level_requirements.select_related("high_level_requirement").all()
        context["hlrs"] = ticket.get_hlrs()
        return context


class TicketCreateView(CreateView):
    model = Ticket
    form_class = TicketForm
    template_name = "tickets/ticket_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Ticket"
        return context

    def get_success_url(self):
        return reverse_lazy("ticket_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        for llr in form.cleaned_data["link_llrs"]:
            TicketRequirement.objects.get_or_create(ticket=self.object, low_level_requirement=llr)
        return response


class TicketUpdateView(UpdateView):
    model = Ticket
    form_class = TicketForm
    template_name = "tickets/ticket_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = f"Edit Ticket #{self.object.pk}"
        return context

    def get_success_url(self):
        return reverse_lazy("ticket_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        selected = set(form.cleaned_data["link_llrs"].values_list("id", flat=True))
        existing = set(TicketRequirement.objects.filter(ticket=self.object).values_list("low_level_requirement_id", flat=True))
        for llr_id in selected - existing:
            TicketRequirement.objects.create(ticket=self.object, low_level_requirement_id=llr_id)
        TicketRequirement.objects.filter(ticket=self.object, low_level_requirement_id__in=existing - selected).delete()
        return response
