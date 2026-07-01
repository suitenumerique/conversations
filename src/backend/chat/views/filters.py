"""Filter backends for chat conversation and project listings."""

from uuid import UUID

from rest_framework import filters

from core.filters import remove_accents


class TitleSearchFilter(filters.BaseFilterBackend):
    """Filter conversation by title (accent-insensitive)."""

    def filter_queryset(self, request, queryset, view):
        """Filter conversation by title."""
        if title := request.GET.get("title"):
            queryset = queryset.filter(title__unaccent__icontains=remove_accents(title))
        return queryset

    def get_schema_operation_parameters(self, view):
        """Return the schema for the ``title`` query parameter (drf-spectacular)."""
        return [
            {
                "name": "title",
                "required": False,
                "in": "query",
                "description": "Search conversations by title (accent-insensitive). "
                "When provided, the response uses a search-specific serializer "
                "with nested project info.",
                "schema": {"type": "string"},
            },
        ]


class ProjectFilter(filters.BaseFilterBackend):
    """Filter conversations by project.

    Accepts a `project` query parameter:
    - a UUID: conversations belonging to that specific project
    - "none": conversations not linked to any project
    - "any": conversations linked to any project
    """

    def filter_queryset(self, request, queryset, view):
        """Filter conversations by project."""
        project_id = request.GET.get("project")
        if project_id is None:
            return queryset
        if project_id == "none":
            return queryset.filter(project__isnull=True)
        if project_id == "any":
            return queryset.filter(project__isnull=False)
        try:
            UUID(project_id)
        except ValueError:
            return queryset.none()
        return queryset.filter(project_id=project_id)

    def get_schema_operation_parameters(self, view):
        """Return the schema for the ``project`` query parameter (drf-spectacular)."""
        return [
            {
                "name": "project",
                "required": False,
                "in": "query",
                "description": "Filter by project. Pass a UUID for a specific project, "
                '"none" for standalone conversations, or "any" for all project conversations.',
                "schema": {"type": "string"},
            },
        ]
