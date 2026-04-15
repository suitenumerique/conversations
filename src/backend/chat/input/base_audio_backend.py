"""Base class for audio input backends."""

from abc import ABC, abstractmethod


class BaseAudioBackend(ABC):
    """Abstract base class for audio transcription backends."""

    @abstractmethod
    def transcribe(self, file_name: str, file_content: bytes, content_type: str) -> str:
        """
        Transcribe the given audio file to text.

        Args:
            file_name (str): The original file name of the audio file.
            file_content (bytes): The raw audio file content.
            content_type (str): The MIME type of the audio file.
            language (str): The language to transcribe the audio content in.

        Returns:
            str: The transcribed text.

        Raises:
            TranscriptionError: If an error occurs during transcription.
        """
