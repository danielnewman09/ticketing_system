from django.shortcuts import render, get_object_or_404, redirect
from .models import (
    Ticket,
    TicketRequirement,
    LowLevelRequirement,
    HighLevelRequirement,
)
from .forms import TicketForm, LowLevelRequirementForm, HighLevelRequirementForm


def ticket_list(request):
    query = request.GET.get("q", "").strip()
    if query:
        from .embeddings import search_tickets
        results = search_tickets(query)
        return render(request, "tickets/ticket_list.html", {
            "tickets": results,
            "search_query": query,
            "is_search": True,
        })
    tickets = Ticket.objects.all().order_by("id")
    return render(request, "tickets/ticket_list.html", {"tickets": tickets})


def ticket_detail(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    llrs = ticket.low_level_requirements.select_related("high_level_requirement").all()
    hlrs = ticket.get_hlrs()
    return render(request, "tickets/ticket_detail.html", {
        "ticket": ticket,
        "llrs": llrs,
        "hlrs": hlrs,
    })


def ticket_create(request):
    if request.method == "POST":
        form = TicketForm(request.POST)
        if form.is_valid():
            ticket = form.save()
            for llr in form.cleaned_data["link_llrs"]:
                TicketRequirement.objects.get_or_create(ticket=ticket, low_level_requirement=llr)
            return redirect("ticket_detail", pk=ticket.pk)
    else:
        form = TicketForm()
    return render(request, "tickets/ticket_form.html", {"form": form, "title": "Create Ticket"})


def ticket_update(request, pk):
    ticket = get_object_or_404(Ticket, pk=pk)
    if request.method == "POST":
        form = TicketForm(request.POST, instance=ticket)
        if form.is_valid():
            form.save()
            selected = set(form.cleaned_data["link_llrs"].values_list("id", flat=True))
            existing = set(TicketRequirement.objects.filter(ticket=ticket).values_list("low_level_requirement_id", flat=True))
            for llr_id in selected - existing:
                TicketRequirement.objects.create(ticket=ticket, low_level_requirement_id=llr_id)
            TicketRequirement.objects.filter(ticket=ticket, low_level_requirement_id__in=existing - selected).delete()
            return redirect("ticket_detail", pk=pk)
    else:
        form = TicketForm(instance=ticket)
    return render(request, "tickets/ticket_form.html", {"form": form, "title": f"Edit Ticket #{ticket.pk}"})


def requirement_list(request):
    hlrs = HighLevelRequirement.objects.prefetch_related("low_level_requirements").all()
    unlinked_llrs = LowLevelRequirement.objects.filter(high_level_requirement__isnull=True)
    return render(request, "tickets/requirement_list.html", {
        "hlrs": hlrs,
        "unlinked_llrs": unlinked_llrs,
    })


def hlr_create(request):
    if request.method == "POST":
        form = HighLevelRequirementForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("requirement_list")
    else:
        form = HighLevelRequirementForm()
    return render(request, "tickets/hlr_form.html", {"form": form, "title": "Create High-Level Requirement"})


def hlr_update(request, pk):
    hlr = get_object_or_404(HighLevelRequirement, pk=pk)
    if request.method == "POST":
        form = HighLevelRequirementForm(request.POST, instance=hlr)
        if form.is_valid():
            form.save()
            return redirect("requirement_list")
    else:
        form = HighLevelRequirementForm(instance=hlr)
    return render(request, "tickets/hlr_form.html", {"form": form, "title": f"Edit HLR #{hlr.pk}"})


def llr_create(request):
    if request.method == "POST":
        form = LowLevelRequirementForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("requirement_list")
    else:
        form = LowLevelRequirementForm()
        hlr_id = request.GET.get("hlr")
        if hlr_id:
            form.initial["high_level_requirement"] = hlr_id
    return render(request, "tickets/requirement_form.html", {"form": form, "title": "Create Low-Level Requirement"})


def requirement_update(request, pk):
    llr = get_object_or_404(LowLevelRequirement, pk=pk)
    if request.method == "POST":
        form = LowLevelRequirementForm(request.POST, instance=llr)
        if form.is_valid():
            form.save()
            return redirect("requirement_list")
    else:
        form = LowLevelRequirementForm(instance=llr)
    return render(request, "tickets/requirement_form.html", {"form": form, "title": f"Edit Requirement #{llr.pk}"})
