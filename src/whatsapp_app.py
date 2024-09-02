import base64
import time
import requests
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from quart import Quart, request, jsonify, send_file, render_template, send_from_directory, make_response
from src.transcriber_app import AudioTranscriberRoute
from src.chatbot import GroupHandler, GroupCreator, group_save_path
from src.speedate_response import SpeedDateResponse
from src import utils
from eli_utils import load_json, save_json, load_txt, save_txt


app = Quart(__name__)


@app.route("/static/<path:filename>")
def serve_static(filename):
    print(f"{filename=}")
    return send_from_directory(app.static_folder, filename)


class Media:
    def __init__(self, data):
        self.data = data


class Message:
    def __init__(self, data):
        self.data = data

    @property
    def message_info(self):
        data = self.data["data"]
        if "message" in data:
            return data["message"]
        key = list(data.keys())[0]
        return data[key]

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

    def get_text(self):
        data = self.data["data"]
        if "message" not in data:
            raise ValueError("No message")
        return data["message"]["body"]

    def make_reply(self, content):
        data = {"content": content, "chatId": self.chat_id, "messageId": self.message_id}
        return data


class WhatsappRouter:
    def __init__(self):
        self.routes = []

    def add_route(self, route):
        self.routes.append(route)

    def update_routes(self):
        group_paths = sorted(group_save_path.glob("*"))
        for path in group_paths:
            group = GroupHandler(group_id=path.name)
            if group not in self.routes:
                self.routes.append(group)

    async def callback(self):
        data = await request.get_json()
        app.logger.info(f"Got message {str(data)[:100]}...")
        data["received_time"] = str(datetime.now())
        save_json(data, "last_message.json", pretty=True, append=True)
        message = Message(data)
        self.update_routes()
        for route in self.routes:
            try:
                is_applicable = route.is_applicable(message)
            except (KeyError, TypeError) as exc:
                formatted = traceback.format_exception(exc, limit=3)
                msg = formatted
                app.logger.error(f"ERROR {route}.is_applicable(): {''.join(msg)} {exc}")
                continue
            if is_applicable:
                app.add_background_task(route.process, message=message)
        return {}


class QRScanner:
    def __init__(self):
        self.running = False
        self.last_run = None

    def is_applicable(self, message):
        is_qr = message.type == "qr" and "qr" in message.data["data"]
        return is_qr

    async def process(self, message):
        already_checked = self.last_run is not None and datetime.now() - self.last_run < timedelta(seconds=60)
        if self.running is True or already_checked:
            return
        self.running = True
        self.last_run = datetime.now()
        response = requests.get(f"http://localhost:3000/session/status/test", headers=utils.make_headers())
        data = response.json()
        if data["success"] is True:
            return
        response = requests.get(f"http://localhost:3000/session/terminate/test", headers=utils.make_headers())
        response = requests.get(f"http://localhost:3000/session/start/test", headers=utils.make_headers())
        time.sleep(5)
        response = requests.get(f"http://localhost:3000/session/qr/test/image", headers=utils.make_headers())
        qr_image = base64.b64encode(response.content).decode()
        html = f"""<!DOCTYPE html>
<html>
<body>
    <h1>Session Reset: {str(datetime.now())}</h1>
    <img src="data:image/png;base64,{qr_image}" alt="QR Code" />
</body>
</html>
"""
        save_txt(html, "src/static/reset.html")
        self.running = False


if __name__ == "__main__":
    router = WhatsappRouter()
    app.route("/callback", methods=["GET", "POST"])(router.callback)
    # router.add_route(AudioTranscriberRoute())
    # router.add_route(GroupCreator())
    router.add_route(QRScanner())
    # router.add_route(SpeedDateResponse())
    app.run(debug=True, port=5093, host="0.0.0.0")

# git clone https://github.com/chrishubert/whatsapp-api.git
# change BASE_WEBHOOK_URL in docker-compose.yml to point to your Quart script
# run docker-compose-up
# pip install -r requirements
# run the quart server
