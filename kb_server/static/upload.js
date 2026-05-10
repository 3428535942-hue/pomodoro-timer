/**
 * 视频上传交互脚本 — 拖拽上传 + 进度展示 + 结果渲染。
 *
 * 功能：
 *   - 拖拽视频文件到上传区域
 *   - 点击上传区域触发文件选择
 *   - 上传进度动画（模拟流水线各阶段）
 *   - 处理结果展示（知识点卡片网格）
 */

var zone = document.getElementById('upload-zone');
var progressArea = document.getElementById('progress-area');
var resultsArea = document.getElementById('results-area');

// === 拖拽上传 ===
zone.addEventListener('dragover', function(e) {
    e.preventDefault();
    zone.classList.add('drag-over');
});
zone.addEventListener('dragleave', function() {
    zone.classList.remove('drag-over');
});
zone.addEventListener('drop', function(e) {
    e.preventDefault();
    zone.classList.remove('drag-over');
    var file = e.dataTransfer.files[0];
    if (file) handleFile(file);
});

/**
 * 处理文件上传 — 将视频发送到 /api/upload 并展示处理进度。
 * @param {File} file - 用户选择的视频文件
 */
async function handleFile(file) {
    if (!file.type.startsWith('video/')) {
        alert('请选择视频文件');
        return;
    }

    progressArea.style.display = 'block';
    resultsArea.style.display = 'none';

    var steps = [
        '[1/4] 上传中…',
        '[2/4] 音频轨道提取中…',
        '[3/4] 关键帧捕获中…',
        '[4/4] AI 语义理解与向量化…',
    ];

    var formData = new FormData();
    formData.append('file', file);

    try {
        updateProgress(0, steps[0]);

        var resp = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });
        if (!resp.ok) {
            throw new Error('HTTP ' + resp.status + ': ' + await resp.text());
        }

        var result = await resp.json();

        // 模拟处理进度动画
        for (var i = 1; i < steps.length; i++) {
            await sleep(800);
            updateProgress((i + 1) / steps.length * 100, steps[i]);
        }

        updateProgress(100, '处理完成！');
        await sleep(500);

        showResults(result);
    } catch (err) {
        updateProgress(0, '');
        document.getElementById('progress-text').textContent = '处理失败：' + err.message;
        document.getElementById('progress-text').style.color = '#ef4444';
    }
}

/**
 * 更新进度条和状态文字。
 * @param {number} pct - 进度百分比 (0–100)
 * @param {string} text - 当前步骤描述
 */
function updateProgress(pct, text) {
    var bar = document.getElementById('progress-bar');
    bar.style.width = pct + '%';
    bar.style.background = pct >= 100
        ? 'linear-gradient(90deg, #4f46e5, #7c3aed)'
        : 'linear-gradient(90deg, #4f46e5 ' + pct + '%, rgba(0,0,0,0.04) ' + pct + '%)';

    var steps = document.getElementById('progress-steps');
    steps.innerHTML = text
        ? '<span style="font-size:0.85rem;font-weight:500">' + text + '</span>'
        : '';

    document.getElementById('progress-text').textContent = pct >= 100 ? '✓ 完成' : Math.round(pct) + '%';
}

/**
 * 渲染处理结果 — 将提取的知识点片段以卡片网格展示。
 * @param {Object} result - /api/upload 返回的处理结果
 */
function showResults(result) {
    if (!result.segments || !result.segments.length) {
        resultsArea.innerHTML =
            '<div class="empty-state">' +
            '<div class="illustration">📭</div>' +
            '<h3>未提取到内容</h3></div>';
        resultsArea.style.display = 'block';
        return;
    }

    var html =
        '<h3 style="margin-bottom:1rem">提取到 ' + result.segments.length + ' 个知识点片段</h3>' +
        '<div class="bento-grid">';

    result.segments.forEach(function(seg, i) {
        html +=
            '<div class="card">' +
            '<div class="card-icon">🎯</div>' +
            '<h3>片段 ' + (i + 1) + '</h3>' +
            '<p style="font-size:0.8rem;color:var(--color-text-muted)">🕐 ' +
            formatTime(seg.start) + ' - ' + formatTime(seg.end) + '</p>' +
            '<p style="margin-top:0.5rem;font-size:0.9rem">' +
            (seg.summary || (seg.text ? seg.text.substring(0, 120) + '…' : '') || '(处理中)') +
            '</p>' +
            (seg.keywords
                ? '<div style="margin-top:0.5rem;display:flex;gap:0.3rem;flex-wrap:wrap">' +
                  seg.keywords.map(function(k) { return '<span class="badge badge-atom">' + k + '</span>'; }).join('') +
                  '</div>'
                : '') +
            '</div>';
    });

    html += '</div>';
    resultsArea.innerHTML = html;
    resultsArea.style.display = 'block';
    progressArea.style.display = 'none';
}

/**
 * 格式化秒数为 m:ss 显示格式。
 * @param {number} s - 秒数
 * @returns {string} 格式化后的时间字符串
 */
function formatTime(s) {
    var m = Math.floor(s / 60);
    var sec = Math.floor(s % 60);
    return m + ':' + (sec < 10 ? '0' : '') + sec;
}

/**
 * 异步延时函数。
 * @param {number} ms - 毫秒数
 * @returns {Promise} 在指定毫秒后 resolve
 */
function sleep(ms) {
    return new Promise(function(r) { setTimeout(r, ms); });
}
