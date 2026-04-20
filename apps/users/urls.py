from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    path('create/', views.UserCreateView.as_view(), name='create'),
    path('update/<int:pk>/', views.UserUpdateView.as_view(), name='update'),
]

