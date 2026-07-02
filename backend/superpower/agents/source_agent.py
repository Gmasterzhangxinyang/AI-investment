from __future__ import annotations

from superpower.runtime.agent import AgentSpec, SkillBackedAgent


class SourceArchiveAgent(SkillBackedAgent):
    name = "source-archive-agent"
    description = "Fingerprint and archive source Excel files."
    success_message = "源文件归档完成"
    spec = AgentSpec(
        role="数据源归档 Agent",
        objective="在每日工作流开始时记录 ETF/TL/可转债源文件的存在性、修改时间、大小和哈希，并归档可用源文件。",
        skill_name="source-archive",
        required_artifacts=("skill_registry", "etf_file", "tl_file"),
        produced_artifacts=("source_manifest", "source_manifest_path"),
        quality_gates=(
            "每次运行必须生成源文件 manifest",
            "存在的源文件必须保留哈希和修改时间",
            "归档只复制文件，不修改客户原始 Excel",
        ),
        decision_policy="数据源归档 Agent 不读取策略含义，只负责可追溯性和交付审计。",
    )
