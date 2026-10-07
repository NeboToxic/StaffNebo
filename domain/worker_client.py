"""Direct provider clients. No Cloudflare Worker or project-owned relay is required."""
import os
import random
import requests


def send_vk_message(token: str, peer_id: str, text: str, photo_path: str = None):
    if not token:
        raise RuntimeError("Не указан VK token")
    api = "https://api.vk.com/method/"
    version = "5.199"
    if photo_path:
        server = requests.post(api + "photos.getMessagesUploadServer", data={
            "peer_id": peer_id, "access_token": token, "v": version
        }, timeout=20).json()
        upload_url = server.get("response", {}).get("upload_url")
        if not upload_url:
            raise RuntimeError(f"VK upload server: {server}")
        with open(photo_path, "rb") as f:
            uploaded = requests.post(upload_url, files={"photo": (os.path.basename(photo_path), f, "image/png")}, timeout=60).json()
        saved = requests.post(api + "photos.saveMessagesPhoto", data={
            "photo": uploaded.get("photo"), "server": uploaded.get("server"),
            "hash": uploaded.get("hash"), "access_token": token, "v": version
        }, timeout=20).json()
        photo = (saved.get("response") or [{}])[0]
        attachment = f"photo{photo.get('owner_id')}_{photo.get('id')}"
    else:
        attachment = ""
    result = requests.post(api + "messages.send", data={
        "peer_id": peer_id, "random_id": random.randint(-2**31, 2**31 - 1),
        "message": text, "attachment": attachment, "access_token": token, "v": version
    }, timeout=30).json()
    if "error" in result:
        raise RuntimeError(str(result["error"]))
    return result
