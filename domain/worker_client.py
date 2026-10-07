"""Direct provider clients for VK/Telegram-compatible notifications."""
import os
import random
import uuid
from io import BytesIO

import requests
from PIL import Image


VK_API = "https://api.vk.com/method/"
VK_VERSION = "5.199"


def _vk_call(session, method, data, timeout=(5, 15)):
    response = session.post(VK_API + method, data=data, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(str(payload["error"]))
    if "response" not in payload:
        raise RuntimeError(f"VK API: неожиданный ответ {payload}")
    return payload["response"]


def _prepare_photo(photo_path: str):
    """Prepare a compact JPEG in memory to make VK uploads much faster."""
    try:
        with Image.open(photo_path) as image:
            image = image.convert("RGB")
            max_width = 1920
            if image.width > max_width:
                height = round(image.height * max_width / image.width)
                image = image.resize((max_width, height), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=84, optimize=True)
            buffer.seek(0)
            return buffer
    except Exception:
        return None


def send_vk_message(token: str, peer_id: str, text: str, photo_path: str = None, random_id=None):
    if not token:
        raise RuntimeError("Не указан VK token")
    if not peer_id:
        raise RuntimeError("Не указан VK ID")

    session = requests.Session()
    rid = random_id if random_id is not None else random.randint(-2**31, 2**31 - 1)
    attachment = ""

    try:
        if photo_path:
            upload_server = _vk_call(
                session,
                "photos.getMessagesUploadServer",
                {"peer_id": peer_id, "access_token": token, "v": VK_VERSION},
                timeout=(5, 12),
            )
            upload_url = upload_server.get("upload_url")
            if not upload_url:
                raise RuntimeError(f"VK upload server не вернул upload_url: {upload_server}")

            image_buffer = _prepare_photo(photo_path)
            if image_buffer is not None:
                file_tuple = (f"nebo_{uuid.uuid4().hex}.jpg", image_buffer, "image/jpeg")
                uploaded_response = session.post(
                    upload_url,
                    files={"photo": file_tuple},
                    timeout=(5, 25),
                )
            else:
                with open(photo_path, "rb") as f:
                    uploaded_response = session.post(
                        upload_url,
                        files={"photo": (os.path.basename(photo_path), f, "image/png")},
                        timeout=(5, 25),
                    )

            uploaded_response.raise_for_status()
            uploaded = uploaded_response.json()
            if not uploaded.get("photo") or uploaded.get("server") is None or not uploaded.get("hash"):
                raise RuntimeError(f"VK загрузка фото вернула неполные данные: {uploaded}")

            saved = _vk_call(
                session,
                "photos.saveMessagesPhoto",
                {
                    "photo": uploaded["photo"],
                    "server": uploaded["server"],
                    "hash": uploaded["hash"],
                    "access_token": token,
                    "v": VK_VERSION,
                },
                timeout=(5, 12),
            )
            if not saved or not saved[0].get("id") or saved[0].get("owner_id") is None:
                raise RuntimeError(f"VK не сохранил фото: {saved}")

            photo = saved[0]
            attachment = f"photo{photo['owner_id']}_{photo['id']}"

        result = _vk_call(
            session,
            "messages.send",
            {
                "peer_id": peer_id,
                "random_id": rid,
                "message": text,
                "attachment": attachment,
                "access_token": token,
                "v": VK_VERSION,
            },
            timeout=(5, 15),
        )
        return result
    finally:
        session.close()
