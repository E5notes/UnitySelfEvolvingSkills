# Unity Self-Evolving Skills

一套用于 **Unity Editor 自动化** 的执行层 + **自进化经验库**（聚合/加权/清理）的组合。

## 优势（为什么值得单独用）

- **可执行**：不是只给建议，而是能通过 UnitySkills REST 直接操作 Unity Editor（建物体、改材质、建 UI、创建/保存场景…）。
- **可验证**：把“做完了”落到证据（`validate_scene`、Console errors、截图、测试）。
- **会变聪明但不堆日志**：
  - 原始工具调用是按月轮转的 JSONL（短期调试用）
  - 长期只保留 **SQLite 聚合统计**（相似操作合并、成功/失败加权）
  - 有清理脚本压缩/归档，避免越用越慢
- **项目可移植**：把 skills 放进仓库即可复用，不依赖个人机器的私有日志。

## 能做什么（示例）

- **UI**：创建 Canvas/Panel/Button/Text，批量布局，验证缺失脚本/重复命名/空引用。
- **Scene/Prefab**：创建/整理层级、实例化 Prefab、保存场景、检查缺失引用。
- **Shader/Material**：创建 shader、创建/修改材质属性、挂载到物体上。
- **Debug/Validation**：读取 Console errors、导出报告、快速发现工程结构问题。

## 使用教程（最短路径）

### 1) 启动 UnitySkills Server

在 Unity Editor 中：

- `Window > UnitySkills > Start Server`

默认服务地址（本仓库使用）：

- `http://127.0.0.1:8090`

### 2) 执行层（unity-skills）

```python
import sys
sys.path.insert(0, 'unity-skills/scripts')
from unity_skills import call_skill, is_unity_running

if is_unity_running():
    call_skill('gameobject_create', name='MyCube', primitiveType='Cube', x=0, y=1, z=0)
```

### 3) 自进化任务（推荐）

```python
import sys
sys.path.insert(0, 'unity-skills/scripts')
from unity_skills import (
    call_skill,
    start_self_evolving_task,
    finish_self_evolving_task,
)

task = start_self_evolving_task(
    "制作一个商业级 UI Panel，展示技能与模型结合优势",
    project_name="YourProject",
    frameworks=["UGUI", "TextMeshPro"],
)

call_skill("ui_create_canvas", name="DemoCanvas")
call_skill("ui_create_panel", name="DemoPanel", parent="DemoCanvas")
validation = call_skill("validate_scene", checkMissingScripts=True, checkDuplicateNames=True)

finish_self_evolving_task(
    task["task_id"],
    output_summary="Created demo UI panel and validated scene.",
    success=bool(validation.get("success")),
    lessons="Use validate_scene to keep UI generation clean; ensure unique object naming.",
    write_experience=True,
    title="Commercial UI Panel Generation Workflow",
)
```

### 4) 清理与合并（防止越用越大）

```bash
python unity-experience/scripts/self_evolving_knowledge.py --cleanup --raw-retention-days 30 --task-retention-days 90
```

## 仓库结构（独立仓库建议）

```text
unity-skills/
  SKILL.md
  scripts/unity_skills.py

unity-experience/
  SKILL.md
  scripts/self_evolving_knowledge.py
  UnityKnowledge/templates/
  .gitignore
```

## Attribution

二次开发：`https://github.com/Besty0728/Unity-Skills`

