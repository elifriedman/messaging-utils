import tempfile
import subprocess
import base64
import requests
import json
import os
from quart import Quart, request, jsonify, send_file, render_template, send_from_directory, make_response


def load_json(f):
    with open(f) as f:
        return json.load(f)

def save_json(obj, f, pretty: bool=False):
    with open(f, 'w') as f:
        json.dump(obj, f, indent=4 if pretty is True else None)

def load_txt(f):
    with open(f) as f:
        return f.read().strip()

app = Quart(__name__)

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

class Media:
    def __init__(self, data):
        self.data = data

class Message:
    def __init__(self, data):
        self.data = data

    @property
    def message_info(self):
        return self.data["data"]["message"]

    @property
    def sender(self):
        if "author" in self.message_info:
            return self.message_info["author"]
        return self.message_info["from"]

    @property
    def chat_id(self):
        return self.message_info["from"]

    @property
    def message_id(self):
        return self.message_info["id"]["id"]

    @property
    def type(self):
        return self.data["dataType"]

    def get_media(self):
        data = self.data["data"]
        if "messageMedia" not in data:
            raise ValueError("No media")
        return data["messageMedia"]["data"]

    def make_reply(self, content):
        data = {
                "content": content,
                "chatId": self.chat_id,
                "messageId": self.message_id
                }
        return data

def save_audio_in_tempdir(data):
    audio_bytes = base64.b64decode(data)
    tmpfile = tempfile.mktemp(dir="/tmp/audio/")
    with open(tmpfile, 'wb') as f:
        f.write(audio_bytes)
    return tmpfile

def run_whisper(audio_path):
    transcript = f"{audio_path}.json"
    args = ["insanely-fast-whisper",
            "--model-name", "distil-whisper/large-v2",
            "--file-name", audio_path, "--transcript-path", transcript]
    try:
        out = subprocess.run(args, capture_output=True)
        code = out.returncode
        if code != 0:
            return f"ERROR: {out.stderr.decode()}"
        output = load_json(transcript)
        os.remove(transcript)
        return output["text"]
    except Exception as exc:
        return f"ERROR: {exc}"
    return "ERROR: could not transcribe"

async def process_audio(message):
    data = message.get_media()
    audio_file = save_audio_in_tempdir(data)
    out = run_whisper(audio_file)
    out = f"TRANSCRIPTION: {out}"
    os.remove(audio_file)
    headers = {"x-api-key": load_txt("api_key.cfg")}
    response = requests.post("http://localhost:3000/message/reply/test", headers=headers, data=message.make_reply(out))
    if not response.status_code == 200:
        print(f"ERROR: ({response.status_code}: {response.reason})")

@app.route('/callback', methods=["GET", "POST"])
async def callback():
    message = Message(await request.get_json())
    if message.type == "media" and message.message_info["type"] == "audio":
        app.add_background_task(process_audio, message=message)
    return {}

if __name__ == '__main__':
    app.run(debug=True)

# git clone https://github.com/chrishubert/whatsapp-api.git
# change BASE_WEBHOOK_URL in docker-compose.yml to point to your Quart script
# run docker-compose-up
# pip install -r requirements
# run the quart server
