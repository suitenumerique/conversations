# Evaluation

To allow simple evaluation of language models, [EvalAP](https://github.com/etalab-ia/evalap/) provides an API 
and a web interface to run evaluations on various datasets using different metrics.

To allow to easily integrate EvalAP with Conversations a new endpoint "OpenAI compatible" is provided to call
the conversation agent.


> **Warning:**
> 
> This is not really an Open AI compatible API, but it follows the same structure to make it easier
to use with existing tools. We only support simple inputs and outputs (no streaming, no function calls, etc).
The result returned will already have called the tools, etc.

This endpoint is only available when running the stack locally (ie in "development" or "tests" mode) under the
`/v1/chat/completions` endpoint.

See the backend's `evaluation/views.py` module for more details.

## Conversations' configuration

First you need to configure the backend for the experiment you want to run. For instance, if you want to compare
the Agent answer with and without a retrieval tool, you will need:

- To create the demo data by running:

```shell
$ make demo
```

- To update settings to the point to a new LLM configuration file, for instance in `env.d/development/common`:

```ini
LLM_CONFIGURATION_FILE_PATH = /app/conversations/configuration/llm/evalap_experiments.json
```

And create the file `conversations/configuration/llm/evalap_experiments.json` with the following content:

```json
{
  "models": [
    {
      "hrid": "mistral-medium-2508-raw",
      "model_name": "mistral-medium-2508",
      "human_readable_name": "Mistral Medium 2508",
      "provider_name": "mistral",
      "profile": null,
      "settings": {},
      "is_active": true,
      "icon": null,
      "system_prompt": "settings.AI_AGENT_INSTRUCTIONS",
      "tools": []
    },
    {
      "hrid": "mistral-medium-2508-with-web-search",
      "model_name": "mistral-medium-2508",
      "human_readable_name": "Mistral Medium 2508",
      "provider_name": "mistral",
      "profile": null,
      "settings": {},
      "is_active": true,
      "icon": null,
      "system_prompt": "settings.AI_AGENT_INSTRUCTIONS",
      "tools": ["web_search_brave"]
    },
    {
      "hrid": "default-summarization-model",
      "model_name": "mistral-medium-2508",
      "human_readable_name": "Mistral Medium 2508",
      "provider_name": "mistral",
      "profile": null,
      "settings": {},
      "is_active": true,
      "icon": null,
      "system_prompt": "settings.SUMMARIZATION_SYSTEM_PROMPT",
      "tools": []
    }
  ],
  "providers": [
    {
      "hrid": "mistral",
      "base_url": "https://api.mistral.ai/",
      "api_key": "environ.MISTRAL_API_KEY",
      "kind": "mistral"
    }
  ]
}
```

Which defines two models for the same LLM, one with a web search tool and one without.

- Create the "SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS" if not already done:

```ini
SPECIFIC_RAG_DOCUMENT_SEARCH_TOOLS={"tool_rag_french_public_services": {"collection_ids": [784, 785],"feature_flag_value": "disabled","tool_description":  "Use this tool when the user asks for information about French public services, the French labor market, employment laws, social benefits, or assistance with administrative procedures."}}
```


> **Note:**
> 
> The specific tool configuration is not mandatory for evaluations, only if you want to 
> test them.

- Restart your stack to apply the changes:

```shell
$ make run-backend
```

## EvalAP configuration

You will need to configure EvalAP to call Conversations for chat completion.

### Run the stack

I needed to update the Docker compose file to add:

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

Globally I followed the instructions in the EvalAP documentation, had a few issues with the stack initialization
but finally managed to run it with.

### Create the dataset

Read the EvalAP documentation to create a new dataset. I did a simple dataset with only two samples to check
the evaluation works.

### Create the evaluation

Same as before, read the EvalAP documentation to create a new evaluation.

The important part is to configure the model to call Conversations, and use the extra parameters to
adapt feature flags if needed.

```python
import requests

# Replace with your Evalap API endpoint
API_URL = "http://localhost:8000/v1"

# Replace with your API key or authentication token
HEADERS = {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
}

# Define your experiment set with CV schema
expset_name = "model_comparison_v1"
expset_readme = "Comparing performance of various LLMs on a QA dataset."
metrics = ["judge_precision", "output_length", "generation_time"]

# Parameters common to all experiments
common_params = {
    "dataset": "Dataset Bidon",  # assuming this dataset has been added before
    #"model": {"sampling_params": {"temperature": 0.2}},
    "metrics": metrics,
    "judge_model": "albert-large",
}

# Parameters that will vary across experiments
grid_params = {
    "model": [
        {
            "name": "etalab-plateform-mistral-medium-2508",
            "aliased_name": "Mistral Medium",
            # base_url points to Conversations API
            "base_url": f"http://host.docker.internal:8071/v1",
            "api_key": "plop",
            "extra_params": {
                "feature_flags": {
                    # Disable RAG tool
                    "tool_rag_french_public_services": "DISABLED",
                },
            },
        },
        {
            "name": "etalab-plateform-mistral-medium-2508",
            "aliased_name": "Mistral Medium + RAG",
            "base_url": f"http://host.docker.internal:8071/v1",
            "api_key": "plop",
            "extra_params": {
                "feature_flags": {
                    # Enable RAG tool
                    "tool_rag_french_public_services": "ENABLED",
                },
            },
        },
    ],
}

# Create the experiment set with CV schema
expset = {
    "name": expset_name,
    "readme": expset_readme,
    "cv": {
        "common_params": common_params,
        "grid_params": grid_params,
        "repeat": 3  # Run each combination 3 times to measure variability
    }
}

# Launch the experiment set
requests.delete(f'{API_URL}/experiment_set/12', json=expset, headers=HEADERS)
response = requests.post(f'{API_URL}/experiment_set', json=expset, headers=HEADERS)
expset_id = response.json()["id"]
print(f"Experiment set {expset_id} is running")
```
