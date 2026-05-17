Files:

- bedrock_codegen.py: asks for user input, calls Bedrock, writes generated Python code.
  Enhanced error messages for Bedrock quota throttling and optional model validation.
- run_generation_and_eval.py: generation pipeline that also runs evaluation from Eval.
	If evaluation fails, it can auto-regenerate and use the eval JSON report as the next prompt.

Examples:

python bedrock_codegen.py --prompt "Write Python code to read messages from SQS"

python bedrock_codegen.py --prompt "Write Python code to read messages from SQS" --validate-model

python run_generation_and_eval.py --prompt "Write Python code to create a DynamoDB table"

python run_generation_and_eval.py --prompt "Write Python code to create a DynamoDB table" --max-regen 3

Optional arguments for bedrock_codegen.py:

- --output path/to/file.py
- --model-id qwen.qwen3-coder-30b-a3b-v1:0 (default)
- --region ap-southeast-2 (default)
- --validate-model
  Validate that the configured model ID is available in your account before generating code.
  Useful for catching configuration errors early.

Optional arguments for run_generation_and_eval.py:

- --fail-below 60
- --max-regen 2
- --model-id, --region (passed to bedrock_codegen.py)

Error Handling:

If Bedrock returns a "Too many tokens per day" error, your account/model has exceeded its daily token
quota. Check AWS Console > Bedrock > Service Quotas to view limits and request increases if needed.
You can retry after the quota window resets.
