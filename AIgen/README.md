# AIgen — Code Generation Module

## Purpose

Generate Python AWS SDK code from natural language prompts using Bedrock or OpenRouter LLM APIs.

## Files

| File | Purpose |
|------|---------|
| `bedrock_codegen.py` | Core Bedrock code generation with prompt handling and model validation |
| `openrouter_codegen.py` | Alternative provider using OpenRouter API |
| `run_generation_and_eval.py` | Pipeline coordinator: generates, evaluates, and auto-regenerates on failure |

## Usage

### Basic Generation (Bedrock)

```bash
python bedrock_codegen.py --prompt "Write Python code to read messages from SQS"
```

### With Model Validation

```bash
python bedrock_codegen.py --prompt "..." --validate-model
```

### Full Pipeline (Generate + Evaluate)

```bash
python run_generation_and_eval.py --prompt "Create Python code that creates a DynamoDB table"
```

### With Auto-Regeneration on Failures

```bash
python run_generation_and_eval.py --prompt "..." --max-regen 3
```

## Command-Line Options

### bedrock_codegen.py

| Option | Description | Default |
|--------|-------------|---------|
| `--prompt` | Code generation request | Required |
| `--output` | Output file path | `ExecCode/generated_code.py` |
| `--model-id` | Bedrock model ID | `qwen.qwen3-coder-30b-a3b-v1:0` |
| `--region` | AWS region | `ap-southeast-2` |
| `--validate-model` | Verify model availability before generation | false |

### run_generation_and_eval.py

| Option | Description | Default |
|--------|-------------|---------|
| `--provider` | Generation provider: `bedrock` or `openrouter` | `bedrock` |
| `--prompt` | Code generation request | Interactive input if missing |
| `--model-id` | Model ID for provider | Provider-specific default |
| `--region` | AWS region (Bedrock only) | `ap-southeast-2` |
| `--api-key` | OpenRouter API key | Reads from `OPENROUTER_API_KEY` env |
| `--fail-below` | Regenerate if eval score below threshold | 60 |
| `--max-regen` | Maximum regeneration attempts | 2 |
| `--deployment-context` | Risk scoring context: `public`/`internal`/`onprem`/`sandbox` | `internal` |
| `--verbose` | Show logs in console | false |

## Error Handling

### Bedrock Quota Errors

If you see "Too many tokens per day":
1. Check AWS Console > Bedrock > Service Quotas
2. View your model's token limits
3. Request quota increases if needed
4. Quota resets daily

### Model Not Found

Use `--validate-model` flag to catch configuration issues early:

```bash
python bedrock_codegen.py --prompt "..." --model-id invalid_model --validate-model
```

This will fail immediately with a clear error instead of during generation.

## Conventions

- **Provider Abstraction:** Keep Bedrock and OpenRouter logic behind provider flags, not one-off branches
- **Model Defaults:** Centralized and overrideable via CLI
- **Credentials:** Use environment variables (`AWS_*`, `OPENROUTER_API_KEY`), never hardcode
- **Run Artifacts:** Preserve timestamped folder structure under `ExecCode/run_<timestamp>/`
- **Regeneration Prompts:** Include evaluation feedback as JSON when available

## Output

By default, generated code is saved to:
```
ExecCode/generated_code.py
```

In pipeline mode with run tracking:
```
ExecCode/run_<timestamp>/
  ├── prompt.txt
  ├── passed/
  │   ├── passed_attempt_1_<timestamp>.py
  │   └── passed_attempt_1_<timestamp>.json
  └── failed/
      ├── failed_attempt_1_<timestamp>.py
      └── failed_attempt_1_<timestamp>.json
```

## Related Modules

- **Eval/** — Evaluates generated code for security and quality
- **ExecCode/** — Storage for generated artifacts
- **ExecComponent/** — Runtime execution utilities
- **run_generation_and_eval.py** — Integration point between generation and evaluation

## Dependencies

- `boto3` — AWS SDK for Bedrock API
- `botocore` — AWS service interactions
- `requests` — HTTP client for OpenRouter
- See [requirements.txt](../requirements.txt) for full list
