from django.contrib import admin
from django.urls import path, include
from sync.views import task_report

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('auth_app.urls')),
    path('reports/', task_report, name='task_report'),
]
