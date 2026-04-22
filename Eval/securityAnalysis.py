import subprocess
import json
import shutil
import tempfile
import os
import sys

class Security:
    """
    Class to perform security analysis using various tools.
    The class accepts a string code from AI to check for security issues and vulnerabilities.
    The class will use tools like Bandit, Semgrep, and OWASP Dependency-Check to perform the analysis.
    The results will be returned in a structured format indicating any issues found and their severity.
    The class can be extended to include additional security tools and checks as needed.
    """
    def __init__(self, code):
        self.code = code
        self.issues = []
        self.warnings = []
        self.findings = []

    def analyze(self, file_path=None):
        if not file_path:
            return {
                "issues": self.issues,
                "warnings": self.warnings,
                "findings": self.findings,
                "tool_status": {"bandit": "skipped", "semgrep": "skipped", "owasp": "skipped"},
            }

        self.__run_bandit(file_path)
        self.__run_semgrep(file_path)
        self.__run_OWASP_dependency_check(file_path)
        return {
            "issues": self.issues,
            "warnings": self.warnings,
            "findings": self.findings,
            "tool_status": {
                "bandit": self._tool_status("bandit"),
                "semgrep": self._tool_status("semgrep"),
                "owasp": self._tool_status("owasp"),
            },
        }

    def _tool_status(self, tool_name):
        prefix = f"{tool_name}:"
        for entry in reversed(self.warnings + self.issues):
            if isinstance(entry, str) and entry.lower().startswith(prefix):
                return entry.split(":", 1)[1].strip()
        return "ok"

    def __ensure_executable(self, path):
        """Ensure a file has execute permissions on Unix-like systems."""
        if sys.platform != "win32" and os.path.exists(path):
            try:
                # Check if file already has execute permissions
                current_permissions = os.stat(path).st_mode
                if not (current_permissions & 0o111):  # Check if any execute bit is set
                    # Grant execute permissions (add 755 permissions)
                    os.chmod(path, current_permissions | 0o111)
            except (OSError, PermissionError) as e:
                # Log but don't fail if we can't set permissions
                pass

    def __check_java_available(self):
        """Check if Java is installed and available."""
        # Check JAVA_HOME environment variable
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            java_path = os.path.join(java_home, "bin", "java")
            if os.path.exists(java_path):
                return True

        # Check if java is in PATH
        if shutil.which("java"):
            return True

        return False

    def __get_dependency_check_tool(self):
        """Detect and return the OWASP Dependency-Check executable for the current platform."""
        # Try to find dependency-check in PATH first
        if shutil.which("dependency-check"):
            return "dependency-check"

        # Get the directory where this script is located
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Check local installation based on OS
        if sys.platform == "win32":
            local_paths = [
                os.path.join(script_dir, "dependency-check", "bin", "dependency-check.bat"),
            ]
        else:  # Linux, macOS, etc.
            local_paths = [
                os.path.join(script_dir, "dependency-check", "bin", "dependency-check.sh"),
                os.path.join(script_dir, "dependency-check", "bin", "dependency-check"),
            ]

        for path in local_paths:
            if os.path.exists(path):
                # Ensure execute permissions on Unix-like systems
                self.__ensure_executable(path)
                return path

        return None


    def __run_bandit(self, file_path):
        # Bandit analysis logic
        if shutil.which("bandit") is None:
            self.warnings.append("bandit: Bandit is not installed; skipping Bandit scan.")
            return

        try:
            result = subprocess.run(["bandit", "-r", file_path, "-f", "json"], capture_output=True, text=True)
        except FileNotFoundError:
            self.warnings.append("bandit: Bandit is not installed; skipping Bandit scan.")
            return

        # Bandit commonly returns 1 when issues are found; parse report for 0/1.
        if result.returncode not in (0, 1):
            stderr_text = (result.stderr or "").strip()
            self.issues.append(f"bandit: Bandit analysis failed: {stderr_text or 'unknown error'}")
            return

        try:
            bandit_report = json.loads(result.stdout)
            for issue in bandit_report.get("results", []):
                severity = issue.get("issue_severity", "LOW")
                finding = {
                    "source": "bandit",
                    "severity": severity,
                    "message": issue.get("issue_text", "Bandit finding detected."),
                    "test_id": issue.get("test_id"),
                    "line_number": issue.get("line_number"),
                    "confidence_hint": issue.get("issue_confidence", "MEDIUM"),
                }
                self.findings.append(finding)
                if severity in ["HIGH", "MEDIUM"]:
                    self.issues.append(f"bandit: Bandit {severity} issue: {issue.get('issue_text')}")
                else:
                    self.warnings.append(f"bandit: Bandit {severity} warning: {issue.get('issue_text')}")
        except json.JSONDecodeError:
            self.issues.append("bandit: Failed to parse Bandit output as JSON.")
        

    def __run_semgrep(self, file_path):
        # Semgrep analysis logic
        if shutil.which("semgrep") is None:
            self.warnings.append("semgrep: Semgrep is not installed; skipping Semgrep scan.")
            return

        try:
            result = subprocess.run(["semgrep", "--config", "p/ci", file_path, "--json"], capture_output=True, text=True)
        except FileNotFoundError:
            self.warnings.append("semgrep: Semgrep is not installed; skipping Semgrep scan.")
            return

        # Semgrep can return 1 when findings are present; parse report for 0/1.
        if result.returncode not in (0, 1):
            stderr_text = (result.stderr or "").strip()
            self.issues.append(f"semgrep: Semgrep analysis failed: {stderr_text or 'unknown error'}")
            return
        
        try:
            semgrep_report = json.loads(result.stdout)
            for finding in semgrep_report.get("results", []):
                severity = finding.get("extra", {}).get("severity", "INFO")
                finding_record = {
                    "source": "semgrep",
                    "severity": severity,
                    "message": finding.get("extra", {}).get("message", "Semgrep finding detected."),
                    "check_id": finding.get("check_id"),
                    "path": finding.get("path"),
                    "line": finding.get("start", {}).get("line"),
                    "confidence_hint": severity,
                }
                self.findings.append(finding_record)
                if severity in ["ERROR", "WARNING"]:
                    self.issues.append(f"semgrep: Semgrep {severity} issue: {finding.get('extra', {}).get('message')}")
                else:
                    self.warnings.append(f"semgrep: Semgrep {severity} warning: {finding.get('extra', {}).get('message')}")
        except json.JSONDecodeError:
            self.issues.append("semgrep: Failed to parse Semgrep output as JSON.")
        
    def __find_dependencies(self, file_path):
        directory = os.path.dirname(file_path)

        dependencies = [
            "requirements.txt",
            "Pipfile.lock",
            "poetry.lock",
            "pyproject.toml",
            "setup.py",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "pom.xml",
            "build.gradle",
            "build.gradle.kts",
            "go.mod",
            "Cargo.lock",
            "Gemfile.lock",
        ]

        for d in dependencies:
            dep_path = os.path.join(directory, d)
            if os.path.exists(dep_path):
                return dep_path
        print(file_path)
        # No manifest available: scan the generated file directly.
        return file_path

    def __run_OWASP_dependency_check(self, file_path):
        """Run OWASP Dependency-Check analysis with cross-platform support."""
        tool = self.__get_dependency_check_tool()

        if tool is None:
            self.warnings.append("owasp: OWASP Dependency-Check is not installed; skipping scan.")
            return

        if not self.__check_java_available():
            self.warnings.append("owasp: Java is not installed or JAVA_HOME is not set; skipping scan. Please install Java to enable OWASP Dependency-Check.")
            return

        target = self.__find_dependencies(file_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                result = subprocess.run(
                    [
                        tool,
                        "--project",
                        "SecurityAnalysis",
                        "--scan",
                        target,
                        "--format",
                        "JSON",
                        "--out",
                        temp_dir,
                        "--noupdate",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (FileNotFoundError, PermissionError) as e:
                if isinstance(e, PermissionError):
                    self.issues.append(f"owasp: OWASP Dependency-Check permission denied. Please ensure execute permissions are set.")
                else:
                    self.warnings.append("owasp: OWASP Dependency-Check is not installed; skipping scan.")
                return
            except subprocess.TimeoutExpired:
                self.issues.append("owasp: OWASP Dependency-Check analysis timed out.")
                return

            if result.returncode != 0:
                stderr_text = (result.stderr or "").strip()
                self.issues.append(f"owasp: OWASP Dependency-Check analysis failed: {stderr_text or 'unknown error'}")
                return

            report_path = os.path.join(temp_dir, "dependency-check-report.json")
            if os.path.exists(report_path):
                try:
                    with open(report_path, 'r') as f:
                        dependency_report = json.load(f)
                        for dependency in dependency_report.get("dependencies", []):
                            for vulnerability in dependency.get("vulnerabilities", []):
                                severity = vulnerability.get("severity", "LOW")
                                description = vulnerability.get("description", "OWASP finding detected.")
                                vuln_name = vulnerability.get("name") or vulnerability.get("vulnId") or "Unknown vulnerability"

                                # Add to findings list for risk scoring
                                finding = {
                                    "source": "owasp",
                                    "severity": severity,
                                    "message": description,
                                    "vuln_id": vuln_name,
                                    "dependency": dependency.get("fileName"),
                                    "confidence_hint": severity,
                                }
                                self.findings.append(finding)

                                # Add to issues/warnings for summary
                                if severity in ["HIGH", "MEDIUM", "CRITICAL"]:
                                    self.issues.append(f"owasp: OWASP {severity} issue: {vuln_name}")
                                else:
                                    self.warnings.append(f"owasp: OWASP {severity} warning: {vuln_name}")
                except json.JSONDecodeError:
                    self.issues.append("owasp: Failed to parse OWASP Dependency-Check output as JSON.")
            else:
                self.issues.append("owasp: OWASP Dependency-Check report not found.")
