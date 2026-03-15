from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic import ListView, DetailView, CreateView
from .models import Component, Language, DependencyManager
from .forms import (
    ComponentForm,
    LanguageForm,
    BuildSystemFormSet,
    TestFrameworkFormSet,
    DependencyManagerFormSet,
    DependencyFormSet,
)


class ComponentListView(ListView):
    model = Component
    template_name = "components/component_list.html"
    context_object_name = "components"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(parent=None)
            .annotate(
                ticket_count=Count("tickets"),
                child_count=Count("children"),
            )
        )


class ComponentDetailView(DetailView):
    model = Component
    template_name = "components/component_detail.html"
    context_object_name = "component"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tickets"] = self.object.tickets.order_by("id")
        context["requirements"] = self.object.low_level_requirements.select_related(
            "high_level_requirement"
        ).order_by("id")
        context["children"] = self.object.children.annotate(
            ticket_count=Count("tickets")
        )
        if self.object.language:
            lang = self.object.language
            context["build_systems"] = lang.build_systems.all()
            context["test_frameworks"] = lang.test_frameworks.all()
            context["dependency_managers"] = lang.dependency_managers.prefetch_related(
                "dependencies"
            )
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


class LanguageListView(ListView):
    model = Language
    template_name = "components/language_list.html"
    context_object_name = "languages"


class LanguageDetailView(DetailView):
    model = Language
    template_name = "components/language_detail.html"
    context_object_name = "language"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["build_systems"] = self.object.build_systems.all()
        context["test_frameworks"] = self.object.test_frameworks.all()
        context["dependency_managers"] = (
            self.object.dependency_managers.prefetch_related("dependencies")
        )
        return context


class LanguageEditView(View):
    template_name = "components/language_edit.html"

    def _build_context(self, language, form, bs_fs, tf_fs, dm_fs):
        return {
            "language": language,
            "form": form,
            "build_system_formset": bs_fs,
            "test_framework_formset": tf_fs,
            "dep_manager_formset": dm_fs,
        }

    def get(self, request, pk):
        language = get_object_or_404(Language, pk=pk)
        from django.shortcuts import render

        return render(
            request,
            self.template_name,
            self._build_context(
                language,
                LanguageForm(instance=language),
                BuildSystemFormSet(instance=language, prefix="bs"),
                TestFrameworkFormSet(instance=language, prefix="tf"),
                DependencyManagerFormSet(instance=language, prefix="dm"),
            ),
        )

    def post(self, request, pk):
        language = get_object_or_404(Language, pk=pk)
        form = LanguageForm(request.POST, instance=language)
        bs_fs = BuildSystemFormSet(request.POST, instance=language, prefix="bs")
        tf_fs = TestFrameworkFormSet(request.POST, instance=language, prefix="tf")
        dm_fs = DependencyManagerFormSet(request.POST, instance=language, prefix="dm")

        if form.is_valid() and bs_fs.is_valid() and tf_fs.is_valid() and dm_fs.is_valid():
            form.save()
            bs_fs.save()
            tf_fs.save()
            dm_fs.save()
            return redirect("language_detail", pk=language.pk)

        from django.shortcuts import render

        return render(
            request,
            self.template_name,
            self._build_context(language, form, bs_fs, tf_fs, dm_fs),
        )


class DependencyEditView(View):
    template_name = "components/dependency_edit.html"

    def get(self, request, dm_pk):
        dm = get_object_or_404(DependencyManager, pk=dm_pk)
        formset = DependencyFormSet(instance=dm)
        from django.shortcuts import render

        return render(request, self.template_name, {"dm": dm, "formset": formset})

    def post(self, request, dm_pk):
        dm = get_object_or_404(DependencyManager, pk=dm_pk)
        formset = DependencyFormSet(request.POST, instance=dm)
        if formset.is_valid():
            formset.save()
            return redirect("language_detail", pk=dm.language_id)

        from django.shortcuts import render

        return render(request, self.template_name, {"dm": dm, "formset": formset})
