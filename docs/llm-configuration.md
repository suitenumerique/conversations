# LLM Configuration

This document describes how to configure Large Language Models (LLMs) in Conversations via the configuration file.

## Overview

Conversations uses a JSON configuration file to define LLM models and providers. This approach allows you to:
- Configure multiple LLM models from different providers
- Switch between models without code changes
- Customize model-specific settings like temperature, max tokens, and system prompts
- Enable or disable models dynamically

The overall structure consists of two main sections: `providers` and `models`.
Settings for models, provides customization through `settings` and `profile`, which corresponds to the 
Pydantic AI model settings and profile. While we currently not use those settings extensively, 
they are available for future use and advanced configurations, please reach us if you face any problem using them.

## Configuration File Location

The default LLM configuration file is located at:
```
src/backend/conversations/configuration/llm/default.json
```

You can override this location by setting the `LLM_CONFIGURATION_FILE_PATH` environment variable, but be careful as 
this path must be accessible by the backend application _inside the docker image_:
``` ini
LLM_CONFIGURATION_FILE_PATH=/path/to/your/llm/config.json
```

## Default Behavior

### Default Configuration

The default configuration file is useful for local development and running the test, while it can be used
in production, we suggest to create a specific one for production and replace the `settings.` values with
`environ.` one.

The default configuration file (`default.json`) includes:

1. **Two default models**:
   - `default-model`: The primary conversational model used for chat interactions
   - `default-summarization-model`: A specialized model for summarizing conversations

2. **One default provider**:
   - `default-provider`: An OpenAI-compatible provider that uses environment variables for configuration

### Environment Variable Integration

The configuration uses dynamic value resolution with two special prefixes:

- `settings.VARIABLE_NAME`: Resolves to a Django setting value
- `environ.VARIABLE_NAME`: Resolves to an environment variable value

For example, in the default configuration:
```json
{
  "model_name": "settings.AI_MODEL",
  "system_prompt": "settings.AI_AGENT_INSTRUCTIONS",
  "tools": "settings.AI_AGENT_TOOLS"
}
```

This allows to configure models in tests using the setting override mechanism from Django/Pytest (but might be replaced
later with a simple override of the full configuration like it's done in some tests already).

### Required Environment Variables

For the default configuration to work, you need to set these environment variables:

| Variable                      | Description                            | Example                     |
|-------------------------------|----------------------------------------|-----------------------------|
| `AI_API_KEY`                  | API key for the default provider       | `sk-...`                    |
| `AI_BASE_URL`                 | Base URL for the OpenAI-compatible API | `https://api.openai.com/v1` |
| `AI_MODEL`                    | Model name to use                      | `gpt-4o-mini`               |

### Optional Environment Variables

If you want to customize the agent behavior and tools, you can set these optional environment variables 
(defaults are provided in the default configuration):

| Variable                      | Description                            | Default           |
|-------------------------------|----------------------------------------|-------------------|
| `AI_AGENT_INSTRUCTIONS`       | System prompt for the agent            | see `settings.py` |
| `AI_AGENT_TOOLS`              | List of enabled tools                  | `[]`              |
| `SUMMARIZATION_SYSTEM_PROMPT` | Base prompt of the summarization agent | see `settings.py` |

### Model Selection

You can configure which models are used for specific tasks via environment variables:

| Variable                       | Description                              | Default                       |
|--------------------------------|------------------------------------------|-------------------------------|
| `LLM_DEFAULT_MODEL_HRID`       | HRID of the model used for conversations | `default-model`               |
| `LLM_SUMMARIZATION_MODEL_HRID` | HRID of the model used for summarization | `default-summarization-model` |

## Configuration Structure

The configuration file has two main sections:

### 1. Providers

Providers define the API endpoints and authentication for LLM services.

```json
{
  "providers": [
    {
      "hrid": "unique-provider-id",
      "base_url": "https://api.example.com/v1",
      "api_key": "environ.API_KEY_VAR",
      "kind": "openai"
    }
  ]
}
```

**Provider Fields:**

| Field      | Type   | Required | Description                                             |
|------------|--------|----------|---------------------------------------------------------|
| `hrid`     | string | Yes      | Unique identifier for the provider                      |
| `base_url` | string | Yes      | API base URL (can use `settings.` or `environ.` prefix) |
| `api_key`  | string | Yes      | API authentication key (use `environ.` here)            |
| `kind`     | string | Yes      | Provider type: `openai` or `mistral`                    |

### 2. Models

Models define the LLMs available in your application.

```json
{
  "models": [
    {
      "hrid": "unique-model-id",
      "model_name": "gpt-4o-mini",
      "human_readable_name": "GPT-4o Mini",
      "provider_name": "unique-provider-id",
      "profile": null,
      "settings": {},
      "is_active": true,
      "icon": null,
      "system_prompt": "You are a helpful assistant",
      "tools": []
    }
  ]
}
```

**Model Fields:**

| Field                 | Type         | Required | Description                                                                                         |
|-----------------------|--------------|----------|-----------------------------------------------------------------------------------------------------|
| `hrid`                | string       | Yes      | Unique identifier for the model                                                                     |
| `model_name`          | string       | Yes      | Name of the model as recognized by the provider (can use `settings.` or `environ.` prefix)          |
| `human_readable_name` | string       | Yes      | Display name shown to users                                                                         |
| `provider_name`       | string       | No*      | Reference to a provider's `hrid`                                                                    |
| `provider`            | object       | No*      | Inline provider definition (alternative to `provider_name`)                                         |
| `profile`             | object       | No       | Model-specific capabilities and settings                                                            |
| `settings`            | object       | No       | Model inference settings (temperature, max_tokens, etc.)                                            |
| `is_active`           | boolean      | Yes      | Whether the model is available for use                                                              |
| `icon`                | string/array | No       | Base64-encoded icon or array of icon parts                                                          |
| `system_prompt`       | string       | Yes      | Default system prompt for the model (can use `settings.` or `environ.` prefix)                      |
| `tools`               | array        | Yes      | List of enabled tools for this model (can use `settings.` or `environ.` prefix for the whole array) |
| `supports_streaming`  | boolean      | No       | Whether the model supports streaming responses                                                      |

\* Either `provider_name` or `provider` must be set, unless `model_name` is in the format `<provider>:<model>`.

## Adding New Models

### Example 1: Adding a New OpenAI Model

To add a new OpenAI model using the existing default provider:

```json
{
  "models": [
    // ...existing models...
    {
      "hrid": "gpt-4-turbo",
      "model_name": "gpt-4-turbo-preview",
      "human_readable_name": "GPT-4 Turbo",
      "provider_name": "default-provider",
      "profile": null,
      "settings": {
        "temperature": 0.7,
        "max_tokens": 4096
      },
      "is_active": true,
      "icon": null,
      "system_prompt": "You are an expert AI assistant.",
      "tools": ["web_search_brave_with_document_backend"],
      "supports_streaming": true
    }
  ],
  "providers": [
    // ...existing providers...
  ]
}
```

### Example 2: Adding a Model using Pydantic AI format

To add a model with a specific provider using the default Pydantic AI format, you don't need to define the provider separately if you use the `model_name` format `<provider>:<model>`.

1. **Add the model without provider**:

```json
{
  "models": [
    {
      "hrid": "claude-3-opus",
      "model_name": "anthropic:claude-3-opus-20240229",
      "human_readable_name": "Claude 3 Opus",
      "provider_name": null,
      "profile": null,
      "settings": {
        "temperature": 0.7,
        "max_tokens": 4096
      },
      "is_active": true,
      "icon": null,
      "system_prompt": "You are Claude, a helpful AI assistant.",
      "tools": []
    }
  ],
  "providers": []
}
```

2**Set the environment variable**:

Pydantic AI expects the API key in an environment variable named `ANTHROPIC_API_KEY` is this example, so set it accordingly:

```ini
ANTHROPIC_API_KEY=your-api-key-here
```

### Example 3: Adding a Mistral Model

For Mistral AI models using the Etalab platform:

```json
{
  "models": [
    {
      "hrid": "mistral-medium",
      "model_name": "mistral-medium-2508",
      "human_readable_name": "Mistral Medium (Etalab)",
      "provider_name": "mistral-etalab",
      "profile": null,
      "settings": {
        "temperature": 0.5,
        "max_tokens": 8192
      },
      "is_active": true,
      "icon": null,
      "system_prompt": "settings.AI_AGENT_INSTRUCTIONS",
      "tools": ["web_search_brave_with_document_backend"]
    }
  ],
  "providers": [
    {
      "hrid": "mistral-etalab",
      "base_url": "https://api.mistral.etalab.gouv.fr/",
      "api_key": "environ.MISTRAL_ETALAB_API_KEY",
      "kind": "mistral"
    }
  ]
}
```

### Example 4: Using Inline Provider Definition

Instead of referencing a provider by name, you can define it inline if you use a unique configuration:

```json
{
  "models": [
    {
      "hrid": "custom-model",
      "model_name": "custom-model-v1",
      "human_readable_name": "Custom Model",
      "provider": {
        "hrid": "custom-provider-inline",
        "base_url": "https://custom-api.example.com/v1",
        "api_key": "environ.CUSTOM_API_KEY",
        "kind": "openai"
      },
      "settings": {},
      "is_active": true,
      "icon": null,
      "system_prompt": "You are a custom assistant.",
      "tools": []
    }
  ]
}
```

## Advanced Configuration

### Model Settings

The `settings` object supports various inference parameters:

```json
{
  "settings": {
    "max_tokens": 4096,
    "temperature": 0.7,
    "top_p": 0.9,
    "timeout": 60.0,
    "parallel_tool_calls": true,
    "seed": 42,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "logit_bias": {},
    "stop_sequences": [],
    "extra_headers": {},
    "extra_body": {}
  }
}
```

### Model Profile

The `profile` object defines model capabilities:

```json
{
  "profile": {
    "supports_tools": true,
    "supports_json_schema_output": true,
    "supports_json_object_output": true,
    "default_structured_output_mode": "json_schema",
    "thinking_tags": ["<thinking>", "</thinking>"],
    "ignore_streamed_leading_whitespace": true
  }
}
```

### Available Tools

Tools can be specified in the `tools` array. Common tools include:
- `web_search_brave_with_document_backend`: Web search using Brave API with document processing

You can also reference the tools list from Django settings:
```json
{
  "tools": "settings.AI_AGENT_TOOLS"
}
```

### Custom Icons

Icons can be provided as base64-encoded PNG images. For long strings, you can split them into an array:

```json
{
  "icon": [
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABwAAAAcCAMAAABF0y+m",
    "AAAAn1BMVEUALosAKoovTZjw8vb////+9/jlPUniAAziABUAGIWbpsTwq7HhAAAA"
  ]
}
```

## Validation

The configuration is validated when loaded. Common validation errors include:

- **Provider not found**: A model references a `provider_name` that doesn't exist in the `providers` array
- **Missing provider**: Neither `provider_name` nor `provider` is specified, and `model_name` is not in `<provider>:<model>` format
- **Environment variable not set**: A value using `environ.` prefix references an undefined environment variable
- **Django setting not set**: A value using `settings.` prefix references an undefined Django setting
- **Invalid provider kind**: The `kind` field must be either `openai` or `mistral`

## Testing Your Configuration

After modifying the configuration file, you can test it by:

1. **Checking for syntax errors**:
   ```bash
   python -m json.tool src/backend/conversations/configuration/llm/default.json
   ```

2. **Starting the application** and checking the logs for validation errors

3. **Using the Django shell** to load the configuration:
   ```bash
   ./bin/manage shell
   ```
   ```python
   from django.conf import settings
   models = settings.LLM_CONFIGURATIONS
   models.keys()  # Should show all model HRIDs
   ```

## Best Practices

1. **Use environment variables** for sensitive data like API keys (with `environ.` prefix)
2. **Use Django settings** for configurable values that may change between environments (with `settings.` prefix)
3. **Keep provider definitions separate** from models to avoid duplication when using multiple models from the same provider
4. **Set `is_active: false`** for models you want to keep in the configuration but temporarily disable
5. **Use descriptive `hrid` values** that clearly identify the model and provider
6. **Document custom configurations** in your deployment documentation
7. **Test configuration changes** in a development environment before deploying to production

## See Also

- [Environment Variables Documentation](env.md) - For configuring environment variables
- [Installation Guide](installation.md) - For deployment instructions

