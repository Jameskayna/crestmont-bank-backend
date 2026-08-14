from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.auditlog.utils import log_action
from apps.notifications.models import Notification
from apps.users.permissions import IsApprover, IsConfigManager, IsStaff

from .models import LoanApplication, LoanProduct
from .serializers import (
    AdminLoanApplicationSerializer,
    LoanApplicationCreateSerializer,
    LoanApplicationSerializer,
    LoanProductSerializer,
    LoanProductWriteSerializer,
)


class LoanProductListView(APIView):
    def get(self, request):
        products = LoanProduct.objects.filter(is_active=True).order_by("name")
        return Response(LoanProductSerializer(products, many=True).data)


class LoanApplicationListCreateView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "loan"

    def get(self, request):
        applications = LoanApplication.objects.filter(applicant=request.user).order_by("-created_at")
        return Response(LoanApplicationSerializer(applications, many=True).data)

    def post(self, request):
        serializer = LoanApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not request.user.can_transact:
            return Response(
                {"error": "Verify your email and complete KYC before applying for a loan."},
                status=status.HTTP_403_FORBIDDEN,
            )

        product = get_object_or_404(LoanProduct, pk=data["product"], is_active=True)

        if not (product.min_amount_cents <= data["requested_amount_cents"] <= product.max_amount_cents):
            return Response(
                {
                    "error": (
                        f"Amount for {product.name} must be between "
                        f"{product.min_amount_cents} and {product.max_amount_cents} cents."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (product.min_term_months <= data["term_months"] <= product.max_term_months):
            return Response(
                {
                    "error": (
                        f"Term for {product.name} must be between "
                        f"{product.min_term_months} and {product.max_term_months} months."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        application = LoanApplication.objects.create(
            applicant=request.user,
            product=product,
            requested_amount_cents=data["requested_amount_cents"],
            term_months=data["term_months"],
            purpose=data.get("purpose", ""),
            monthly_income_cents=data.get("monthly_income_cents"),
        )
        Notification.objects.create(
            user=request.user,
            category=Notification.Category.LOAN,
            title="Loan application submitted",
            body=f"Your application for {product.name} is under review.",
        )

        return Response(LoanApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


class AdminLoanApplicationListView(APIView):
    permission_classes = [IsStaff]

    def get(self, request):
        applications = LoanApplication.objects.select_related("applicant", "product").order_by("-created_at")[:200]
        return Response(AdminLoanApplicationSerializer(applications, many=True).data)


class AdminLoanApproveView(APIView):
    permission_classes = [IsApprover]

    def post(self, request, pk):
        application = get_object_or_404(LoanApplication, pk=pk, status=LoanApplication.Status.SUBMITTED)
        application.status = LoanApplication.Status.APPROVED
        application.reviewed_by = request.user
        # Locked in at approval time, per the product's docstring — later
        # rate changes never rewrite an already-decided application.
        application.approved_interest_rate_bps = application.product.annual_interest_rate_bps
        application.save(update_fields=["status", "reviewed_by", "approved_interest_rate_bps"])
        Notification.objects.create(
            user=application.applicant,
            category=Notification.Category.LOAN,
            title="Loan approved",
            body=f"Your {application.product.name} application was approved.",
        )
        log_action(request, "loan.approve", "LoanApplication", application.id)
        return Response(AdminLoanApplicationSerializer(application).data)


class AdminLoanRejectView(APIView):
    permission_classes = [IsApprover]

    def post(self, request, pk):
        application = get_object_or_404(LoanApplication, pk=pk, status=LoanApplication.Status.SUBMITTED)
        reason = request.data.get("reason", "")
        if not reason:
            return Response({"error": "A reason is required."}, status=status.HTTP_400_BAD_REQUEST)

        application.status = LoanApplication.Status.REJECTED
        application.reviewed_by = request.user
        application.rejection_reason = reason
        application.save(update_fields=["status", "reviewed_by", "rejection_reason"])
        Notification.objects.create(
            user=application.applicant, category=Notification.Category.LOAN, title="Loan declined", body=reason
        )
        log_action(request, "loan.reject", "LoanApplication", application.id, reason=reason)
        return Response(AdminLoanApplicationSerializer(application).data)


class AdminLoanProductListCreateView(APIView):
    """Settings tab: fee/rate configuration. Any staff can view; only
    admin/superadmin can create — matches the product's own docstring
    describing rates as 'admin-configurable'."""

    permission_classes = [IsStaff]

    def get(self, request):
        products = LoanProduct.objects.all().order_by("name")
        return Response(LoanProductSerializer(products, many=True).data)

    def post(self, request):
        if not IsConfigManager().has_permission(request, self):
            return Response({"error": "Only admins can create loan products."}, status=status.HTTP_403_FORBIDDEN)

        serializer = LoanProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        product = LoanProduct.objects.create(**serializer.validated_data)
        log_action(request, "loan_product.create", "LoanProduct", product.id, metadata=serializer.validated_data)
        return Response(LoanProductSerializer(product).data, status=status.HTTP_201_CREATED)


class AdminLoanProductDetailView(APIView):
    permission_classes = [IsStaff]

    def patch(self, request, pk):
        if not IsConfigManager().has_permission(request, self):
            return Response({"error": "Only admins can edit loan products."}, status=status.HTTP_403_FORBIDDEN)

        product = get_object_or_404(LoanProduct, pk=pk)
        serializer = LoanProductWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        for field, value in serializer.validated_data.items():
            setattr(product, field, value)
        product.save()
        log_action(request, "loan_product.update", "LoanProduct", product.id, metadata=serializer.validated_data)
        return Response(LoanProductSerializer(product).data)
