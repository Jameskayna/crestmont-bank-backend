from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.notifications.models import Notification

from .models import LoanApplication, LoanProduct
from .serializers import LoanApplicationCreateSerializer, LoanApplicationSerializer, LoanProductSerializer


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
