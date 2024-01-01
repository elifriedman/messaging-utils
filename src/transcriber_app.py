import tempfile
import subprocess
import base64
import requests
import os
from pathlib import Path
from src import utils


def save_audio_in_tempdir(data):
    audio_bytes = base64.b64decode(data)
    tmpdir = Path("/tmp/audio/")
    tmpdir.mkdir(exist_ok=True)
    tmpfile = tempfile.mktemp(dir=tmpdir)
    with open(tmpfile, 'wb') as f:
        f.write(audio_bytes)
    return tmpfile

def run_whisper(audio_path):
    transcript = f"{audio_path}.json"
    args = ["insanely-fast-whisper",
            "--model-name", "distil-whisper/large-v2",
            "--device-id", "1",
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

class AudioTranscriberRoute:
    def is_applicable(self, message):
        return message.type == "media" and "message" in message.data["data"]["message"] and message.data["data"]["message"]["type"] in ["audio", "ptt"]

    async def process(self, message):
        data = message.get_media()
        audio_file = save_audio_in_tempdir(data)
        out = run_whisper(audio_file)
        out = f"TRANSCRIPTION: {out}"
        os.remove(audio_file)
        response = requests.post(f"http://localhost:3000/message/reply/test", headers=utils.make_headers(), data=message.make_reply(out))
        if not response.status_code == 200:
            print(f"ERROR: ({response.status_code}: {response.reason})")


