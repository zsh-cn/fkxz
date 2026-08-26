self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    if (url.pathname.endsWith('/fkxz')) {
        const fkxUrl = url.searchParams.get('fkx');
        if (fkxUrl) {
            event.respondWith(streamDownload(fkxUrl, event.request));
        }
    }
});

async function streamDownload(fkxUrl, request) {
    try {
        const fkxRes = await fetch(fkxUrl);
        if (!fkxRes.ok) throw new Error('无法获取文件信息: HTTP ' + fkxRes.status);
        const fkxText = await fkxRes.text();
        const info = parseFkx(fkxText);
        if (!info.filename || !info.chunks?.length) throw new Error('文件信息格式不正确');

        const baseUrl = getBaseUrl(fkxUrl);
        const totalSize = info.chunks.reduce((s, c) => s + c.size, 0);
        const sanitizedName = info.filename.replace(/[<>:"/\\|?*]/g, '_');

        let rangeStart = 0, rangeEnd = totalSize - 1;
        const rangeHeader = request && request.headers.get('Range');
        const isRangeRequest = !!rangeHeader;
        if (rangeHeader) {
            const match = rangeHeader.match(/bytes=(\d+)-(\d*)/);
            if (match) {
                rangeStart = parseInt(match[1], 10) || 0;
                rangeEnd = match[2] ? parseInt(match[2], 10) : totalSize - 1;
            }
        }
        const rangeLength = rangeEnd - rangeStart + 1;

        let startChunkIdx = 0, startOffset = rangeStart;
        let cumulativeSize = 0;
        for (let i = 0; i < info.chunks.length; i++) {
            if (cumulativeSize + info.chunks[i].size > rangeStart) {
                startChunkIdx = i;
                startOffset = rangeStart - cumulativeSize;
                break;
            }
            cumulativeSize += info.chunks[i].size;
        }

        const stream = new ReadableStream({
            async start(controller) {
                let rangeSent = 0;
                for (let i = startChunkIdx; i < info.chunks.length && rangeSent < rangeLength; i++) {
                    try {
                        const chunkRes = await fetch(baseUrl + info.chunks[i].filename);
                        if (!chunkRes.ok) {
                            controller.error(new Error('无法下载分片: ' + info.chunks[i].filename));
                            return;
                        }
                        const reader = chunkRes.body.getReader();
                        let chunkOffset = 0;
                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;

                            if (i === startChunkIdx && chunkOffset + value.length <= startOffset) {
                                chunkOffset += value.length;
                                continue;
                            }

                            let data = value;
                            if (i === startChunkIdx && chunkOffset < startOffset) {
                                data = value.subarray(startOffset - chunkOffset);
                            }
                            chunkOffset += value.length;

                            if (rangeSent + data.length > rangeLength) {
                                data = data.subarray(0, rangeLength - rangeSent);
                            }

                            if (data.length > 0) {
                                controller.enqueue(data);
                                rangeSent += data.length;
                            }

                            if (rangeSent >= rangeLength) break;
                        }
                    } catch (e) {
                        controller.error(e);
                        return;
                    }
                }
                controller.close();
            },
            cancel() {}
        });

        const headers = {
            'Content-Type': 'application/octet-stream',
            'Content-Disposition': `attachment; filename="${sanitizedName}"; filename*=UTF-8''${encodeURIComponent(sanitizedName)}`,
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length, Content-Range',
            'Accept-Ranges': 'bytes'
        };

        if (isRangeRequest) {
            headers['Content-Range'] = `bytes ${rangeStart}-${rangeEnd}/${totalSize}`;
            headers['Content-Length'] = String(rangeLength);
            return new Response(stream, { status: 206, headers });
        }

        headers['Content-Length'] = String(totalSize);
        return new Response(stream, { headers });
    } catch (e) {
        console.error('下载失败:', e);
        return new Response('下载失败: ' + e.message, { status: 500 });
    }
}

function parseFkx(content) {
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