"""
Orchestrator相关的Pydantic模型定义
用于验证Planner和Judge的JSON输出
"""

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, validator
from enum import Enum


class StepType(str, Enum):
    """步骤类型枚举"""
    TOOL_CALL = "tool_call"
    WEB_SEARCH = "web_search"  # 网络搜索步骤
    SUMMARIZE = "summarize"
    WRITE_FILE = "write_file"
    ASK_USER = "ask_user"


class PlanStep(BaseModel):
    """计划步骤模型"""
    id: str = Field(..., description="步骤唯一标识")
    type: StepType = Field(..., description="步骤类型")
    tool: Optional[str] = Field(None, description="工具名称（当type为tool_call时必填）")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="步骤输入参数")
    depends_on: List[str] = Field(default_factory=list, description="依赖的步骤ID列表")
    expect: str = Field(..., description="期望的证据或结果描述")
    output_key: str = Field(..., description="输出结果的键名")
    retry: int = Field(0, ge=0, le=1, description="重试次数（0或1）")


class PlannerOutput(BaseModel):
    """Planner输出模型"""
    goal: str = Field(..., description="任务目标")
    success_criteria: List[str] = Field(..., min_items=1, description="成功标准列表")
    max_steps: int = Field(..., gt=0, le=10, description="最大步骤数")
    steps: List[PlanStep] = Field(..., min_items=1, description="执行步骤列表")
    final_answer_template: str = Field(..., description="最终答案模板")

    @validator('steps')
    def validate_steps(cls, v):
        """验证步骤的依赖关系"""
        step_ids = {step.id for step in v}
        for step in v:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ValueError(f"步骤 {step.id} 依赖不存在的步骤 {dep}")
        return v


class JudgeOutput(BaseModel):
    """Judge输出模型"""
    satisfied: bool = Field(..., description="是否满足成功标准")
    missing: List[str] = Field(default_factory=list, description="缺失的信息或证据")
    plan_patch: Optional[Dict[str, Any]] = Field(None, description="计划补丁（当satisfied=false时可选）")
    questions: Optional[List[str]] = Field(None, description="需要询问用户的问题列表（最多2个）")

    @validator('questions')
    def validate_questions(cls, v):
        """验证问题数量不超过2个"""
        if v is not None and len(v) > 2:
            raise ValueError("问题数量不能超过2个")
        return v

    @validator('missing', 'questions')
    def validate_conditional_fields(cls, v, values):
        """当satisfied=false时，至少要有missing或questions之一"""
        if not values.get('satisfied', True):
            if not v and not values.get('questions'):
                raise ValueError("当satisfied=false时，必须提供missing或questions")
        return v


def validate_planner_output(json_str: str) -> PlannerOutput:
    """
    验证Planner的JSON输出

    Args:
        json_str: JSON字符串

    Returns:
        验证后的PlannerOutput对象

    Raises:
        ValueError: JSON格式错误或验证失败
    """
    import json
    try:
        data = json.loads(json_str)
        return PlannerOutput(**data)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {e}")
    except Exception as e:
        raise ValueError(f"Planner输出验证失败: {e}")


def validate_judge_output(json_str: str) -> JudgeOutput:
    """
    验证Judge的JSON输出

    Args:
        json_str: JSON字符串

    Returns:
        验证后的JudgeOutput对象

    Raises:
        ValueError: JSON格式错误或验证失败
    """
    import json
    try:
        data = json.loads(json_str)
        return JudgeOutput(**data)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON解析失败: {e}")
    except Exception as e:
        raise ValueError(f"Judge输出验证失败: {e}")


# 为了向后兼容，提供别名
Plan = PlannerOutput
JudgeVerdict = JudgeOutput
