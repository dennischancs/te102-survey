// Netlify Function: 钉钉 webhook 代理（国内可达）
const crypto = require('crypto');

const WEBHOOK_URL = 'https://oapi.dingtalk.com/robot/send?access_token=7e2120d25d16e13ddd2a214618764b9417a217752f960cd7835a5a1c68b28b84';
const SECRET = 'SECf03bbadc47bd7bdc8102169e9767336b877efee79be6fc29c5a7449a4e14d77e';

function signUrl(url, secret) {
  const timestamp = Date.now();
  const stringToSign = timestamp + '\n' + secret;
  const hmac = crypto.createHmac('sha256', secret).update(stringToSign).digest('base64');
  const sign = encodeURIComponent(hmac);
  return `${url}&timestamp=${timestamp}&sign=${sign}`;
}

exports.handler = async (event) => {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers, body: '' };
  }

  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  try {
    const body = JSON.parse(event.body);
    const finalUrl = signUrl(WEBHOOK_URL, SECRET);

    const resp = await fetch(finalUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });

    const result = await resp.json();
    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ ok: true, dingtalk: result })
    };
  } catch (err) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ ok: false, error: err.message })
    };
  }
};
