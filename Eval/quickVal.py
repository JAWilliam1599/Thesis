import ast


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
        self.findings = []
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
            "findings": self.findings,
            "issues": self.issues,
            "approval": not any(
                finding.get("severity") in {"high", "critical"} for finding in self.findings
            ),
        }

    def _add_finding(self, severity, message):
        self.findings.append(
            {
                "source": "quickval",
                "severity": severity,
                "message": message,
            }
        )
        self.issues.append(message)

    def _self_review(self):
        if self.model is None or not hasattr(self.model, "review"):
            return

        # Let the model review its own code
        review = self.model.review(self.code)

        if review.get("risk_score", 0) > 5:
            self._add_finding("medium", "Model self-review points out high risk.")

    def _syntax_check(self):
        try:
            compile(self.code, "<string>", "exec")
        except SyntaxError as e:
            self._add_finding("high", f"Syntax error: {e}")

    def _check_forbiden_imports(self):
        for imp in self.FORBIDENT_IMPORTS:
            if f"import {imp}" in self.code or f"from {imp}" in self.code:
                self._add_finding("high", f"Forbiden import detected: {imp}")

    def _check_forbiden_functions(self):
        try:
            tree = ast.parse(self.code)
        except SyntaxError:
            # Syntax is already handled in _syntax_check; skip call analysis here.
            return

        called_functions = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                called_name = self._get_called_function_name(node.func)
                if called_name:
                    called_functions.add(called_name)

        for func in self.FORBIDENT_FUNCTIONS:
            if func in called_functions:
                self._add_finding("high", f"Forbiden function detected: {func}")

    def _get_called_function_name(self, node):
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Attribute):
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
                return ".".join(reversed(parts))

        return None

    def _check_complexity(self):
        try:
            tree = ast.parse(self.code)
        except SyntaxError:
            # Syntax is already handled in _syntax_check.
            return

        max_loop_depth = self._get_max_loop_depth(tree)
        if max_loop_depth > 2:
            self._add_finding(
                "low",
                f"Complexity risk detected: nested loop depth is {max_loop_depth}. "
                "Expected complexity should not exceed O(n^2)."
            )

    def _get_max_loop_depth(self, tree):
        max_depth = 0

        def walk(node, current_depth):
            nonlocal max_depth

            is_loop = isinstance(node, (ast.For, ast.While, ast.AsyncFor))
            next_depth = current_depth + 1 if is_loop else current_depth
            if next_depth > max_depth:
                max_depth = next_depth

            for child in ast.iter_child_nodes(node):
                walk(child, next_depth)

        walk(tree, 0)
        return max_depth