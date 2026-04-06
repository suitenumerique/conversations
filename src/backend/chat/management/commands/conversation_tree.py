"""Display the tree of model instances belonging to a conversation."""

from django.core.management.base import BaseCommand, CommandError

from chat.models import ChatConversation

# !!! for dev, remove me !!!


class Command(BaseCommand):
    help = "Display the tree of model instances belonging to a conversation."

    def add_arguments(self, parser):
        parser.add_argument("conversation_id", type=str, help="UUID of the conversation")

    def handle(self, *args, **options):
        try:
            conversation = (
                ChatConversation.objects.select_related("owner", "project")
                .prefetch_related(
                    "attachments",
                    "collections__documents__attachment",
                )
                .get(pk=options["conversation_id"])
            )
        except ChatConversation.DoesNotExist:
            raise CommandError(f"Conversation {options['conversation_id']} not found.")  # noqa

        self.stdout.write(f"ChatConversation {conversation.pk}")
        self.stdout.write(f"  title: {conversation.title or '(none)'}")
        self.stdout.write(f"  owner: {conversation.owner}")
        self.stdout.write(f"  created: {conversation.created_at}")
        self.stdout.write(f"  collection_id (legacy): {conversation.collection_id or '(none)'}")

        # Project
        if conversation.project:
            p = conversation.project
            self.stdout.write(f"  +-- ChatProject {p.pk}")
            self.stdout.write(f"  |     title: {p.title}")
            for col in p.collections.all():
                self._print_collection(col, indent="  |     ")

        # Collections
        for col in conversation.collections.all():
            self._print_collection(col, indent="  ")

        # Attachments
        attachments = conversation.attachments.all()
        if attachments:
            self.stdout.write(f"  +-- Attachments ({len(attachments)})")
            for i, att in enumerate(attachments):
                prefix = "|" if i < len(attachments) - 1 else " "
                self.stdout.write(f"  |   +-- Attachment {att.pk}")
                self.stdout.write(f"  |   {prefix}     file: {att.file_name}")
                self.stdout.write(f"  |   {prefix}     type: {att.content_type}")
                self.stdout.write(f"  |   {prefix}     state: {att.upload_state}")
                self.stdout.write(f"  |   {prefix}     key: {att.key}")
                if att.conversion_from:
                    self.stdout.write(f"  |   {prefix}     converted_from: {att.conversion_from}")

        # Messages stats
        n_pydantic = len(conversation.pydantic_messages)
        n_ui = len(conversation.messages)
        self.stdout.write(f"  +-- Messages: {n_pydantic} pydantic, {n_ui} ui")

    def _print_collection(self, collection, indent="  "):
        self.stdout.write(f"{indent}+-- Collection {collection.pk}")
        self.stdout.write(f"{indent}|     backend: {collection.backend}")
        self.stdout.write(f"{indent}|     external_id: {collection.external_id or '(none)'}")
        self.stdout.write(f"{indent}|     name: {collection.name}")

        docs = collection.documents.all()
        if docs:
            self.stdout.write(f"{indent}|     +-- CollectionDocuments ({len(docs)})")
            for doc in docs:
                self.stdout.write(
                    f"{indent}|          - {doc.attachment.file_name} "
                    f"(attachment {doc.attachment.pk})"
                )
