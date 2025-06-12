export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).send('Only POST allowed');

  const { fileUrl, fileName } = req.body;

  const BOT_TOKEN = process.env.BOT_TOKEN;
  const CHANNEL_ID = process.env.CHANNEL_ID;

  try {
    const fileRes = await fetch(fileUrl);
    const fileBuffer = await fileRes.arrayBuffer();

    const boundary = '----CloudUploaderBoundary' + Math.random().toString(16).slice(2);
    const parts = [];

    const push = (text) => parts.push(Buffer.from(text));
    push(`--${boundary}\r\n`);
    push(`Content-Disposition: form-data; name="chat_id"\r\n\r\n`);
    push(`${CHANNEL_ID}\r\n`);
    push(`--${boundary}\r\n`);
    push(`Content-Disposition: form-data; name="caption"\r\n\r\n`);
    push(`${fileName}\r\n`);
    push(`--${boundary}\r\n`);
    push(`Content-Disposition: form-data; name="document"; filename="${fileName}"\r\n`);
    push(`Content-Type: application/octet-stream\r\n\r\n`);
    parts.push(Buffer.from(fileBuffer));
    push(`\r\n--${boundary}--\r\n`);

    const tgRes = await fetch(`https://api.telegram.org/bot${BOT_TOKEN}/sendDocument`, {
      method: 'POST',
      headers: {
        'Content-Type': `multipart/form-data; boundary=${boundary}`,
      },
      body: Buffer.concat(parts),
    });

    const tgJson = await tgRes.json();
    res.status(200).json(tgJson);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
}