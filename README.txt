Project workflow:

1) Generate Python AWS SDK code from Bedrock in AIgen.
2) Save generated code into ExecCode.
3) Evaluate generated code with Python scripts in Eval.

Setup:

- Install dependencies: pip install -r requirements.txt
- Configure AWS credentials and region (for example with environment variables or AWS profile):
	- AWS_ACCESS_KEY_ID
	- AWS_SECRET_ACCESS_KEY
	- AWS_REGION
- Optional for OpenRouter provider:
	- OPENROUTER_API_KEY
	- If UI API key field is empty, both UIs use OPENROUTER_API_KEY automatically.

UI options:

- Web UI (Streamlit):
	- Install Streamlit: pip install streamlit
	- Run: streamlit run ui_app.py
- Desktop UI (tkinter):
	- Run: python ui_desktop.py

OpenRouter key examples:

- bash/zsh session:
	- export OPENROUTER_API_KEY=your_api_key_here
- fish persistent:
	- set -Ux OPENROUTER_API_KEY your_api_key_here

Run full pipeline (generate + evaluate):

python AIgen/run_generation_and_eval.py --prompt "Create Python code that lists S3 buckets using boto3"

With automatic regeneration on failed evaluation:

python AIgen/run_generation_and_eval.py --prompt "Create Python code that lists S3 buckets using boto3" --max-regen 2

Run generation only:

python AIgen/bedrock_codegen.py --prompt "Create Python code that uploads a file to S3"

With model validation:

python AIgen/bedrock_codegen.py --prompt "Create Python code that uploads a file to S3" --validate-model

Run evaluation only:

python Eval/evaluate_generated_code.py --file ExecCode/generated_code.py

Notes:

- Default model ID is qwen.qwen3-coder-30b-a3b-v1:0.
- If Bedrock uses a different model ID in your account, pass --model-id explicitly.
- Use --validate-model to verify the model is available before generating code.
- If you hit "Too many tokens per day" errors, check Bedrock service quotas in AWS Console.
