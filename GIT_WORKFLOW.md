# Git 工作流程指南

## 🎯 目标
通过分支保护和PR流程确保代码质量，保护主分支的稳定性。

## 📋 工作流程

### 1. 创建功能分支
```bash
# 从main分支创建新分支
git checkout main
git pull origin main

# 创建功能分支
git checkout -b feature/your-feature-name
# 或修复分支
git checkout -b fix/your-bug-name
```

### 2. 开发过程
```bash
# 定期提交小变更
git add .
git commit -m "feat: 实现XXX功能

- 详细说明做了什么
- 为什么这么做
- 有什么影响"

# 保持分支与main同步
git fetch origin
git rebase origin/main
```

### 3. 提交前检查
```bash
# 运行测试
python -m pytest tests/ -v

# 检查代码格式
black --check .
isort --check-only .

# 检查是否包含模拟代码
grep -r "模拟\|mock\|fake" --exclude-dir=.git .
```

### 4. 创建Pull Request
```bash
# 推送分支到远程
git push -u origin feature/your-feature-name

# 在GitHub上创建PR
# 访问: https://github.com/Atomheart-Father/AgentFlow/pull/new/feature/your-feature-name
```

### 5. PR 审查流程
- **自动检查**: CI会运行代码检查、测试、安全扫描
- **人工审查**: 至少一人审查代码
- **测试验证**: 确保功能正常工作
- **合并**: 审查通过后合并到main

## 🔧 分支命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 功能 | `feature/description` | `feature/m3-orchestrator` |
| 修复 | `fix/description` | `fix/gradio-timeout` |
| 文档 | `docs/description` | `docs/api-reference` |
| 重构 | `refactor/description` | `refactor/agent-core` |

## ✅ 提交信息规范

```
type: 简短描述

详细说明做了什么，为什么这么做
- 具体变更点1
- 具体变更点2
- 相关问题链接

Fixes #123
```

### 提交类型
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档变更
- `style`: 代码格式调整
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建工具配置等

## 🚫 禁止操作

### 不要直接推送到main
```bash
# ❌ 错误
git add .
git commit -m "update"
git push origin main

# ✅ 正确
git checkout -b feature/some-update
git add .
git commit -m "feat: some update"
git push origin feature/some-update
# 然后创建PR
```

### 不要强制推送
```bash
# ❌ 避免使用 --force
git push --force origin main

# ✅ 使用 --force-with-lease (更安全)
git push --force-with-lease origin feature/branch
```

## 🔍 代码审查清单

### 功能完整性
- [ ] 功能按需求实现
- [ ] 边界情况处理
- [ ] 错误处理完善
- [ ] 测试覆盖充分

### 代码质量
- [ ] 代码格式符合规范
- [ ] 变量命名清晰
- [ ] 函数职责单一
- [ ] 注释准确必要

### 安全检查
- [ ] 无敏感信息泄露
- [ ] 输入验证完善
- [ ] SQL注入防护
- [ ] XSS防护措施

### 性能考虑
- [ ] 无明显性能问题
- [ ] 资源使用合理
- [ ] 异步处理正确

## 🛠️ 常用Git命令

```bash
# 查看状态
git status
git log --oneline -10

# 分支管理
git branch -a                    # 查看所有分支
git checkout -b new-branch      # 创建并切换分支
git branch -d branch-name       # 删除本地分支

# 同步代码
git fetch origin                # 拉取远程更新
git pull origin main           # 拉取并合并main
git rebase origin/main         # 变基到main

# 撤销操作
git reset --soft HEAD~1        # 撤销提交，保留更改
git reset --hard HEAD~1        # 撤销提交，删除更改
git revert commit-hash         # 创建撤销提交

# 清理
git clean -fd                  # 删除未跟踪文件
git gc                         # 垃圾回收
```

## 🚨 紧急修复流程

对于紧急bug修复：

1. 从main创建hotfix分支: `git checkout -b hotfix/critical-bug`
2. 快速修复并测试
3. 直接合并到main（跳过完整PR流程）
4. 同时合并到develop分支

## 📊 分支保护规则

### Main分支
- ✅ 需要PR审查
- ✅ 需要CI检查通过
- ✅ 需要至少1人批准
- ❌ 禁止直接推送
- ❌ 禁止强制推送

### 开发分支
- ✅ 允许直接推送
- ✅ 可选CI检查
- ❌ 禁止强制推送

## 🔗 相关链接

- [GitHub PR模板](../.github/pull_request_template.md)
- [CI/CD配置](../.github/workflows/pr-checks.yml)
- [贡献指南](../CONTRIBUTING.md)
