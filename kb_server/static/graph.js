/**
 * 知识图谱 — D3.js 赛博朋克风格可视化。
 *
 * 功能：
 *   - D3 v7 力导向布局 + 霓虹发光节点 + 暗黑主题
 *   - 悬停高亮邻域 / 点击聚焦跳转 / 搜索定位
 *   - 鼠标缩放平移 / 小地图 / 图例
 *   - 尊重 prefers-reduced-motion
 */
(function () {
    'use strict';

    // ================================================================
    // 配置
    // ================================================================

    var COLORS = {
        topic: { fill: '#00e676', glow: '#00e676', label: '主题' },
        atom:  { fill: '#448aff', glow: '#448aff', label: '概念' },
        raw:   { fill: '#78909c', glow: '#78909c', label: '原始' },
        other: { fill: '#546e7a', glow: '#546e7a', label: '其他' }
    };

    var FORCE_CHARGE = -350;
    var FORCE_LINK_DIST = 120;
    var FORCE_LINK_STR = 0.3;
    var FORCE_COLLIDE = 20;
    var FORCE_CENTER_STR = 0.08;
    var FORCE_ALPHA_DECAY = 0.02;
    var NODE_R_MIN = 5;
    var NODE_R_MAX = 16;
    var REDUCED_MOTION = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ================================================================
    // DOM 就绪后初始化
    // ================================================================

    function init() {
        var container = document.getElementById('graph-container');
        if (!container) { console.error('graph-container not found'); return; }

        var tooltipEl = document.getElementById('node-tooltip');
        var searchInput = document.getElementById('graph-search-input');
        var matchBadge = document.getElementById('match-badge');
        var statsEl = document.getElementById('stats');
        var minimapCanvas = document.getElementById('minimap-canvas');
        var minimapCtx = minimapCanvas ? minimapCanvas.getContext('2d') : null;

        // 画布尺寸：确保有效值
        var W = Math.max(container.clientWidth, 800);
        var H = Math.max(container.clientHeight, 500);

        // 如果容器高度为 0（CSS 尚未计算完成），用视口高度兜底
        if (container.clientHeight < 100) {
            H = Math.max(window.innerHeight - 60, 500);
            container.style.height = H + 'px';
        }

        // ---------- SVG 创建 ----------

        var svg = d3.select('#graph-container')
            .append('svg')
            .attr('width', W)
            .attr('height', H)
            .style('background', 'radial-gradient(ellipse at center, #111122 0%, #0a0a0f 70%)');

        // ---------- SVG 滤镜 ----------

        var defs = svg.append('defs');

        Object.keys(COLORS).forEach(function (t) {
            var f = defs.append('filter')
                .attr('id', 'glow-' + t)
                .attr('x', '-60%').attr('y', '-60%')
                .attr('width', '220%').attr('height', '220%');
            f.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'b');
            f.append('feMerge')
                .selectAll('feMergeNode').data(['b', 'SourceGraphic'])
                .enter().append('feMergeNode').attr('in', function (d) { return d; });
        });

        var sf = defs.append('filter')
            .attr('id', 'glow-sel')
            .attr('x', '-80%').attr('y', '-80%')
            .attr('width', '260%').attr('height', '260%');
        sf.append('feGaussianBlur').attr('stdDeviation', '8').attr('result', 'b');
        sf.append('feMerge')
            .selectAll('feMergeNode').data(['b', 'SourceGraphic'])
            .enter().append('feMergeNode').attr('in', function (d) { return d; });

        // ---------- 图层 ----------

        var edgeG = svg.append('g');
        var flowG = svg.append('g');
        var nodeG = svg.append('g');
        var labelG = svg.append('g');

        // ---------- D3 Zoom ----------

        var zoom = d3.zoom()
            .scaleExtent([0.15, 4])
            .on('zoom', function (event) {
                edgeG.attr('transform', event.transform);
                flowG.attr('transform', event.transform);
                nodeG.attr('transform', event.transform);
                labelG.attr('transform', event.transform);
                if (minimapCtx) drawMinimap(event.transform);
            });

        svg.call(zoom);

        // ---------- 数据加载 ----------

        fetch('/api/graph')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.nodes || !data.nodes.length) {
                    container.innerHTML =
                        '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;color:#b0b8d0">' +
                        '<div style="font-size:4rem;margin-bottom:1rem">🗺️</div>' +
                        '<h3>暂无图谱数据</h3><p style="color:#5c6270">收录资料后 wikilink 会自动形成知识网络</p></div>';
                    statsEl.textContent = '0 节点 · 0 边';
                    return;
                }
                build(data);
            })
            .catch(function (err) {
                container.innerHTML =
                    '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;color:#b0b8d0">' +
                    '<div style="font-size:4rem;margin-bottom:1rem">⚠️</div>' +
                    '<h3>图谱加载失败</h3><p style="color:#5c6270">' + (err.message || '未知错误') + '</p></div>';
            });

        // ============================================================
        // 主构建函数
        // ============================================================

        function build(raw) {
            // ---- 数据预处理 ----

            var maxDeg = d3.max(raw.nodes, function (n) { return n.data.degree; }) || 1;

            var nodes = raw.nodes.map(function (n) {
                var d = n.data;
                var ratio = maxDeg > 1 ? Math.log(1 + d.degree) / Math.log(1 + maxDeg) : 0.5;
                return {
                    id: d.id,
                    label: d.label,
                    type: d.type || 'other',
                    summary: d.summary || '',
                    url: d.url || '',
                    degree: d.degree || 0,
                    r: NODE_R_MIN + (NODE_R_MAX - NODE_R_MIN) * ratio
                };
            });

            var nodeMap = {};
            nodes.forEach(function (n) { nodeMap[n.id] = n; });

            var edges = raw.edges
                .map(function (e) { return { source: e.data.source, target: e.data.target }; })
                .filter(function (e) { return nodeMap[e.source] && nodeMap[e.target]; });

            // ---- 渲染边 ----

            var link = edgeG.selectAll('line')
                .data(edges).enter().append('line')
                .attr('stroke', '#1a1a3e')
                .attr('stroke-width', 1)
                .attr('stroke-opacity', 0.5);

            // ---- 渲染边流动粒子 ----

            var flowDots = flowG.selectAll('circle')
                .data(edges).enter().append('circle')
                .attr('r', 2)
                .attr('fill', '#6366f1')
                .attr('opacity', 0);

            // ---- 渲染节点 ----

            var nodeSel = nodeG.selectAll('g.node-g')
                .data(nodes).enter().append('g')
                .attr('class', 'node-g')
                .style('cursor', 'pointer');

            nodeSel.append('circle')
                .attr('class', 'node-body')
                .attr('r', function (d) { return d.r; })
                .attr('fill', function (d) { return COLORS[d.type].fill; })
                .attr('fill-opacity', 0.85)
                .attr('stroke', function (d) { return COLORS[d.type].glow; })
                .attr('stroke-width', 1.5)
                .attr('stroke-opacity', 0.6)
                .attr('filter', function (d) { return 'url(#glow-' + d.type + ')'; });

            nodeSel.append('circle')
                .attr('class', 'node-core')
                .attr('r', function (d) { return Math.max(1.5, d.r * 0.3); })
                .attr('fill', '#fff')
                .attr('fill-opacity', 0.4);

            // ---- 渲染标签 ----

            var label = labelG.selectAll('text')
                .data(nodes).enter().append('text')
                .text(function (d) {
                    return d.label.length > 8 ? d.label.substring(0, 8) + '...' : d.label;
                })
                .attr('font-size', '10px')
                .attr('font-family', 'Inter, sans-serif')
                .attr('fill', '#b0b8d0')
                .attr('text-anchor', 'middle')
                .attr('pointer-events', 'none')
                .attr('opacity', 0.6);

            // ---- 力导向模拟 ----

            var sim = d3.forceSimulation(nodes)
                .force('link', d3.forceLink(edges).id(function (d) { return d.id; })
                    .distance(FORCE_LINK_DIST).strength(FORCE_LINK_STR))
                .force('charge', d3.forceManyBody().strength(FORCE_CHARGE))
                .force('collide', d3.forceCollide().radius(function (d) { return d.r + FORCE_COLLIDE; }))
                .force('center', d3.forceCenter(W / 2, H / 2).strength(FORCE_CENTER_STR))
                .alphaDecay(REDUCED_MOTION ? 0.5 : FORCE_ALPHA_DECAY);

            // tick: 只做位置更新，不做昂贵计算
            sim.on('tick', function () {
                link
                    .attr('x1', function (d) { return d.source.x; })
                    .attr('y1', function (d) { return d.source.y; })
                    .attr('x2', function (d) { return d.target.x; })
                    .attr('y2', function (d) { return d.target.y; });

                nodeSel.attr('transform', function (d) {
                    return 'translate(' + d.x + ',' + d.y + ')';
                });

                label
                    .attr('x', function (d) { return d.x; })
                    .attr('y', function (d) { return d.y - d.r - 7; });
            });

            sim.on('end', function () {
                statsEl.textContent = '节点 ' + nodes.length + ' · 边 ' + edges.length;
                if (minimapCtx) drawMinimap(d3.zoomTransform(svg.node()));
                // 粒子流动动画在模拟结束后用 RAF 驱动
                if (!REDUCED_MOTION) startFlowAnimation(edges, flowDots);
            });

            // ---- 交互：悬停 ----

            nodeSel.on('mouseenter', function (event, d) {
                var self = d3.select(this);
                self.select('.node-body')
                    .transition().duration(180)
                    .attr('r', d.r * 1.5)
                    .attr('stroke-opacity', 1)
                    .attr('filter', 'url(#glow-sel)');

                var conn = connectedSet(d, edges, nodeMap);
                nodeSel.select('.node-body')
                    .transition().duration(180)
                    .attr('opacity', function (n) {
                        return n.id === d.id ? 1 : conn.has(n.id) ? 0.85 : 0.12;
                    });
                link
                    .transition().duration(180)
                    .attr('stroke-opacity', function (l) {
                        var src = l.source.id || l.source;
                        var tgt = l.target.id || l.target;
                        return (src === d.id || tgt === d.id) ? 0.85 : 0.04;
                    })
                    .attr('stroke', function (l) {
                        var src = l.source.id || l.source;
                        var tgt = l.target.id || l.target;
                        return (src === d.id || tgt === d.id) ? '#6366f1' : '#1a1a3e';
                    });
                label
                    .transition().duration(180)
                    .attr('opacity', function (n) {
                        return n.id === d.id ? 1 : conn.has(n.id) ? 0.5 : 0.04;
                    });

                showTooltip(event, d, tooltipEl, container);
            });

            nodeSel.on('mousemove', function (event) {
                positionTooltip(event, tooltipEl, container);
            });

            nodeSel.on('mouseleave', function () {
                nodeSel.select('.node-body')
                    .transition().duration(250)
                    .attr('r', function (n) { return n.r; })
                    .attr('opacity', 0.85)
                    .attr('stroke-opacity', 0.6)
                    .attr('filter', function (n) { return 'url(#glow-' + n.type + ')'; });
                link.transition().duration(250)
                    .attr('stroke', '#1a1a3e').attr('stroke-opacity', 0.5);
                label.transition().duration(250).attr('opacity', 0.6);
                tooltipEl.classList.remove('visible');
            });

            // ---- 交互：点击 ----

            nodeSel.on('click', function (event, d) {
                event.stopPropagation();
                // 涟漪
                var rp = svg.append('circle')
                    .attr('cx', d.x).attr('cy', d.y).attr('r', 6)
                    .attr('fill', 'none').attr('stroke', COLORS[d.type].fill)
                    .attr('stroke-width', 2.5).attr('opacity', 1);
                rp.transition().duration(700).attr('r', 55).attr('opacity', 0).remove();
                // 聚焦
                svg.transition().duration(500).call(zoom.transform,
                    d3.zoomIdentity.translate(W / 2, H / 2).scale(2).translate(-d.x, -d.y));
                if (d.url) setTimeout(function () { window.location.href = d.url; }, 450);
            });

            svg.on('click', function () { tooltipEl.classList.remove('visible'); });

            // ---- 搜索 ----

            searchInput.addEventListener('input', function () {
                var q = this.value.trim().toLowerCase();
                if (!q) {
                    resetHighlight(nodeSel, link, label);
                    matchBadge.style.display = 'none';
                    return;
                }
                var hit = nodes.filter(function (n) {
                    return n.label.toLowerCase().indexOf(q) !== -1 ||
                           n.summary.toLowerCase().indexOf(q) !== -1;
                });
                matchBadge.style.display = 'inline';
                if (hit.length) {
                    matchBadge.textContent = hit.length + ' 个匹配';
                    matchBadge.style.background = 'rgba(0,230,118,0.15)';
                    matchBadge.style.color = '#00e676';
                    highlightNodes(hit, nodeSel, link, label);
                } else {
                    matchBadge.textContent = '无匹配';
                    matchBadge.style.background = 'rgba(255,82,82,0.15)';
                    matchBadge.style.color = '#ff5252';
                }
            });

            searchInput.addEventListener('keydown', function (e) {
                if (e.key !== 'Enter') { if (e.key === 'Escape') { this.value = ''; resetHighlight(nodeSel, link, label); matchBadge.style.display = 'none'; } return; }
                var q = this.value.trim().toLowerCase();
                if (!q) return;
                var hit = nodes.filter(function (n) {
                    return n.label.toLowerCase().indexOf(q) !== -1 ||
                           n.summary.toLowerCase().indexOf(q) !== -1;
                });
                if (!hit.length) return;
                window._si = (window._si || 0) % hit.length;
                var t = hit[window._si];
                svg.transition().duration(450).call(zoom.transform,
                    d3.zoomIdentity.translate(W / 2, H / 2).scale(2.2).translate(-t.x, -t.y));
                matchBadge.textContent = (window._si + 1) + '/' + hit.length;
                window._si++;
            });

            // ---- 图例 ----

            var leg = document.getElementById('legend');
            if (leg) {
                var h = '';
                Object.keys(COLORS).forEach(function (k) {
                    var c = COLORS[k];
                    h += '<span style="display:inline-flex;align-items:center;gap:0.35rem;font-size:0.78rem;color:#b0b8d0">' +
                        '<i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + c.fill +
                        ';box-shadow:0 0 8px ' + c.glow + '"></i>' + c.label + '</span>';
                });
                leg.innerHTML = h;
            }

            // ---- 首帧小地图 ----

            if (minimapCtx) setTimeout(function () { drawMinimap(d3.zoomTransform(svg.node())); }, 1000);
        }

        // ============================================================
        // 辅助函数
        // ============================================================

        function connectedSet(d, edges, map) {
            var s = new Set(); s.add(d.id);
            edges.forEach(function (e) {
                var src = typeof e.source === 'object' ? e.source.id : e.source;
                var tgt = typeof e.target === 'object' ? e.target.id : e.target;
                if (src === d.id) s.add(tgt);
                if (tgt === d.id) s.add(src);
            });
            return s;
        }

        function showTooltip(ev, d, el, ct) {
            var c = COLORS[d.type];
            el.innerHTML =
                '<span class="tt-type" style="background:' + c.fill + '20;color:' + c.fill + '">' +
                c.label + '</span>' +
                '<div class="tt-label">' + d.label + '</div>' +
                (d.summary ? '<div class="tt-summary">' + escHtml(d.summary.substring(0, 100)) + '</div>' : '') +
                '<div class="tt-meta">关联 ' + d.degree + ' 项 · 点击查看详情</div>';
            el.classList.add('visible');
            positionTooltip(ev, el, ct);
        }

        function positionTooltip(ev, el, ct) {
            var r = ct.getBoundingClientRect();
            var l = ev.clientX - r.left + 14;
            var t = ev.clientY - r.top - 10;
            if (l + 240 > r.width) l = ev.clientX - r.left - 250;
            if (t + 130 > r.height) t = ev.clientY - r.top - 140;
            el.style.left = l + 'px';
            el.style.top = t + 'px';
        }

        function escHtml(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

        function highlightNodes(hit, ns, lk, lb) {
            var set = new Set(hit.map(function (n) { return n.id; }));
            ns.select('.node-body').transition().duration(200)
                .attr('opacity', function (n) { return set.has(n.id) ? 1 : 0.06; });
            lk.transition().duration(200).attr('stroke-opacity', 0.03);
            lb.transition().duration(200)
                .attr('opacity', function (n) { return set.has(n.id) ? 1 : 0; });
        }

        function resetHighlight(ns, lk, lb) {
            ns.select('.node-body').transition().duration(250).attr('opacity', 0.85);
            lk.transition().duration(250).attr('stroke', '#1a1a3e').attr('stroke-opacity', 0.5);
            lb.transition().duration(250).attr('opacity', 0.6);
            window._si = 0;
        }

        /** RAF 驱动的粒子流动动画（仅模拟结束后运行） */
        function startFlowAnimation(edges, dots) {
            var startTime = Date.now();
            function step() {
                var elapsed = Date.now() - startTime;
                dots
                    .attr('cx', function (d) {
                        var t = (elapsed * 0.00015 + d.source.x * 0.02) % 1;
                        return d.source.x + (d.target.x - d.source.x) * t;
                    })
                    .attr('cy', function (d) {
                        var t = (elapsed * 0.00015 + d.source.y * 0.02) % 1;
                        return d.source.y + (d.target.y - d.source.y) * t;
                    })
                    .attr('opacity', 0.1 + Math.abs(Math.sin(elapsed * 0.001)) * 0.35);
                window._flowRaf = requestAnimationFrame(step);
            }
            window._flowRaf = requestAnimationFrame(step);
        }

        /** 小地图 */
        function drawMinimap(transform) {
            var cw = minimapCanvas.width, ch = minimapCanvas.height;
            var ctx = minimapCtx;
            ctx.clearRect(0, 0, cw, ch);
            ctx.fillStyle = 'rgba(10,10,20,0.85)';
            ctx.fillRect(0, 0, cw, ch);

            var s = Math.min(cw / W, ch / H);
            var ox = (cw - W * s) / 2;
            var oy = (ch - H * s) / 2;

            ctx.fillStyle = '#6366f1';
            d3.selectAll('.node-g').each(function () {
                var t = d3.select(this).attr('transform');
                if (!t) return;
                var m = t.match(/translate\(([^,]+),\s*([^)]+)\)/);
                if (!m) return;
                var cx = parseFloat(m[1]) * s + ox;
                var cy = parseFloat(m[2]) * s + oy;
                ctx.beginPath(); ctx.arc(cx, cy, 1.5, 0, Math.PI * 2); ctx.fill();
            });

            if (transform) {
                var vx = -transform.x * s / transform.k + ox;
                var vy = -transform.y * s / transform.k + oy;
                var vw = W * s / transform.k;
                var vh = H * s / transform.k;
                ctx.strokeStyle = '#00e676'; ctx.lineWidth = 1.2;
                ctx.strokeRect(vx, vy, vw, vh);
            }
        }
    }

    // ================================================================
    // 启动
    // ================================================================

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
