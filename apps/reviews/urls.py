from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('request-play/', views.ReviewRequestPlayView.as_view(), name='request_play'),

    path('<int:pk>/save-draft/', views.ReviewSaveDraftView.as_view(), name='save_draft'),
    path('<int:pk>/submit/', views.ReviewSubmitView.as_view(), name='submit'),

    path('<int:pk>/mark-public/', views.ReviewMarkPublicView.as_view(), name='mark_public'),
    path('<int:pk>/mark-hidden/', views.ReviewMarkHiddenView.as_view(), name='mark_hidden'),
    path('<int:pk>/mark-obsolete/', views.ReviewMarkObsoleteView.as_view(), name='mark_obsolete'),
    path('<int:pk>/restore/', views.ReviewRestoreView.as_view(), name='restore'),
]
