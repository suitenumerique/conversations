"""API ViewSets for activation codes."""

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.brevo import add_user_to_brevo_list
from core.permissions import IsAuthenticated

from . import models, serializers
from .exceptions import InvalidCodeError, UserAlreadyActivatedError

logger = logging.getLogger(__name__)


class ActivationViewSet(viewsets.GenericViewSet):
    """
    ViewSet for handling user activation with codes.

    Endpoints:
    - GET /activation/status/ - Check if current user is activated
    - POST /activation/validate/ - Validate and use an activation code
    - POST /activation/register/ - Register an email to be notified later
    """

    permission_classes = [IsAuthenticated]
    serializer_class = serializers.ActivationCodeValidationSerializer

    @action(detail=False, methods=["get"], url_path="status")
    def status(self, request):
        """
        Get the activation status of the current user.

        Returns:
            - is_activated: Whether the user has activated their account
            - activation: Details of the activation (if exists)
            - requires_activation: Whether activation is required by the system
        """
        requires_activation = getattr(settings, "ACTIVATION_REQUIRED", False)

        try:
            activation = models.UserActivation.objects.select_related("activation_code").get(
                user=request.user
            )
            is_activated = True
        except models.UserActivation.DoesNotExist:
            activation = None
            is_activated = False

        response_data = {
            "is_activated": is_activated,
            "activation": activation,
            "requires_activation": requires_activation,
        }

        return Response(
            serializers.ActivationStatusSerializer(response_data).data, status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"], url_path="validate")
    def validate_code(self, request):
        """
        Validate an activation code and activate the user's account.

        Request body:
            - code: The activation code to validate

        Returns:
            - Success: Activation details
            - Error: Validation error message
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code_value = serializer.validated_data["code"]

        # Get the activation code
        try:
            activation_code = models.ActivationCode.objects.get(code=code_value)
        except models.ActivationCode.DoesNotExist:
            logger.info("Activation code %s does not exist", code_value)
            return Response({"code": "invalid-code"}, status=status.HTTP_400_BAD_REQUEST)

        # Use the code
        try:
            activation = activation_code.use(request.user)
        except InvalidCodeError as exc:
            logger.warning(exc)
            return Response({"code": "invalid-code"}, status=status.HTTP_400_BAD_REQUEST)
        except UserAlreadyActivatedError as exc:
            logger.info(exc)
            return Response(
                {"code": "account-already-activated"}, status=status.HTTP_400_BAD_REQUEST
            )

        logger.info("User %s activated account with code %s", request.user.id, activation_code.code)

        return Response(
            {
                "code": "activation-successful",
                "detail": _("Your account has been successfully activated"),
                "activation": serializers.UserActivationSerializer(activation).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["post"], url_path="register")
    def register_email(self, request):
        """
        Register an email to be notified when activation codes are available.

        Request body:
            - email: The email address to register

        Returns:
            - Success: Confirmation message
            - Error: Validation error message
        """
        serializer = serializers.UserRegistrationRequestSerializer(
            data={},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        # Create the registration
        try:
            serializer.save()
        except ValidationError:
            # user is already registered, it's OK
            return Response(
                {"code": "registration-successful"},
                status=status.HTTP_200_OK,
            )

        add_user_to_brevo_list(
            [serializer.validated_data["user"].email], settings.BREVO_WAITING_LIST_ID
        )

        logger.info(
            "Registered email %s for activation notifications",
            serializer.validated_data["user"].email,
        )

        return Response(
            {"code": "registration-successful"},
            status=status.HTTP_201_CREATED,
        )
