"""Fake weather tool for the chat agent."""


def get_current_weather(location: str, unit: str):
    """
    Get the current weather in a given location.

    Args:
        location (str): The city and state, e.g. San Francisco, CA.
        unit (str): The unit of temperature, either 'celsius' or 'fahrenheit'.

    Returns:
        dict: A dictionary containing the location, temperature, and unit.
    """
    return {
        "location": location,
        "temperature": 22 if unit == "celsius" else 72,
        "unit": unit,
    }
