import requests
from datetime import datetime
from pathlib import Path
from eli_utils import load_json, save_json
from src import utils
from gpt import Context, Role

group_save_path = Path("conversations")
group_save_path.mkdir(exist_ok=True)

class GroupCreator:
    def is_applicable(self, message):
        new_group = message.type == "group_join"
        return new_group

    async def process(self, message):
        group_id = message.message_info["id"]["remote"]
        path = group_save_path / group_id
        save_json({"group_name": None, "group_description": None, "conversation": []}, path)

class GroupHandler:
    NAME = "assistant"

    def __init__(self, group_id):
        self.group_id = group_id
        self.path = group_save_path / self.group_id

    def is_applicable(self, message):
        group_id = message.message_info["id"]["remote"]
        is_current_group = self.group_id == group_id
        return is_current_group

    def update_group_info(self):
        input_data = {"chatId": self.group_id}
        response = requests.post(f"http://localhost:3000/groupChat/getClassInfo/test", headers=utils.make_headers(), data=input_data)
        if response.status_code != 200:
            print(f"ERROR: ({response.status_code}: {response.reason})")
        out = response.json()
        if out["success"] is not True:
            print(f"ERROR: {input_data=} {out=}")
        data = load_json(self.path)
        metadata = out["chat"]["groupMetadata"]
        data["group_name"] = metadata["subject"]
        data["group_description"] = metadata["desc"] if 'desc' in metadata else None
        save_json(data, self.path, pretty=True)
        return data

    async def process(self, message):
        data = self.update_group_info()
        if message.type != "message":
            return
        body = message.get_text()
        author = message.sender
        timestamp = message.data["received_time"]
        data["conversation"].append({"author": author, "body": body, "timestamp": timestamp})
        self.process_conversation(data)
        save_json(data, self.path, pretty=True)

    def __eq__(self, other):
        return isinstance(other, type(self)) and self.group_id == other.group_id

    def process_conversation(self, data):
        instructions = data["group_description"] or ""
        conversation = data["conversation"]
        context = Context(instructions=instructions, max_contexts=100)
        for turn in conversation:
            if turn["author"] == self.NAME:
                context.add(content=turn["body"], role=Role.ASSISTANT)
            else:
                context.add(content=turn["body"], role=Role.USER)
        out = context.get_response(model="gpt-4", max_tokens=3000)
        conversation.append({"author": self.NAME, "body": out, "timestamp": str(datetime.now())})
        input_data = {
                "chatId": self.group_id,
                "contentType": "string",
                "content": out
            }
        response = requests.post(f"http://localhost:3000/client/sendMessage/test", headers=utils.make_headers(), data=input_data)
        if response.status_code != 200:
            print(f"ERROR: ({response.status_code}: {response.reason})")
        out = response.json()
        if out["success"] is not True:
            print(f"ERROR: {input_data=} {out=}")

