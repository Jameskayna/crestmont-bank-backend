from django.urls import path

from . import views

urlpatterns = [
    path("documents", views.KYCDocumentListCreateView.as_view(), name="kyc-document-list-create"),
]
