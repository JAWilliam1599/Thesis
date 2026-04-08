# This is where code will put in a quick validation

class QuickVal:
    # This class will accept code only for quick validation

    # Some forbiden imports
    FORBIDENT_IMPORTS = [
        "os",
        "sys",
        "subprocess",
        "socket",
        "shutil",
    ]

    # Some forbiden functions
    FORBIDENT_FUNCTIONS = [
        "eval",
        "exec",
        "open",
        "input",
        "compile",
        "__import__",
        "os.system",
    ]



    def __init__(self, model, code):
        self.model = model
        self.code = code
        self.risk_score = 0
        self.issues = []

    def validate(self):
        # Validation logic
        # Let the model review itself
        self._self_review()

        # Check for syntax errors
        self._syntax_check()

        # Check for forbiden imports
        self._check_forbiden_imports()

        # Check for forbiden functions
        self._check_forbiden_functions()

        # Check for complexity like loops and recursion
        self._check_complexity()

        return {
            "risk_score": self.risk_score,
            "issues": self.issues,
            "approval": self.risk_score < 5,  # Approve if risk score is less than 5
        }

    def _self_review(self):
        if self.model is None or not hasattr(self.model, "review"):
            return

        # Let the model review its own code
        review = self.model.review(self.code)

        if review.get("risk_score", 0) > 5:
            self.risk_score += 2
            self.issues.append("Model self-review points out high risk.")

    def _syntax_check(self):
        try:
            compile(self.code, "<string>", "exec")
        except SyntaxError as e:
            self.risk_score += 5
            self.issues.append(f"Syntax error: {e}")

    def _check_forbiden_imports(self):
        for imp in self.FORBIDENT_IMPORTS:
            if f"import {imp}" in self.code or f"from {imp}" in self.code:
                self.risk_score += 3
                self.issues.append(f"Forbiden import detected: {imp}")

    def _check_forbiden_functions(self):
        for func in self.FORBIDENT_FUNCTIONS:
            if func in self.code:
                self.risk_score += 3
                self.issues.append(f"Forbiden function detected: {func}")

    def _check_complexity(self):
        # Simple check for loops and recursion
        loop_count = self.code.count("for ") + self.code.count("while ")

        if loop_count > 5:
            self.risk_score += 2
            self.issues.append("Loop detected.")