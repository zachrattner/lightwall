import os
import json
from urllib import request as urlrequest, error as urlerror
from logger import warning
import re

def query_ollama(messages: list):
    host = os.environ.get("OLLAMA_HOST", "localhost")
    port = os.environ.get("OLLAMA_PORT", "11434")
    model = os.environ.get("BASE_MODEL", "gemma3:12b")
    num_ctx = int(os.environ.get("NUM_CTX", "4096"))
    num_batch = int(os.environ.get("NUM_BATCH", "512"))
    temperature = float(os.environ.get("TEMPERATURE", "0.6"))
    top_p = float(os.environ.get("TOP_P", "0.9"))

    url = f"http://{host}:{port}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": "24h",
        "options": {
            "num_ctx": num_ctx,
            "num_batch": num_batch,
            "temperature": temperature,
            "top_p": top_p
        }
    }
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers={"Content-Type": "application/json"})
    reply_text = ""
    try:
        with urlrequest.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            j = json.loads(body)
            if isinstance(j, dict):
                if "message" in j and isinstance(j["message"], dict):
                    reply_text = j["message"].get("content", "") or ""
    except urlerror.URLError as e:
        warning(f"Ollama request failed: {e}")
        return
    except Exception as e:
        warning(f"Ollama parsing error: {e}")
        return
    if reply_text:
        # Remove emojis from the reply text
        emoji_pattern = re.compile(
            "["
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map symbols
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+",
            flags=re.UNICODE
        )
        reply_text = emoji_pattern.sub(r'', reply_text)
        return reply_text