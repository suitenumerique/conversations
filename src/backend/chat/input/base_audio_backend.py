"""Base class for audio input backends."""

from abc import ABC, abstractmethod
from typing import IO


class BaseAudioBackend(ABC):
    """Abstract base class for audio transcription backends."""

    @abstractmethod
    def transcribe(self, file_name: str, file_content: IO[bytes], content_type: str) -> str:
        """
        Transcribe the given audio file to text.

        Args:
            file_name (str): The original file name of the audio file.
            file_content (IO[bytes]): A file-like object with the audio content.
            content_type (str): The MIME type of the audio file.

        Returns:
            str: The transcribed text.

        Raises:
            TranscriptionError: If an error occurs during transcription.
        """
