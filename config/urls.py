from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('tickets.urls')),
    path('components/', include('components.urls')),
    path('requirements/', include('requirements.urls')),
    path('ontology/', include('codebase.urls')),
]
