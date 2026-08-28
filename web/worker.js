export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let fkxUrl = url.searchParams.get('fkx');

    if (!fkxUrl) {
      return new Response('缺少 fkx 参数', {
        status: 400,
        headers: { 'Access-Control-Allow-Origin': '*' }
      });
    }

    if (!fkxUrl.startsWith('http://') && !fkxUrl.startsWith('https://')) {
      fkxUrl = new URL(fkxUrl, request.url).href;
    }

    try {
      const fkxResponse = await fetch(fkxUrl);
      if (!fkxResponse.ok) {
        return new Response('无法获取文件信息', {
          status: fkxResponse.status,
          headers: { 'Access-Control-Allow-Origin': '*' }
        });
      }

      const fkxContent = await fkxResponse.text();
      const fkxInfo = parseFkx(fkxContent);

      if (!fkxInfo.filename || !fkxInfo.chunks || fkxInfo.chunks.length === 0) {
        return new Response('文件信息格式不正确', {
          status: 400,
          headers: { 'Access-Control-Allow-Origin': '*' }
        });
      }

      const baseUrl = getBaseUrl(fkxUrl);
      const totalSize = fkxInfo.chunks.reduce((sum, chunk) => sum + chunk.size, 0);
      const sanitizedName = fkxInfo.filename.replace(/[<>:"/\\|?*]/g, '_');
      const rangeHeader = request.headers.get('Range');
      const isRangeRequest = !!rangeHeader;

      let rangeStart = 0, rangeEnd = totalSize - 1;
      if (rangeHeader) {
        const match = rangeHeader.match(/bytes=(\d+)-(\d*)/);
        if (match && match[1] !== undefined) {
          rangeStart = parseInt(match[1], 10) || 0;
          if (match[2] !== '' && match[2] !== undefined) {
            rangeEnd = parseInt(match[2], 10) || totalSize - 1;
          }
          if (rangeEnd >= totalSize) rangeEnd = totalSize - 1;
        }
      }
      const rangeLength = Math.max(0, rangeEnd - rangeStart + 1);

      let startChunkIdx = 0, startOffset = rangeStart;
      let cumulativeSize = 0;
      for (let i = 0; i < fkxInfo.chunks.length; i++) {
        if (cumulativeSize + fkxInfo.chunks[i].size > rangeStart) {
          startChunkIdx = i;
          startOffset = rangeStart - cumulativeSize;
          break;
        }
        cumulativeSize += fkxInfo.chunks[i].size;
      }

      const headers = new Headers({
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename="${sanitizedName}"; filename*=UTF-8''${encodeURIComponent(sanitizedName)}`,
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length, Content-Range, Accept-Ranges',
        'Accept-Ranges': 'bytes'
      });

      if (isRangeRequest) {
        headers.set('Content-Range', `bytes ${rangeStart}-${rangeEnd}/${totalSize}`);
        headers.set('Content-Length', String(rangeLength));
        return new Response(createStream(baseUrl, fkxInfo.chunks, startChunkIdx, startOffset, rangeLength), { status: 206, headers });
      }

      headers.set('Content-Length', String(totalSize));
      return new Response(createStream(baseUrl, fkxInfo.chunks), { headers });
    } catch (error) {
      console.error('下载合并失败:', error);
      return new Response(`下载合并失败: ${error.message}`, {
        status: 500,
        headers: { 'Access-Control-Allow-Origin': '*' }
      });
    }
  }
};

function parseFkx(content) {
  const info = { chunks: [] };
  const lines = content.trim().split('\n');

  for (const line of lines) {
    const eqIdx = line.indexOf('=');
    if (eqIdx < 0) continue;
    const key = line.substring(0, eqIdx);
    const value = line.substring(eqIdx + 1);

    if (key.startsWith('chunk_')) {
      const parts = value.split(',');
      if (parts.length >= 2) {
        info.chunks.push({
          filename: parts[0].trim().replace(/^.*[\\/]/, ''),
          size: parseInt(parts[1].trim(), 10) || 0,
        });
      }
    } else {
      info[key] = value.trim();
    }
  }

  return info;
}

function getBaseUrl(fkxUrl) {
  const parsed = new URL(fkxUrl);
  const pathParts = parsed.pathname.split('/');
  pathParts.pop();
  return `${parsed.protocol}//${parsed.host}${pathParts.join('/')}/`;
}

async function* streamChunks(baseUrl, chunks, startIdx, startOffset, maxBytes) {
  let sent = 0;
  for (let i = 0; i < chunks.length; i++) {
    const chunkHeaders = {};
    if (i === startIdx && startOffset > 0) {
      chunkHeaders['Range'] = 'bytes=' + startOffset + '-';
    }
    const chunkUrl = baseUrl + chunks[i].filename;
    const response = await fetch(chunkUrl, { headers: chunkHeaders });

    if (!response.ok) {
      throw new Error(`无法下载分片: ${chunks[i].filename}`);
    }

    const reader = response.body.getReader();
    let chunkOffset = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      if (i === startIdx && chunkOffset + value.length <= startOffset) {
        chunkOffset += value.length;
        continue;
      }

      let data = value;
      if (i === startIdx && chunkOffset < startOffset) {
        data = value.subarray(startOffset - chunkOffset);
      }
      chunkOffset += value.length;

      if (maxBytes && sent + data.length > maxBytes) {
        data = data.subarray(0, maxBytes - sent);
      }

      if (data.length > 0) {
        yield data;
        sent += data.length;
      }

      if (maxBytes && sent >= maxBytes) return;
    }
  }
}

function createStream(baseUrl, chunks, startIdx, startOffset, maxBytes) {
  const { writable, readable } = new ReadableStream({
    async start(controller) {
      const writer = controller;
      try {
        for await (const chunk of streamChunks(baseUrl, chunks, startIdx, startOffset, maxBytes)) {
          writer.enqueue(chunk);
        }
        writer.close();
      } catch (error) {
        writer.error(error);
      }
    }
  });
  return readable;
}
