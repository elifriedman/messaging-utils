import os
import requests
from datetime import datetime
from pathlib import Path
from eli_utils import load_json, save_json
from src import utils
from gpt import Context, Role

group_save_path = Path("conversations")
group_save_path.mkdir(exist_ok=True)

DEFAULT_SETTINGS = dict(
            model="gpt-4",
            temperature=0.5,
            max_tokens=2000,
            frequency_penalty=0,
            presence_penalty=0.6,
            seed=None,
            max_contexts=100,
            api_key=os.getenv("OPENAI_API_KEY")
        )

class GroupCreator:
    def is_applicable(self, message):
        new_group = message.type == "group_join" 
        new_group_in_community = message.type == "group_update" and message.message_info["type"] == "create"
        return new_group or new_group_in_community

    async def process(self, message):
        group_id = message.message_info["id"]["remote"]
        path = group_save_path / group_id
        save_json({"group_name": None, "group_description": None, "conversation": [], "settings": DEFAULT_SETTINGS}, path)


class GroupHandler:
    NAME = "assistant"
    SETTINGS = "/settings"
    HELP = "/help"

    def __init__(self, group_id):
        self.group_id = group_id
        self.path = group_save_path / self.group_id
        data = load_json(self.path)
        self.settings = data.get("settings", DEFAULT_SETTINGS)

    def is_applicable(self, message):
        group_id = message.message_info["id"]["remote"]
        is_current_group = self.group_id == group_id
        return is_current_group

    def update_group_info(self):
        input_data = {"chatId": self.group_id}
        response = requests.post(
            f"http://localhost:3000/groupChat/getClassInfo/test", headers=utils.make_headers(), data=input_data
        )
        if response.status_code != 200:
            print(f"ERROR: ({response.status_code}: {response.reason})")
        out = response.json()
        if out["success"] is not True:
            print(f"ERROR: {input_data=} {out=}")
        data = load_json(self.path)
        metadata = out["chat"]["groupMetadata"]
        data["group_name"] = metadata["subject"]
        data["group_description"] = metadata["desc"] if "desc" in metadata else None
        save_json(data, self.path, pretty=True)
        return data

    def is_config_message(self, body):
        configs = [self.SETTINGS, self.HELP]
        for config in configs:
            if config in body.lower():
                return True
        return False

    def handle_config_message(self, body, data):
        format_keys = lambda k, v: f"{k}={v}" if k != "api_key" else f"{k}={v[:3]}..{v[-3:]}"
        if self.HELP in body.lower():
            response_message = f"/settings\n" + "\n".join(sorted([format_keys(k, v) for k, v in self.settings.items()]))
        elif self.SETTINGS in body.lower():
            response_message = self.process_settings(body, data)
        else:
            return
        self.send_message(response_message)

    async def process(self, message):
        data = self.update_group_info()
        if message.type != "message":
            return
        body = message.get_text()
        author = message.sender
        timestamp = message.data["received_time"]
        if self.is_config_message(body):
            self.handle_config_message(body, data)
        else:
            data["conversation"].append({"author": author, "body": body, "timestamp": timestamp})
            self.process_conversation(data)
        save_json(data, self.path, pretty=True)

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.group_id == other.group_id

    def process_settings(self, message, data):
        settings = message.split("\n")
        changed_keys = []
        for row in settings:
            if "=" not in row:
                continue
            k, v = row.strip().split("=")
            if k in self.settings:
                current_v = self.settings[k]
                current_type = type(current_v)
                typed_v = current_type(v)
                value_changed = typed_v != current_v 
                if value_changed:
                    changed_keys.append(k)
                self.settings[k] = typed_v
        data["settings"] = self.settings
        return "Updated settings: " + ", ".join(changed_keys)

    def process_conversation(self, data):
        instructions = data["group_description"] or ""
        conversation = data["conversation"]
        last_message = conversation[-1]["body"]
        context = Context(instructions=instructions, max_contexts=100)
        for turn in conversation:
            if turn["author"] == self.NAME:
                context.add(content=turn["body"], role=Role.ASSISTANT)
            else:
                context.add(content=turn["body"], role=Role.USER)
        response_message = context.get_response(**self.settings)
        conversation.append({"author": self.NAME, "body": response_message, "timestamp": str(datetime.now())})
        self.send_message(message=response_message)

    def send_message(self, message):
        input_data = {"chatId": self.group_id, "contentType": "string", "content": message}
        response = requests.post(
            f"http://localhost:3000/client/sendMessage/test", headers=utils.make_headers(), data=input_data
        )
        if response.status_code != 200:
            print(f"ERROR: ({response.status_code}: {response.reason})")
        out = response.json()
        if out["success"] is not True:
            print(f"ERROR: {input_data=} {out=}")
