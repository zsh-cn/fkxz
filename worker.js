export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    let wjxUrl = url.searchParams.get('wjx');
    
    if (!wjxUrl) {
      return new Response('缺少 wjx 参数', { status: 400 });
    }
    
    if (!wjxUrl.startsWith('http://') && !wjxUrl.startsWith('https://')) {
      wjxUrl = new URL(wjxUrl, request.url).href;
    }
    
    if (!wjxUrl.endsWith('.wjx')) {
      return new Response('wjx 参数必须指向 .wjx 文件', { status: 400 });
    }
    
    try {
      const wjxResponse = await fetch(wjxUrl);
      if (!wjxResponse.ok) {
        return new Response('无法获取文件信息', { status: wjxResponse.status });
      }
      
      const wjxContent = await wjxResponse.text();
      const wjxInfo = parseWjx(wjxContent);
      
      if (!wjxInfo.filename || !wjxInfo.chunks || wjxInfo.chunks.length === 0) {
        return new Response('文件信息格式不正确', { status: 400 });
      }
      
      const baseUrl = getBaseUrl(wjxUrl);
      const totalSize = wjxInfo.chunks.reduce((sum, chunk) => sum + chunk.size, 0);
      
      const headers = new Headers({
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': `attachment; filename="${wjxInfo.filename}"; filename*=UTF-8''${encodeURIComponent(wjxInfo.filename)}`,
        'Access-Control-Allow-Origin': '*',
      });
      
      return new Response(createStream(baseUrl, wjxInfo.chunks, totalSize), { headers });
    } catch (error) {
      console.error('下载合并失败:', error);
      return new Response(`下载合并失败: ${error.message}`, { status: 500 });
    }
  }
};

function parseWjx(content) {
  const info = { chunks: [] };
  const lines = content.trim().split('\n');
  
  for (const line of lines) {
    if (!line.includes('=')) continue;
    
    const [key] = line.split('=', 1);
    const value = line.substring(key.length + 1);
    
    if (key.startsWith('chunk_')) {
      const parts = value.split(',');
      if (parts.length >= 2) {
        info.chunks.push({
          filename: parts[0].trim(),
          size: parseInt(parts[1].trim(), 10) || 0,
        });
      }
    } else {
      info[key] = value.trim();
    }
  }
  
  return info;
}

function getBaseUrl(wjxUrl) {
  const parsed = new URL(wjxUrl);
  const pathParts = parsed.pathname.split('/');
  pathParts.pop();
  return `${parsed.protocol}//${parsed.host}${pathParts.join('/')}/`;
}

async function* streamChunks(baseUrl, chunks) {
  for (const chunk of chunks) {
    const chunkUrl = baseUrl + chunk.filename;
    const response = await fetch(chunkUrl);
    
    if (!response.ok) {
      throw new Error(`无法下载分片: ${chunk.filename}`);
    }
    
    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      yield value;
    }
  }
}

function createStream(baseUrl, chunks, totalSize) {
  const { writable, readable } = new FixedLengthStream(totalSize);
  
  (async () => {
    const writer = writable.getWriter();
    try {
      for await (const chunk of streamChunks(baseUrl, chunks)) {
        await writer.write(chunk);
      }
      await writer.close();
    } catch (error) {
      writer.abort(error);
    }
  })();
  
  return readable;
}