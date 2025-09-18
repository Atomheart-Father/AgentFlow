"""
数学计算工具 - 安全执行数学表达式
"""

import ast
import operator
import math
from typing import Dict, Any, Union


class ToolMath:
    """数学计算工具"""

    def __init__(self):
        self.name = "math.calc"
        self.description = "执行安全的数学计算表达式，支持基本运算、函数和常量"
        self.parameters = {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，例如: '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)'"
                }
            },
            "required": ["expression"]
        }

        # 允许的运算符
        self.allowed_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.USub: operator.neg,
            ast.UAdd: operator.pos,
        }

        # 允许的函数
        self.allowed_functions = {
            'sin': math.sin,
            'cos': math.cos,
            'tan': math.tan,
            'sqrt': math.sqrt,
            'log': math.log,
            'exp': math.exp,
            'abs': abs,
            'round': round,
            'max': max,
            'min': min,
        }

        # 允许的常量
        self.allowed_constants = {
            'pi': math.pi,
            'e': math.e,
        }

    def _safe_eval(self, node: ast.AST) -> Union[int, float]:
        """
        安全评估AST节点

        Args:
            node: AST节点

        Returns:
            计算结果

        Raises:
            ValueError: 不安全的表达式
        """
        if isinstance(node, ast.Constant):
            # 常量
            if isinstance(node.value, (int, float)):
                return node.value
            else:
                raise ValueError(f"不支持的常量类型: {type(node.value)}")

        elif isinstance(node, ast.Name):
            # 变量名
            if node.id in self.allowed_constants:
                return self.allowed_constants[node.id]
            elif node.id in self.allowed_functions:
                return self.allowed_functions[node.id]
            else:
                raise ValueError(f"未定义的标识符: {node.id}")

        elif isinstance(node, ast.BinOp):
            # 二元运算
            left = self._safe_eval(node.left)
            right = self._safe_eval(node.right)
            op_type = type(node.op)

            if op_type in self.allowed_operators:
                op_func = self.allowed_operators[op_type]
                try:
                    return op_func(left, right)
                except ZeroDivisionError:
                    raise ValueError("除零错误")
            else:
                raise ValueError(f"不支持的运算符: {op_type}")

        elif isinstance(node, ast.UnaryOp):
            # 一元运算
            operand = self._safe_eval(node.operand)
            op_type = type(node.op)

            if op_type in self.allowed_operators:
                op_func = self.allowed_operators[op_type]
                return op_func(operand)
            else:
                raise ValueError(f"不支持的一元运算符: {op_type}")

        elif isinstance(node, ast.Call):
            # 函数调用
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name in self.allowed_functions:
                    func = self.allowed_functions[func_name]
                    args = [self._safe_eval(arg) for arg in node.args]
                    return func(*args)
                else:
                    raise ValueError(f"不支持的函数: {func_name}")
            else:
                raise ValueError("复杂的函数调用不支持")

        else:
            raise ValueError(f"不支持的表达式类型: {type(node)}")

    def run(self, expression: str, **kwargs) -> Dict[str, Any]:
        """
        执行数学表达式

        Args:
            expression: 数学表达式字符串
            **kwargs: 其他参数（忽略）

        Returns:
            计算结果
        """
        try:
            # 解析表达式
            tree = ast.parse(expression, mode='eval')
            result = self._safe_eval(tree.body)

            return {
                "expression": expression,
                "result": result,
                "type": type(result).__name__
            }

        except SyntaxError as e:
            raise ValueError(f"表达式语法错误: {e}")
        except ValueError as e:
            raise ValueError(f"计算错误: {e}")
        except Exception as e:
            raise ValueError(f"未知错误: {e}")
