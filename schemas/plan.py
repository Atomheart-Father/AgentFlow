"""
Plan结构验证和定义
使用Pydantic进行JSON Schema校验
"""
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, validator
from enum import Enum


class StepType(str, Enum):
    """步骤类型枚举"""
    TOOL_CALL = "tool_call"
    READ = "read"
    SUMMARIZE = "summarize"
    ASK_USER = "ask_user"
    PROCESS = "process"  # LLM推理处理步骤
    REASONING = "reasoning"  # 推理步骤
    RESPONSE_GENERATION = "response_generation"  # 响应生成步骤
    OUTPUT = "output"  # 输出步骤


class PlanStep(BaseModel):
    """计划步骤模型"""
    id: str = Field(..., description="步骤唯一标识符")
    type: StepType = Field(..., description="步骤类型")
    tool: Optional[str] = Field(None, description="工具名称（当type=tool_call时必填）")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="输入参数")
    depends_on: List[str] = Field(default_factory=list, description="依赖的步骤ID列表")
    expect: str = Field(..., description="此步骤应产出的证据预期")
    output_key: str = Field(..., description="输出结果的键名")
    retry: int = Field(1, ge=0, le=3, description="重试次数（0-3次）")

    @validator('tool')
    def validate_tool_requirement(cls, v, values):
        """验证工具字段"""
        if values.get('type') == StepType.TOOL_CALL and not v:
            raise ValueError("当type为tool_call时，tool字段为必填项")
        return v


class Plan(BaseModel):
    """完整计划模型"""
    goal: str = Field(..., description="总体目标描述")
    success_criteria: List[str] = Field(..., min_items=1, description="成功标准列表")
    max_steps: int = Field(6, ge=1, le=10, description="最大步骤数")
    steps: List[PlanStep] = Field(..., min_items=1, description="步骤列表")
    final_answer_template: str = Field(..., description="最终答案模板")

    @validator('steps')
    def validate_step_dependencies(cls, v):
        """验证步骤依赖关系"""
        step_ids = {step.id for step in v}

        for step in v:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ValueError(f"步骤 {step.id} 依赖的步骤 {dep} 不存在")

        return v

    @validator('steps')
    def validate_max_steps(cls, v, values):
        """验证步骤数量不超过最大限制"""
        max_steps = values.get('max_steps', 6)
        if len(v) > max_steps:
            raise ValueError(f"步骤数量 {len(v)} 超过最大限制 {max_steps}")
        return v


class PlanValidationError(Exception):
    """计划验证错误"""
    pass


def validate_plan(plan_data: Union[Dict[str, Any], str]) -> Plan:
    """
    验证和解析计划数据

    Args:
        plan_data: 计划数据（字典或JSON字符串）

    Returns:
        Plan: 验证后的Plan对象

    Raises:
        PlanValidationError: 验证失败时抛出
    """
    try:
        if isinstance(plan_data, str):
            import json
            plan_dict = json.loads(plan_data)
        else:
            plan_dict = plan_data

        return Plan(**plan_dict)

    except Exception as e:
        raise PlanValidationError(f"计划验证失败: {str(e)}")


def create_sample_plan() -> Plan:
    """创建示例计划"""
    return Plan(
        goal="回答用户关于当前时间的问题",
        success_criteria=[
            "获取到准确的当前时间",
            "时间格式正确且易读"
        ],
        max_steps=3,
        steps=[
            PlanStep(
                id="s1",
                type=StepType.TOOL_CALL,
                tool="time_now",
                inputs={},
                depends_on=[],
                expect="获取当前时间的完整信息",
                output_key="current_time",
                retry=1
            ),
            PlanStep(
                id="s2",
                type=StepType.SUMMARIZE,
                inputs={"data": "{{current_time}}"},
                depends_on=["s1"],
                expect="将时间信息格式化为易读的回答",
                output_key="formatted_time",
                retry=0
            )
        ],
        final_answer_template="现在时间是：{{formatted_time}}"
    )


if __name__ == "__main__":
    # 测试示例
    sample_plan = create_sample_plan()
    print("示例计划创建成功:")
    print(f"目标: {sample_plan.goal}")
    print(f"步骤数量: {len(sample_plan.steps)}")
    print(f"成功标准: {sample_plan.success_criteria}")

    # 测试验证
    try:
        validated_plan = validate_plan(sample_plan.dict())
        print("✅ 计划验证通过")
    except PlanValidationError as e:
        print(f"❌ 计划验证失败: {e}")
