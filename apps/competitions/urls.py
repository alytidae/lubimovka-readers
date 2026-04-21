from django.urls import path
from . import views

app_name = 'competitions'

urlpatterns = [
    path('', views.CompetitionListView.as_view(), name='list'),
    path('create/', views.CompetitionCreateView.as_view(), name='create'),
    path('<slug:slug>/update/', views.CompetitionUpdateView.as_view(), name='update'),
    path('<slug:slug>/', views.CompetitionDetailView.as_view(), name='detail'),
]
