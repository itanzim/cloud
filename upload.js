export const config = {
  api: {
    bodyParser: false,
  },
};

import busboy from "busboy";
import fetch from "node-fetch";
import { Readable } from "stream";

const BOT_TOKEN = "7940804849:AAFpqkamFGbj1hWMOZmrGXDSarJ0yi54DgQ";
const CHANNEL_ID = "-1002837205535"; // must be negative for channels

export default async function handler(req, res) {
  if (req.method !== "POST") return res.status(405).json({ error: "Only POST allowed" });

  const bb = busboy({ headers: req.headers });
  let fileBuffer = Buffer.alloc(0);
  let fileName = "upload";

  bb.on("file", (_, file, info) => {
    fileName = info.filename;
    file.on("data", (data) => {
      fileBuffer = Buffer.concat([fileBuffer, data]);
    });
  });

  bb.on("finish", async () => {
    try {
      const telegramURL = `https://api.telegram.org/bot${BOT_TOKEN}/sendDocument`;

      const formData = new FormData();
      formData.append("chat_id", CHANNEL_ID);
      formData.append("caption", fileName);
      formData.append("document", new Blob([fileBuffer]), fileName);

      const response = await fetch(telegramURL, {
        method: "POST",
        body: formData,
      });

      const result = await response.json();
      if (result.ok) {
        const fileId = result.result.document.file_id;
        res.status(200).json({ success: true, url: `https://t.me/c/${CHANNEL_ID.slice(4)}/${result.result.message_id}` });
      } else {
        res.status(500).json({ error: "Telegram error", details: result });
      }
    } catch (e) {
      res.status(500).json({ error: e.message });
    }
  });

  req.pipe(bb);
}