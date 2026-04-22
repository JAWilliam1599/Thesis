# Code Generation & Evaluation Pipeline UI

Simple user interfaces for running the code generation and evaluation pipeline. Choose between a modern web UI or a standalone desktop application.

## 📋 Overview

Two UI options are available:

1. **Web UI (Streamlit)** - `ui_app.py` - Modern, browser-based interface
2. **Desktop UI (tkinter)** - `ui_desktop.py` - Standalone desktop application

Both UIs provide:
- ✅ Easy configuration of generation parameters
- ✅ Real-time pipeline execution feedback
- ✅ Results display and evaluation reports
- ✅ Generated code view with save/download options
- ✅ History of recent runs
- ✅ Detailed logging

---

## 🌐 Option 1: Web UI (Streamlit) - Recommended

### Installation

Install Streamlit first:

```bash
pip install streamlit
```

### Usage

Run the web UI:

```bash
streamlit run ui_app.py
```

This will open your browser at `http://localhost:8501`

### Features

- **🚀 Run Pipeline Tab**
  - Enter your code generation prompt
  - Select provider (Bedrock or OpenRouter)
  - Configure model ID, API keys, and parameters
  - View real-time results with metrics
  - View generated Python code in the UI
  - Download generated code from the UI
  - See detailed evaluation reports

- **📊 View Results Tab**
  - Browse recent runs
  - View passed and failed code generations
  - Open code and report for each attempt
  - Inspect detailed evaluation reports

### Configuration

The web UI allows you to:

- **Provider**: Choose between `bedrock` (AWS) or `openrouter`
- **Model ID**: Specify the AI model to use
  - Bedrock and OpenRouter defaults can be edited directly in the UI fields
- **AWS Region**: For Bedrock (default: `us-east-1`)
- **API Key**: For OpenRouter (if blank, UI falls back to `OPENROUTER_API_KEY`)
- **Fail Below Score**: Evaluation score threshold (0-100, default: 60)
- **Max Regeneration**: Number of retry attempts (0-5, default: 2)
- **Verbose Logging**: Show detailed runtime logs

---

## 🖥️ Option 2: Desktop UI (tkinter)

No additional installation needed! tkinter comes with Python.

### Usage

Run the desktop UI:

```bash
python ui_desktop.py
```

A window will open with the pipeline interface.

### Features

- **Left Panel**: Configuration and prompt input
  - Provider selection
  - Model and API configuration
  - Pipeline parameters
  - Code prompt entry area

- **Right Panel**: Results and logs
  - 📋 Results tab: Summary, evaluation report, and generated code
  - 📊 Logs tab: Detailed execution logs
  - 📁 Recent Runs tab: Select run/type/attempt and open code + report

### Controls

- **▶️ Run Pipeline**: Execute the pipeline with current settings
- **🗑️ Clear**: Clear results and logs
- **🔄 Refresh History**: Update list of recent runs
- **💾 Save Current Code**: Save code shown in Results tab

---

## ⚙️ Configuration Options

### Provider Selection

#### AWS Bedrock
- Requires AWS credentials configured locally
- Set `AWS_REGION` or use `--region` parameter
- Model ID format: `anthropic.claude-3-5-sonnet-20241022-v2:0`

#### OpenRouter
- Requires OpenRouter API key
- Get API key from https://openrouter.ai/
- Enter API key in UI, or leave field empty to use exported `OPENROUTER_API_KEY`
- Model ID format depends on model provider naming (for example: `qwen/qwen3-coder-30b-a3b-instruct`)

### Pipeline Parameters

- **Fail Below Score**: The evaluation score threshold. If generated code scores below this, it's marked as failed and will be regenerated (if max-regen > 0)
- **Max Regeneration**: Number of times to automatically regenerate code after a failed evaluation

---

## 📊 Understanding Results

### Evaluation Report

Each run produces a report with:

- **Score** (0-100): Higher is better. Based on code quality, syntax, and risk assessment
- **Syntax OK**: Whether the generated code has valid Python syntax
- **Risk Score** (0-5): Code safety assessment
- **Approval**: Whether the code passed all checks
- **Issues**: List of identified problems or warnings
- **Line Count**: Number of lines in generated code

### Result Status

- ✅ **Passed**: Code generated successfully and passed evaluation
- ❌ **Failed**: Code failed evaluation (syntax error or score below threshold)
- 🔄 **Regenerated**: Code was automatically regenerated after failure

---

## 📁 Result Storage

Results are stored in `ExecCode/run_<timestamp>/`:

```
run_20260409T025933Z/
├── passed/
│   ├── passed_attempt_1_<timestamp>.py
│   └── passed_attempt_1_<timestamp>.json
└── failed/
    ├── failed_attempt_1_<timestamp>.py
    └── failed_attempt_1_<timestamp>.json
```

---

## 🔧 Troubleshooting

### "ModuleNotFoundError: No module named 'streamlit'"

Install Streamlit:
```bash
pip install streamlit
```

### "OPENROUTER_API_KEY not found"

Set environment variable:
```bash
export OPENROUTER_API_KEY=your_api_key_here
```

For fish shell persistent setting:
```bash
set -Ux OPENROUTER_API_KEY your_api_key_here
```

Then restart the terminal or app. You can still override it by typing a key directly in the UI.

### AWS Bedrock Authorization Error

Ensure AWS credentials are configured:
```bash
aws configure
```

Or set environment variables:
```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

### Pipeline Hangs or Times Out

- Check your internet connection
- Verify API keys are valid
- Try with verbose logging enabled to see detailed logs

---

## 💡 Tips

1. **Start Simple**: Begin with basic prompts to understand the system
2. **Iterate**: Use failed results to refine your prompts
3. **Monitor Scores**: Adjust `fail_below` based on your quality requirements
4. **Check Logs**: Use verbose mode to diagnose issues
5. **Review History**: Check recent runs to understand patterns

---

## 🚀 Quick Start

### First Run - Web UI

```bash
pip install streamlit
streamlit run ui_app.py
```

Then:
1. Open browser to `http://localhost:8501`
2. Select provider (`openrouter` if using OpenRouter)
3. Leave API key field empty to use exported `OPENROUTER_API_KEY`, or type a key directly
4. Enter a prompt like: "Create a Python function that validates email addresses"
5. Click "Run Pipeline"
6. Wait for results

### First Run - Desktop UI

```bash
python ui_desktop.py
```

Then:
1. Configure settings in left panel
2. Select provider (`openrouter` if using OpenRouter)
3. Leave API key field empty to use exported `OPENROUTER_API_KEY`, or type a key directly
4. Enter prompt in text area
5. Click "▶️ Run Pipeline"
6. Check Results and Logs tabs for output

---

## 📝 Example Prompts

- "Create a Python function that validates email addresses using regex"
- "Write a Python script to fetch weather data from an API and display it"
- "Implement a simple binary search algorithm with test cases"
- "Create a Python class for managing a todo list with save/load functionality"

---

## 📞 Support

For issues with the pipeline itself, check the logs and error messages. For specific model issues, consult the respective provider documentation:
- AWS Bedrock: https://docs.aws.amazon.com/bedrock/
- OpenRouter: https://openrouter.ai/docs

