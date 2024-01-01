import tempfile
import subprocess
import base64
import json
import os
from datetime import datetime
from pathlib import Path
from quart import Quart, request, jsonify, send_file, render_template, send_from_directory, make_response
from src.transcriber_app import AudioTranscriberRoute
from src.chatbot import GroupHandler, GroupCreator, group_save_path
from eli_utils import load_json, save_json, load_txt


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
        data = {
                "content": content,
                "chatId": self.chat_id,
                "messageId": self.message_id
                }
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
            if route.is_applicable(message):
                app.add_background_task(route.process, message=message)
        return {}

if __name__ == '__main__':
    router = WhatsappRouter()
    app.route('/callback', methods=["GET", "POST"])(router.callback)
    router.add_route(AudioTranscriberRoute())
    router.add_route(GroupCreator())
    app.run(debug=True)

# git clone https://github.com/chrishubert/whatsapp-api.git
# change BASE_WEBHOOK_URL in docker-compose.yml to point to your Quart script
# run docker-compose-up
# pip install -r requirements
# run the quart server
