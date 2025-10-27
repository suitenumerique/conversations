"""tools for testing chat functionality"""

import re


def replace_uuids_with_placeholder(text):
    """Replace all UUIDs in the given text with a placeholder."""
    text = re.sub('"toolCallId":"([a-z0-9-]){36}"', '"toolCallId":"XXX"', text)
    text = re.sub('"toolCallId":"pyd_ai_([a-z0-9]){32}"', '"toolCallId":"pyd_ai_YYY"', text)
    text = re.sub('"([a-z0-9-]){36}"', '"<mocked_uuid>"', text)
    return text
