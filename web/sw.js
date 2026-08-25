self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (url.pathname.endsWith('/fkxz')) {
        const wjxUrl = url.searchParams.get('wjx');
        if (wjxUrl) {
            event.respondWith(streamDownload(wjxUrl));
        }
    }
});

async function streamDownload(wjxUrl) {
    try {
        const wjxRes = await fetch(wjxUrl);
        if (!wjxRes.ok) throw new Error('无法获取文件信息: HTTP ' + wjxRes.status);
        const wjxText = await wjxRes.text();
        const info = parseWjx(wjxText);
        if (!info.filename || !info.chunks?.length) throw new Error('文件信息格式不正确');

        const baseUrl = getBaseUrl(wjxUrl);
        const totalSize = info.chunks.reduce((s, c) => s + c.size, 0);
        const sanitizedName = info.filename.replace(/[<>:"/\\|?*]/g, '_');

        const stream = new ReadableStream({
            async start(controller) {
                for (const chunk of info.chunks) {
                    try {
                        const chunkRes = await fetch(baseUrl + chunk.filename);
                        if (!chunkRes.ok) {
                            controller.error(new Error('无法下载分片: ' + chunk.filename));
                            return;
                        }
                        const reader = chunkRes.body.getReader();
                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;
                            controller.enqueue(value);
                        }
                    } catch (e) {
                        controller.error(e);
                        return;
                    }
                }
                controller.close();
            },
            cancel() {
                console.log('下载已取消');
            }
        });

        return new Response(stream, {
            headers: {
                'Content-Type': 'application/octet-stream',
                'Content-Disposition': `attachment; filename="${sanitizedName}"; filename*=UTF-8''${encodeURIComponent(sanitizedName)}`,
                'Content-Length': String(totalSize),
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length'
            }
        });
    } catch (e) {
        console.error('下载失败:', e);
        return new Response('下载失败: ' + e.message, { status: 500 });
    }
}

function parseWjx(content) {
    const info = { chunks: [] };
    for (const line of content.trim().split('\n')) {
        const eqIdx = line.indexOf('=');
        if (eqIdx < 0) continue;
        const key = line.substring(0, eqIdx), value = line.substring(eqIdx + 1);
        if (key.startsWith('chunk_')) {
            const parts = value.split(',');
            if (parts.length >= 2) info.chunks.push({
                filename: parts[0].trim().replace(/^.*[\\/]/, ''),
                size: parseInt(parts[1].trim()) || 0
            });
        } else info[key] = value.trim();
    }
    return info;
}

function getBaseUrl(url) {
    const parsed = new URL(url);
    const pathParts = parsed.pathname.split('/');
    pathParts.pop();
    return parsed.origin + pathParts.join('/') + '/';
}