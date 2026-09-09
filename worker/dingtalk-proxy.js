/**
 * TE102 问卷 → 钉钉机器人 CORS 代理
 *
 * 部署步骤：
 * 1. 登录 https://dash.cloudflare.com → Workers & Pages → Create application
 * 2. 取名 te102-dingtalk，粘贴此代码，Deploy
 * 3. 复制 Worker URL（如 https://te102-dingtalk.xxx.workers.dev）
 * 4. 填入 index.html 的 WORKER_URL 常量
 */

const DINGTALK_WEBHOOK = 'https://oapi.dingtalk.com/robot/send?access_token=7e2120d25d16e13ddd2a214618764b9417a217752f960cd7835a5a1c68b28b84';
const DINGTALK_SECRET = 'SECf03bbadc47bd7bdc8102169e9767336b877efee79be6fc29c5a7449a4e14d77e';

export default {
  async fetch(request) {
    // CORS 预检
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type'
        }
      });
    }

    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405, headers: { 'Access-Control-Allow-Origin': '*' } });
    }

    try {
      // 加签
      const timestamp = Date.now();
      const stringToSign = timestamp + '\n' + DINGTALK_SECRET;
      const key = await crypto.subtle.importKey(
        'raw', new TextEncoder().encode(DINGTALK_SECRET),
        { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
      );
      const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(stringToSign));
      const sign = btoa(String.fromCharCode(...new Uint8Array(sig)));
      const url = DINGTALK_WEBHOOK + '&timestamp=' + timestamp + '&sign=' + encodeURIComponent(sign);

      // 转发到钉钉
      const body = await request.text();
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body
      });

      const result = await response.text();
      return new Response(result, {
        status: response.status,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Content-Type': 'application/json'
        }
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 500,
        headers: { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' }
      });
    }
  }
};
