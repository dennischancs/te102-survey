// Vercel Serverless Function: 钉钉 webhook 代理
// 文件位置: api/dingtalk.js → 部署后 URL: https://<项目名>.vercel.app/api/dingtalk
const crypto = require('crypto');

// ── 配置（部署后在 Vercel 环境变量中设置）──
const WEBHOOK_URL = process.env.DINGTALK_WEBHOOK || 'https://oapi.dingtalk.com/robot/send?access_token=7e2120d25d16e13ddd2a214618764b9417a217752f960cd7835a5a1c68b28b84';
const SECRET = process.env.DINGTALK_SECRET || 'SECf03bbadc47bd7bdc8102169e9767336b877efee79be6fc29c5a7449a4e14d77e';

function signUrl(url, secret) {
  const timestamp = Date.now();
  const stringToSign = timestamp + '\n' + secret;
  const hmac = crypto.createHmac('sha256', secret).update(stringToSign).digest('base64');
  const sign = encodeURIComponent(hmac);
  return `${url}&timestamp=${timestamp}&sign=${sign}`;
}

module.exports = async (req, res) => {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const body = req.body;
    const finalUrl = signUrl(WEBHOOK_URL, SECRET);

    const resp = await fetch(finalUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    const result = await resp.json();
    return res.status(200).json({ ok: true, dingtalk: result });
  } catch (err) {
    return res.status(500).json({ ok: false, error: err.message });
  }
};
