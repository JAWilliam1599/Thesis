"""
Desktop UI for Code Generation and Evaluation Pipeline using tkinter
Alternative to the Streamlit web UI - runs as a standalone desktop application
"""
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import (
    Tk, Frame, Label, Text, Button,
    Spinbox, Checkbutton, BooleanVar, scrolledtext,
    messagebox, filedialog, StringVar, END, DISABLED, NORMAL, TclError
)
from tkinter import ttk


class PipelineUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Code Generation & Evaluation Pipeline")
        self.root.geometry("1200x800")
        self.root.minsize(900, 600)
        
        # Workspace paths
        self.root_dir = Path(__file__).resolve().parent
        self.exec_code_dir = self.root_dir / "ExecCode"
        
        # State
        self.is_running = False
        self.last_results = None
        self.run_dir_map = {}
        self.history_attempt_map = {}
        
        # Setup UI
        self._setup_styles()
        self._create_ui()
    
    def _setup_styles(self):
        """Configure ttk styles"""
        self.style = ttk.Style()
        self.style.theme_use("clam")
    
    def _create_ui(self):
        """Create the main UI layout"""
        # Create main frames
        control_frame = ttk.Frame(self.root)
        control_frame.pack(side="left", fill="both", expand=False, padx=10, pady=10, ipadx=10)
        
        output_frame = ttk.Frame(self.root)
        output_frame.pack(side="right", fill="both", expand=True, padx=10, pady=10)
        
        # Control panel
        self._create_control_panel(control_frame)
        
        # Output panel
        self._create_output_panel(output_frame)
    
    def _create_control_panel(self, parent):
        """Create left-side control panel"""
        title_label = ttk.Label(parent, text="Settings", font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 15))
        
        # Provider selection
        ttk.Label(parent, text="Provider:", font=("Arial", 10, "bold")).pack(anchor="w")
        self.provider_var = ttk.Combobox(
            parent,
            values=["bedrock", "openrouter"],
            state="readonly",
            width=20
        )
        self.provider_var.set("bedrock")
        self.provider_var.pack(pady=(0, 10), fill="x")
        
        # Model ID
        ttk.Label(parent, text="Model ID:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.model_id_var = ttk.Entry(parent, width=25)
        self.model_id_var.insert(0, "qwen/qwen3-coder-30b-a3b-instruct")
        self.model_id_var.pack(pady=(0, 10), fill="x")
        
        # Region (for Bedrock)
        ttk.Label(parent, text="AWS Region:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.region_var = ttk.Entry(parent, width=25)
        self.region_var.insert(0, "us-east-1")
        self.region_var.pack(pady=(0, 10), fill="x")
        
        # API Key (for OpenRouter)
        ttk.Label(parent, text="API Key (OpenRouter):", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.api_key_var = ttk.Entry(parent, width=25, show="*")
        self.api_key_var.pack(pady=(0, 10), fill="x")
        
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=10)
        
        # Fail below score
        ttk.Label(parent, text="Fail Below Score:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.fail_below_var = Spinbox(parent, from_=0, to=100, width=23)
        self.fail_below_var.delete(0, END)
        self.fail_below_var.insert(0, "60")
        self.fail_below_var.pack(pady=(0, 10), fill="x")
        
        # Max regeneration
        ttk.Label(parent, text="Max Regeneration:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.max_regen_var = Spinbox(parent, from_=0, to=5, width=23)
        self.max_regen_var.delete(0, END)
        self.max_regen_var.insert(0, "2")
        self.max_regen_var.pack(pady=(0, 10), fill="x")
        
        # Verbose logging
        self.verbose_var = BooleanVar()
        ttk.Checkbutton(
            parent,
            text="Verbose Logging",
            variable=self.verbose_var
        ).pack(anchor="w", pady=(10, 0))
        
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=10)
        
        # Prompt input
        ttk.Label(parent, text="Code Generation Prompt:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(10, 0))
        
        self.prompt_text = scrolledtext.ScrolledText(
            parent,
            height=12,
            width=35,
            wrap="word",
            font=("Arial", 9)
        )
        self.prompt_text.bind("<Control-BackSpace>", self._delete_previous_word_in_prompt)
        self.prompt_text.pack(pady=(5, 10), fill="both", expand=True)
        self.prompt_text.insert("1.0", "Describe the Python code you want to generate...")
        
        # Buttons
        button_frame = ttk.Frame(parent)
        button_frame.pack(fill="x", pady=10)
        
        self.run_button = ttk.Button(
            button_frame,
            text="▶️ Run Pipeline",
            command=self._run_pipeline
        )
        self.run_button.pack(side="left", fill="both", expand=True, padx=(0, 5))
        
        self.clear_button = ttk.Button(
            button_frame,
            text="🗑️  Clear",
            command=self._clear_results
        )
        self.clear_button.pack(side="left", fill="both", expand=True)
    
    def _create_output_panel(self, parent):
        """Create right-side output panel"""
        title_label = ttk.Label(parent, text="Results & Logs", font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        
        # Results tab
        results_frame = ttk.Frame(self.notebook)
        self.notebook.add(results_frame, text="📋 Results")
        self.result_status_label = ttk.Label(results_frame, text="No run yet", font=("Arial", 10, "bold"))
        self.result_status_label.pack(anchor="w", pady=(0, 8))

        self.result_notebook = ttk.Notebook(results_frame)
        self.result_notebook.pack(fill="both", expand=True)

        summary_frame = ttk.Frame(self.result_notebook)
        self.result_notebook.add(summary_frame, text="🧾 Summary")
        self.summary_text = scrolledtext.ScrolledText(
            summary_frame,
            height=8,
            width=80,
            wrap="word",
            font=("Courier", 9)
        )
        self.summary_text.pack(fill="both", expand=True)

        report_frame = ttk.Frame(self.result_notebook)
        self.result_notebook.add(report_frame, text="📊 Evaluation Report")
        self.report_text = scrolledtext.ScrolledText(
            report_frame,
            height=20,
            width=80,
            wrap="word",
            font=("Courier", 9)
        )
        self.report_text.pack(fill="both", expand=True)

        code_frame = ttk.Frame(self.result_notebook)
        self.result_notebook.add(code_frame, text="💻 Generated Code")
        code_button_frame = ttk.Frame(code_frame)
        code_button_frame.pack(fill="x", pady=(0, 6))
        self.save_code_button = ttk.Button(code_button_frame, text="💾 Save Current Code", command=self._save_current_code)
        self.save_code_button.pack(side="left")
        self.code_text = scrolledtext.ScrolledText(
            code_frame,
            height=20,
            width=80,
            wrap="none",
            font=("Courier", 9)
        )
        self.code_text.pack(fill="both", expand=True)
        
        # Logs tab
        logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(logs_frame, text="📊 Logs")
        
        self.logs_text = scrolledtext.ScrolledText(
            logs_frame,
            height=20,
            width=80,
            wrap="word",
            font=("Courier", 8)
        )
        self.logs_text.pack(fill="both", expand=True)
        
        # History tab
        history_frame = ttk.Frame(self.notebook)
        self.notebook.add(history_frame, text="📁 Recent Runs")
        
        self._create_history_panel(history_frame)
    
    def _create_history_panel(self, parent):
        """Create history/recent runs panel"""
        ttk.Label(parent, text="Recent Runs:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 8))

        selection_frame = ttk.Frame(parent)
        selection_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(selection_frame, text="Run:").pack(side="left", padx=(0, 6))
        self.history_run_var = StringVar()
        self.history_run_combo = ttk.Combobox(selection_frame, textvariable=self.history_run_var, state="readonly", width=38)
        self.history_run_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.history_run_combo.bind("<<ComboboxSelected>>", self._on_history_run_selected)

        ttk.Button(selection_frame, text="🔄 Refresh", command=self._refresh_history).pack(side="left")

        filter_frame = ttk.Frame(parent)
        filter_frame.pack(fill="x", pady=(0, 8))

        ttk.Label(filter_frame, text="Type:").pack(side="left", padx=(0, 6))
        self.history_type_var = StringVar(value="passed")
        self.history_type_combo = ttk.Combobox(filter_frame, textvariable=self.history_type_var, state="readonly", width=12)
        self.history_type_combo["values"] = ["passed", "failed"]
        self.history_type_combo.pack(side="left", padx=(0, 8))
        self.history_type_combo.bind("<<ComboboxSelected>>", self._on_history_type_selected)

        ttk.Label(filter_frame, text="Attempt:").pack(side="left", padx=(0, 6))
        self.history_attempt_var = StringVar()
        self.history_attempt_combo = ttk.Combobox(filter_frame, textvariable=self.history_attempt_var, state="readonly", width=42)
        self.history_attempt_combo.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ttk.Button(filter_frame, text="Open", command=self._open_selected_attempt).pack(side="left")

        self.history_notebook = ttk.Notebook(parent)
        self.history_notebook.pack(fill="both", expand=True)

        history_report_frame = ttk.Frame(self.history_notebook)
        self.history_notebook.add(history_report_frame, text="📊 Report")
        self.history_report_text = scrolledtext.ScrolledText(
            history_report_frame,
            height=16,
            width=80,
            wrap="word",
            font=("Courier", 9)
        )
        self.history_report_text.pack(fill="both", expand=True)

        history_code_frame = ttk.Frame(self.history_notebook)
        self.history_notebook.add(history_code_frame, text="💻 Code")
        self.history_code_text = scrolledtext.ScrolledText(
            history_code_frame,
            height=16,
            width=80,
            wrap="none",
            font=("Courier", 9)
        )
        self.history_code_text.pack(fill="both", expand=True)
    
    def _run_pipeline(self):
        """Run the pipeline in a separate thread"""
        prompt = self.prompt_text.get("1.0", END).strip()
        
        if not prompt or prompt == "Describe the Python code you want to generate...":
            messagebox.showwarning("Empty Prompt", "Please enter a code generation prompt.")
            return
        
        if self.is_running:
            messagebox.showwarning("Already Running", "Pipeline is already running. Please wait...")
            return
        
        # Disable controls
        self.is_running = True
        self._update_ui_state(DISABLED)
        
        # Run in separate thread
        thread = threading.Thread(target=self._execute_pipeline, args=(prompt,), daemon=True)
        thread.start()

    def _delete_previous_word_in_prompt(self, _event):
        """Delete the previous word in prompt text for Ctrl+Backspace behavior."""
        try:
            insert_idx = self.prompt_text.index("insert")
            prev_word_start = self.prompt_text.index("insert -1c wordstart")
            if prev_word_start != insert_idx:
                self.prompt_text.delete(prev_word_start, insert_idx)
        except TclError:
            pass
        return "break"
    
    def _execute_pipeline(self, prompt):
        """Execute pipeline and update UI with results"""
        try:
            self.result_status_label.config(text="🔄 Running pipeline...")
            self.summary_text.config(state=NORMAL)
            self.summary_text.delete("1.0", END)
            self.summary_text.insert(END, "Running pipeline, please wait...\n")
            self.summary_text.config(state=DISABLED)
            
            self.logs_text.config(state=NORMAL)
            self.logs_text.delete("1.0", END)
            
            # Build command
            cmd = [
                sys.executable,
                str(self.root_dir / "AIgen" / "run_generation_and_eval.py"),
                "--provider", self.provider_var.get(),
                "--prompt", prompt,
                "--fail-below", self.fail_below_var.get(),
                "--max-regen", self.max_regen_var.get(),
            ]
            env = os.environ.copy()
            
            if self.model_id_var.get():
                cmd.extend(["--model-id", self.model_id_var.get()])
            
            if self.provider_var.get() == "bedrock" and self.region_var.get():
                cmd.extend(["--region", self.region_var.get()])
            elif self.provider_var.get() == "openrouter":
                api_key_input = self.api_key_var.get().strip()
                env_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
                if api_key_input:
                    env["OPENROUTER_API_KEY"] = api_key_input
                elif not env_api_key:
                    self.logs_text.insert(END, "WARNING: API Key field is empty and OPENROUTER_API_KEY is not set.\n")
            
            if self.verbose_var.get():
                cmd.append("--verbose")
            
            # Run pipeline
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.root_dir / "AIgen"),
                env=env,
            )
            
            # Update logs
            self.logs_text.insert(END, "=== STDOUT ===\n")
            self.logs_text.insert(END, result.stdout)
            self.logs_text.insert(END, "\n\n=== STDERR ===\n")
            self.logs_text.insert(END, result.stderr)
            self.logs_text.config(state=DISABLED)
            
            # Parse and display results
            self._display_results(result)
            
            # Refresh history
            self.root.after(100, self._refresh_history)
        
        except Exception as e:
            self.result_status_label.config(text=f"❌ Error: {str(e)}")
            self.summary_text.config(state=NORMAL)
            self.summary_text.delete("1.0", END)
            self.summary_text.insert(END, f"Unexpected error while running pipeline:\n{str(e)}\n")
            self.summary_text.config(state=DISABLED)
        
        finally:
            self.is_running = False
            self._update_ui_state(NORMAL)
    
    def _display_results(self, result):
        """Parse and display pipeline results"""
        report_data = None
        generated_code = ""

        latest_run_dir = self._get_latest_run_dir()
        latest_context = self._get_latest_attempt_context(latest_run_dir) if latest_run_dir else None
        if latest_context is not None:
            report_data = latest_context.get("report")
            generated_code = latest_context.get("code", "")

        if report_data is None:
            report_data = self._extract_json_from_output(result.stdout)

        self.last_results = {
            "return_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "report": report_data,
            "generated_code": generated_code,
            "run_dir": str(latest_run_dir) if latest_run_dir else None,
        }

        status_text = "✅ Pipeline completed successfully" if result.returncode == 0 else f"❌ Pipeline failed (exit code {result.returncode})"
        self.result_status_label.config(text=status_text)

        self.summary_text.config(state=NORMAL)
        self.summary_text.delete("1.0", END)
        self.summary_text.insert(END, status_text + "\n\n")
        if latest_run_dir is not None:
            self.summary_text.insert(END, f"Run folder: {latest_run_dir}\n")
        if report_data is not None:
            self.summary_text.insert(END, f"Quality Score: {report_data.get('score', 'N/A')}\n")
            self.summary_text.insert(END, f"Risk Score: {report_data.get('risk_score', 'N/A')}\n")
            self.summary_text.insert(END, f"Risk Level: {report_data.get('risk_level', 'N/A')}\n")
            self.summary_text.insert(END, f"Risk Action: {report_data.get('risk_action', 'N/A')}\n")
            self.summary_text.insert(END, f"Syntax OK: {report_data.get('syntax_ok', 'N/A')}\n")
            self.summary_text.insert(END, f"Approval: {report_data.get('approval', 'N/A')}\n")
        self.summary_text.config(state=DISABLED)

        self.report_text.config(state=NORMAL)
        self.report_text.delete("1.0", END)
        if report_data is not None:
            self.report_text.insert(END, json.dumps(report_data, indent=2))
        else:
            self.report_text.insert(END, "No evaluation report found.\n\nRaw output:\n")
            self.report_text.insert(END, result.stdout)
        self.report_text.config(state=DISABLED)

        self.code_text.config(state=NORMAL)
        self.code_text.delete("1.0", END)
        if generated_code:
            self.code_text.insert(END, generated_code)
        else:
            self.code_text.insert(END, "Generated code not found for this run.")
        self.code_text.config(state=DISABLED)
    
    def _clear_results(self):
        """Clear all results and logs"""
        self.result_status_label.config(text="No run yet")
        self.last_results = None

        self.summary_text.config(state=NORMAL)
        self.summary_text.delete("1.0", END)
        self.summary_text.config(state=DISABLED)

        self.report_text.config(state=NORMAL)
        self.report_text.delete("1.0", END)
        self.report_text.config(state=DISABLED)

        self.code_text.config(state=NORMAL)
        self.code_text.delete("1.0", END)
        self.code_text.config(state=DISABLED)
        
        self.logs_text.config(state=NORMAL)
        self.logs_text.delete("1.0", END)
        self.logs_text.config(state=DISABLED)
    
    def _refresh_history(self):
        """Refresh the history panel with recent runs"""
        run_dirs = self._get_run_dirs()
        self.run_dir_map = {run_dir.name: run_dir for run_dir in run_dirs}
        run_names = list(self.run_dir_map.keys())
        self.history_run_combo["values"] = run_names

        if run_names:
            self.history_run_combo.set(run_names[0])
            self._update_history_attempts()
        else:
            self.history_run_combo.set("")
            self.history_attempt_combo["values"] = []
            self.history_attempt_combo.set("")
            self._set_history_report_text("No runs found yet. Generate some code to see results here!")
            self._set_history_code_text("")

    def _on_history_run_selected(self, _event=None):
        self._update_history_attempts()

    def _on_history_type_selected(self, _event=None):
        self._update_history_attempts()

    def _update_history_attempts(self):
        run_name = self.history_run_var.get()
        run_dir = self.run_dir_map.get(run_name)
        selected_type = self.history_type_var.get() or "passed"
        self.history_attempt_map = {}

        if run_dir is None:
            self.history_attempt_combo["values"] = []
            self.history_attempt_combo.set("")
            self._set_history_report_text("Select a run to view results.")
            self._set_history_code_text("")
            return

        target_dir = run_dir / selected_type
        if not target_dir.exists():
            self.history_attempt_combo["values"] = []
            self.history_attempt_combo.set("")
            self._set_history_report_text(f"No {selected_type} attempts in this run.")
            self._set_history_code_text("")
            return

        json_files = sorted(target_dir.glob("*.json"), reverse=True)
        display_values = []
        for json_file in json_files:
            py_file = json_file.with_suffix(".py")
            display_name = json_file.stem
            self.history_attempt_map[display_name] = {"json": json_file, "py": py_file}
            display_values.append(display_name)

        self.history_attempt_combo["values"] = display_values
        if display_values:
            self.history_attempt_combo.set(display_values[0])
            self._open_selected_attempt()
        else:
            self.history_attempt_combo.set("")
            self._set_history_report_text(f"No {selected_type} attempts in this run.")
            self._set_history_code_text("")

    def _open_selected_attempt(self):
        attempt_key = self.history_attempt_var.get()
        attempt = self.history_attempt_map.get(attempt_key)
        if attempt is None:
            self._set_history_report_text("Select an attempt to view report and code.")
            self._set_history_code_text("")
            return

        json_file = attempt["json"]
        py_file = attempt["py"]

        try:
            report = json.loads(json_file.read_text(encoding="utf-8"))
            self._set_history_report_text(json.dumps(report, indent=2))
        except Exception as exc:  # noqa: BLE001
            self._set_history_report_text(f"Failed to load report {json_file.name}: {exc}")

        if py_file.exists():
            try:
                self._set_history_code_text(py_file.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                self._set_history_code_text(f"Failed to load code {py_file.name}: {exc}")
        else:
            self._set_history_code_text("Code file not found for this attempt.")

    def _set_history_report_text(self, value):
        self.history_report_text.config(state=NORMAL)
        self.history_report_text.delete("1.0", END)
        self.history_report_text.insert(END, value)
        self.history_report_text.config(state=DISABLED)

    def _set_history_code_text(self, value):
        self.history_code_text.config(state=NORMAL)
        self.history_code_text.delete("1.0", END)
        self.history_code_text.insert(END, value)
        self.history_code_text.config(state=DISABLED)

    def _get_run_dirs(self):
        if not self.exec_code_dir.exists():
            return []
        return sorted(
            [d for d in self.exec_code_dir.iterdir() if d.is_dir() and d.name.startswith("run_")],
            reverse=True,
            key=lambda x: x.name,
        )

    def _get_latest_run_dir(self):
        run_dirs = self._get_run_dirs()
        return run_dirs[0] if run_dirs else None

    def _get_latest_attempt_context(self, run_dir):
        if run_dir is None:
            return None
        for bucket in ["passed", "failed"]:
            bucket_dir = run_dir / bucket
            if not bucket_dir.exists():
                continue
            json_files = sorted(bucket_dir.glob("*.json"), reverse=True)
            if not json_files:
                continue
            latest_json = json_files[0]
            latest_py = latest_json.with_suffix(".py")
            try:
                report = json.loads(latest_json.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                report = None
            try:
                code = latest_py.read_text(encoding="utf-8") if latest_py.exists() else ""
            except Exception:  # noqa: BLE001
                code = ""
            return {
                "bucket": bucket,
                "report": report,
                "code": code,
                "json_path": latest_json,
                "py_path": latest_py,
            }
        return None

    def _extract_json_from_output(self, output_text):
        decoder = json.JSONDecoder()
        for idx, char in enumerate(output_text):
            if char != "{":
                continue
            try:
                parsed, _end = decoder.raw_decode(output_text[idx:])
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
        return None

    def _save_current_code(self):
        if not self.last_results or not self.last_results.get("generated_code"):
            messagebox.showinfo("No Code", "No generated code is available to save.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")],
            initialfile="generated_code.py",
            title="Save generated code",
        )
        if not file_path:
            return

        try:
            Path(file_path).write_text(self.last_results["generated_code"], encoding="utf-8")
            messagebox.showinfo("Saved", f"Code saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Save Failed", str(exc))
    
    def _update_ui_state(self, state):
        """Enable or disable UI controls"""
        self.run_button.config(state=state)
        self.clear_button.config(state=state if not self.is_running else DISABLED)
        self.provider_var.config(state=state if state == NORMAL else "readonly")
        self.model_id_var.config(state=state)
        self.region_var.config(state=state)
        self.api_key_var.config(state=state)
        self.fail_below_var.config(state=state)
        self.max_regen_var.config(state=state)
        self.history_run_combo.config(state=state if state == NORMAL else "readonly")
        self.history_type_combo.config(state=state if state == NORMAL else "readonly")
        self.history_attempt_combo.config(state=state if state == NORMAL else "readonly")


def main():
    root = Tk()
    app = PipelineUI(root)
    app._refresh_history()  # Load initial history
    root.mainloop()


if __name__ == "__main__":
    main()
