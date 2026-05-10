"""GraphBuilder — 知识网络图谱数据构建器。

将扫描器产出的页面列表转换为 Cytoscape.js 兼容的图数据格式。
节点按页面类型着色、按链接度（degree）分级大小，
边表示页面间的 wikilink 关系。
"""


class GraphBuilder:
    """从页面字典构建知识图谱节点和边数据。

    用法：
        builder = GraphBuilder()
        graph_data = builder.build(pages)  # 返回 {"nodes": [...], "edges": [...]}
    """

    def build(self, pages: dict) -> dict:
        """构建 Cytoscape.js 兼容的图谱数据。

        参数：
            pages: {rel_path: PageInfo} 字典

        返回：
            {"nodes": [...], "edges": [...]}，可直接序列化为 JSON
        """
        nodes = []
        edges = []
        edge_ids: set[str] = set()

        for path, info in pages.items():
            # 节点的连接度 = 正向链接数 + 反向链接数
            degree = len(info.resolved_links) + len(info.backlinks)

            nodes.append({
                "data": {
                    "id": path,
                    "label": info.title,
                    "type": info.page_type,
                    "summary": (
                        info.summary[:80] if info.summary else info.title
                    ),
                    "url": f"/page/{path}",
                    "degree": degree,
                }
            })

            # 为每个已解析的 wikilink 创建边
            for _target_name, target_path in info.resolved_links:
                edge_id = f"{path}->{target_path}"
                # 去重：同一条边只添加一次
                if edge_id not in edge_ids and target_path in pages:
                    edge_ids.add(edge_id)
                    edges.append({
                        "data": {
                            "id": edge_id,
                            "source": path,
                            "target": target_path,
                        }
                    })

        return {"nodes": nodes, "edges": edges}
