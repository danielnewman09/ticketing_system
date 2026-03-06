from django.shortcuts import render, get_object_or_404, redirect
from .models import HighLevelRequirement, LowLevelRequirement
from .forms import HighLevelRequirementForm, LowLevelRequirementForm


def requirement_list(request):
    hlrs = HighLevelRequirement.objects.prefetch_related("low_level_requirements").all()
    unlinked_llrs = LowLevelRequirement.objects.filter(high_level_requirement__isnull=True)
    return render(request, "requirements/requirement_list.html", {
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
    return render(request, "requirements/hlr_form.html", {"form": form, "title": "Create High-Level Requirement"})


def hlr_update(request, pk):
    hlr = get_object_or_404(HighLevelRequirement, pk=pk)
    if request.method == "POST":
        form = HighLevelRequirementForm(request.POST, instance=hlr)
        if form.is_valid():
            form.save()
            return redirect("requirement_list")
    else:
        form = HighLevelRequirementForm(instance=hlr)
    return render(request, "requirements/hlr_form.html", {"form": form, "title": f"Edit HLR #{hlr.pk}"})


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
    return render(request, "requirements/requirement_form.html", {"form": form, "title": "Create Low-Level Requirement"})


def requirement_update(request, pk):
    llr = get_object_or_404(LowLevelRequirement, pk=pk)
    if request.method == "POST":
        form = LowLevelRequirementForm(request.POST, instance=llr)
        if form.is_valid():
            form.save()
            return redirect("requirement_list")
    else:
        form = LowLevelRequirementForm(instance=llr)
    return render(request, "requirements/requirement_form.html", {"form": form, "title": f"Edit Requirement #{llr.pk}"})
