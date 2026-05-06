from django.urls import path
from . import views

app_name = "plays"

urlpatterns = [
    path("list/", views.PlayListView.as_view(), name="list"),
    path("detail/<int:pk>/", views.PlayDetailView.as_view(), name="detail"),
    path("activate/<int:pk>/", views.PlayActivateView.as_view(), name="activate"),
    path("deactivate/<int:pk>/", views.PlayDeactivateView.as_view(), name="deactivate"),
]
