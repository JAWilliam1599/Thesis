import subprocess
import json
import shutil

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

    def analyze(self, file_path=None):
        if not file_path:
            return

        self.__run_bandit(file_path)
        self.__run_semgrep(file_path)
        self.__run_OWASP_dependency_check(file_path)
        return {
            "issues": self.issues,
            "warnings": self.warnings,
        }


    def __run_bandit(self, file_path):
        # Bandit analysis logic
        if shutil.which("bandit") is None:
            self.warnings.append("Bandit is not installed; skipping Bandit scan.")
            return

        try:
            result = subprocess.run(["bandit", "-r", file_path, "-f", "json"], capture_output=True, text=True)
        except FileNotFoundError:
            self.warnings.append("Bandit is not installed; skipping Bandit scan.")
            return

        # Bandit commonly returns 1 when issues are found; parse report for 0/1.
        if result.returncode not in (0, 1):
            stderr_text = (result.stderr or "").strip()
            self.issues.append(f"Bandit analysis failed: {stderr_text or 'unknown error'}")
            return

        try:
            bandit_report = json.loads(result.stdout)
            for issue in bandit_report.get("results", []):
                severity = issue.get("issue_severity", "LOW")
                if severity in ["HIGH", "MEDIUM"]:
                    self.issues.append(f"Bandit {severity} issue: {issue.get('issue_text')}")
                else:
                    self.warnings.append(f"Bandit {severity} warning: {issue.get('issue_text')}")
        except json.JSONDecodeError:
            self.issues.append("Failed to parse Bandit output as JSON.")
        

    def __run_semgrep(self, file_path):
        # Semgrep analysis logic
        if shutil.which("semgrep") is None:
            self.warnings.append("Semgrep is not installed; skipping Semgrep scan.")
            return

        try:
            result = subprocess.run(["semgrep", "--config", "p/ci", file_path, "--json"], capture_output=True, text=True)
        except FileNotFoundError:
            self.warnings.append("Semgrep is not installed; skipping Semgrep scan.")
            return

        # Semgrep can return 1 when findings are present; parse report for 0/1.
        if result.returncode not in (0, 1):
            stderr_text = (result.stderr or "").strip()
            self.issues.append(f"Semgrep analysis failed: {stderr_text or 'unknown error'}")
            return
        
        try:
            semgrep_report = json.loads(result.stdout)
            for finding in semgrep_report.get("results", []):
                severity = finding.get("extra", {}).get("severity", "INFO")
                if severity in ["ERROR", "WARNING"]:
                    self.issues.append(f"Semgrep {severity} issue: {finding.get('extra', {}).get('message')}")
                else:
                    self.warnings.append(f"Semgrep {severity} warning: {finding.get('extra', {}).get('message')}")
        except json.JSONDecodeError:
            self.issues.append("Failed to parse Semgrep output as JSON.")
        

    def __run_OWASP_dependency_check(self, file_path):
        # Placeholder for OWASP Dependency-Check analysis logic
        pass

    