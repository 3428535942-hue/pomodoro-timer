"""Graph data builder — produces nodes & edges from scanner pages."""


class GraphBuilder:
    def build(self, pages: dict) -> dict:
        """Build Cytoscape.js compatible graph data."""
        nodes = []
        edges = []
        edge_ids = set()

        for path, info in pages.items():
            # Count connections
            degree = len(info.resolved_links) + len(info.backlinks)

            nodes.append({
                "data": {
                    "id": path,
                    "label": info.title,
                    "type": info.page_type,
                    "summary": info.summary[:80] if info.summary else info.title,
                    "url": f"/page/{path}",
                    "degree": degree,
                }
            })

            # Edges from resolved wikilinks
            for target_name, target_path in info.resolved_links:
                edge_id = f"{path}->{target_path}"
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
