from django.urls import path
from . import views

urlpatterns = [
    path("", views.ai_assist, name="ai_assist"),
    path("apply/", views.ai_assist_apply, name="ai_assist_apply"),
]
