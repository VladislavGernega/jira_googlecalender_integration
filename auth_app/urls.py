from django.urls import path
from . import views

app_name = 'auth_app'

urlpatterns = [
    path('google/', views.google_oauth_start, name='google_start'),
    path('google/callback/', views.google_oauth_callback, name='google_callback'),
    path('google/link/', views.google_oauth_link, name='google_link'),
]
