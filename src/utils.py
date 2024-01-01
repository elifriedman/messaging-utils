from eli_utils import load_txt

def make_headers():
    headers = {"x-api-key": load_txt("api_key.cfg").strip()}
    return headers
