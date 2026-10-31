import ast
import operator


class Calculator:
    operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}

    def calculate(self, expression: str) -> str:
        answers = []
        for line in expression.splitlines()[:10]:
            text = line.strip().replace(",", "")
            if not text:
                continue
            try:
                answers.append(f"{text} = {self._evaluate(ast.parse(text, mode='eval').body):,.2f}")
            except (SyntaxError, ValueError, TypeError, ArithmeticError):
                answers.append(f"{text} = could not be evaluated")
        return "; ".join(answers) or "No arithmetic expression was supplied; no calculation was performed."

    def _evaluate(self, node: ast.AST) -> float:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in self.operators:
            left, right = self._evaluate(node.left), self._evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("Exponent is too large")
            result = self.operators[type(node.op)](left, right)
            if isinstance(result, complex) or abs(result) > 1e15:
                raise ValueError("Calculation exceeds the supported range")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in self.operators:
            return self.operators[type(node.op)](self._evaluate(node.operand))
        raise ValueError("Unsupported calculation expression")
