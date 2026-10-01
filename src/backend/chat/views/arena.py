"""Arena endpoints: draw a blind comparison for the next turn, then vote on it.

Both actions live on the conversation viewset. The streaming endpoint itself
learns about arena mode through two query parameters (``arena_comparison`` and
``arena_side``) handled in ``ChatViewSet.post_conversation``. No response of
these endpoints ever carries a model name: which model sits on which side is a
server-side fact.
"""

import logging

from drf_spectacular.utils import extend_schema
from rest_framework import decorators, status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from chat import arena as arena_service
from chat import models, serializers
from chat.ai_sdk_types import UIMessage
from chat.clients.pydantic_ai import AIAgentService

logger = logging.getLogger(__name__)


class ArenaMixin:
    """Arena actions for ``ChatViewSet``."""

    def _get_pending_comparison_or_404(self, conversation, comparison_id):
        """The pending comparison of this conversation and user, or 404."""
        comparison = models.ArenaComparison.objects.filter(
            pk=comparison_id,
            conversation=conversation,
            user=self.request.user,
        ).first()
        if comparison is None:
            raise NotFound("Unknown arena comparison for this conversation.")
        return comparison

    @decorators.action(
        methods=["post"],
        detail=True,
        url_path="arena/draw",
        url_name="arena-draw",
    )
    def post_arena_draw(self, request, pk):  # pylint: disable=unused-argument
        """Decide whether the next turn of this conversation is an arena turn.

        Returns ``{"arena": false}`` for a normal turn, otherwise the id of the
        pending comparison the client must pass to two streaming requests, one
        per side.
        """
        conversation = self.get_object()
        serializer = serializers.ArenaDrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        comparison = arena_service.draw_comparison(
            conversation=conversation,
            user=request.user,
            force_web_search=serializer.validated_data["force_web_search"],
            force_datagouv=serializer.validated_data["force_datagouv"],
            last_message=serializer.validated_data.get("message"),
            model_hrid=serializer.validated_data["model_hrid"],
        )
        if comparison is None:
            return Response({"arena": False}, status=status.HTTP_200_OK)
        return Response({"arena": True, "comparison_id": str(comparison.pk)})

    @extend_schema(
        request=serializers.ArenaVoteSerializer,
        responses={200: serializers.ArenaVoteResponseSerializer},
    )
    @decorators.action(
        methods=["post"],
        detail=True,
        url_path=r"arena/(?P<comparison_id>[0-9a-f-]{36})/vote",
        url_name="arena-vote",
    )
    def post_arena_vote(self, request, pk, comparison_id):  # pylint: disable=unused-argument
        """Record the user's pick (or abandonment) and commit the chosen answer.

        Returns the updated conversation so the client can replace the split view
        with the committed history in one round trip, plus an ``acknowledgement``
        block (vote counts, milestone) on a vote and ``null`` on an abandonment.
        """
        conversation = self.get_object()
        serializer = serializers.ArenaVoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comparison = self._get_pending_comparison_or_404(conversation, comparison_id)

        try:
            comparison = arena_service.vote(comparison, serializer.validated_data["side"])
        except arena_service.ArenaConflict as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)

        conversation.refresh_from_db()
        return Response(
            {
                **self.get_serializer(conversation).data,
                "acknowledgement": arena_service.build_acknowledgement(comparison, request.user),
            },
            status=status.HTTP_200_OK,
        )

    def _resolve_arena_stream_params(self, conversation, validated_query_params, message):
        """Turn the arena query parameters into ``(comparison, role, model_hrid)``.

        Raises ``NotFound`` when the comparison does not belong to this conversation
        and user, ``ValidationError`` when it is closed or the side already ran.
        """
        comparison_id = validated_query_params.get("arena_comparison")
        side = validated_query_params.get("arena_side")
        if not comparison_id:
            return None
        comparison = self._get_pending_comparison_or_404(conversation, comparison_id)
        role = comparison.role_for_side(side)
        try:
            comparison = arena_service.claim_candidate(comparison, role, message)
        except arena_service.ArenaConflict as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
        return comparison, role, comparison.model_hrid_for_side(side)

    def _arena_candidate_response(self, conversation, validated_query_params, message):
        """Stream one arena candidate, or return ``None`` for a normal turn.

        A side that cannot be claimed gets a 409 response instead of a stream.
        """
        arena = self._resolve_arena_stream_params(conversation, validated_query_params, message)
        if arena is None or isinstance(arena, Response):
            return arena
        language = (
            self.request.user.language or self.request.LANGUAGE_CODE  # from the LocaleMiddleware
        )
        messages, force_web_search, ai_service = self._arena_candidate_run(
            conversation, arena, language
        )
        return self._stream_response(
            ai_service,
            messages,
            force_web_search=force_web_search,
            # Frozen at the draw like web search; absent from older snapshots.
            force_datagouv=arena[0].input_snapshot.get("force_datagouv", False),
        )

    def _arena_candidate_run(self, conversation, arena, language):
        """Build the run of one candidate from the input frozen when the turn was drawn.

        Returns ``(messages, force_web_search, ai_service)``. The candidate works on
        an in-memory copy of the conversation: only the comparison is written to.
        """
        comparison, role, model_hrid = arena
        snapshot = comparison.input_snapshot
        ai_service = AIAgentService(
            conversation=arena_service.snapshot_conversation(conversation, comparison),
            user=self.request.user,
            session=self.request.session,
            model_hrid=model_hrid,
            language=language,
            arena_comparison=comparison,
            arena_role=role,
        )
        messages = [UIMessage.model_validate(snapshot["request_ui_message"])]
        return messages, snapshot["force_web_search"], ai_service
