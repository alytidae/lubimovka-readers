from django.urls import path
from . import views

app_name = "plays"

urlpatterns = [
    path("list/", views.PlayListView.as_view(), name="list"),
    path("detail/<int:pk>/", views.PlayDetailView.as_view(), name="detail"),
    path("activate/<int:pk>/", views.PlayActivateView.as_view(), name="activate"),
    path("deactivate/<int:pk>/", views.PlayDeactivateView.as_view(), name="deactivate"),
    path(
        "edit-comment/<int:pk>/",
        views.PlayUpdateCommentView.as_view(),
        name="edit-comment",
    ),
    path(
        "force-phase-2/<int:pk>/",
        views.PlayForcePhase2View.as_view(),
        name="force-phase-2",
    ),
    path(
        "unforce-phase-2/<int:pk>/",
        views.PlayUnforcePhase2View.as_view(),
        name="unforce-phase-2",
    ),
]
