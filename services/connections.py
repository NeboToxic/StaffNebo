import requests
from core.telegram_proxy import build_proxy_url,requests_proxies
from core.secrets import redact,FIELDS

VK_ERRORS={5:'Неверный или просроченный VK Token',7:'У токена недостаточно прав',15:'Доступ запрещён',
           901:'Получатель не разрешил сообщения этому сообществу. Проверьте VK ID и разрешение в диалоге.',
           902:'Сообщения запрещены настройками приватности получателя',917:'Нет доступа к беседе'}


def provider_error(exc,settings):
    if isinstance(exc,requests.Timeout):return 'Превышено время ожидания. Проверьте интернет и прокси.'
    if isinstance(exc,requests.ConnectionError):return 'Нет соединения с API. Проверьте интернет и прокси.'
    return redact(exc,[getattr(settings,f) for f in FIELDS])


def check_connection(settings,cancel=lambda:False):
    try:
        if cancel():raise RuntimeError('Проверка отменена')
        if settings.platform=='telegram':
            if not settings.bot_id or not settings.chat_id:raise ValueError('Введите Bot Token и Chat ID')
            proxies=requests_proxies(build_proxy_url(settings.tg_proxy_type,settings.tg_proxy_host,settings.tg_proxy_port,settings.tg_proxy_username,settings.tg_proxy_password))
            url='https://api.telegram.org/bot'+settings.bot_id+'/'
            response=requests.get(url+'getMe',timeout=(5,15),proxies=proxies)
            data=response.json()
            if not data.get('ok'):raise RuntimeError('Неверный Bot Token' if data.get('error_code')==401 else data.get('description','Ошибка Telegram'))
            response.raise_for_status()
            if cancel():raise RuntimeError('Проверка отменена')
            chat=requests.get(url+'getChat',params={'chat_id':settings.chat_id},timeout=(5,15),proxies=proxies)
            payload=chat.json()
            if not payload.get('ok'):raise RuntimeError('Чат недоступен: '+str(payload.get('description','Проверьте Chat ID и права бота')))
            chat.raise_for_status()
            return True,'Telegram доступен. Токен и чат проверены. Прокси: '+settings.tg_proxy_type
        if not settings.vk_token or not settings.vk_user_id:raise ValueError('Введите VK Token и VK ID получателя')
        response=requests.post('https://api.vk.com/method/photos.getMessagesUploadServer',data={
            'peer_id':settings.vk_user_id,'access_token':settings.vk_token,'v':'5.199'},timeout=(5,15))
        data=response.json();error=data.get('error')
        if error:raise RuntimeError('VK '+str(error.get('error_code'))+': '+VK_ERRORS.get(error.get('error_code'),error.get('error_msg','Ошибка API')))
        response.raise_for_status()
        if not data.get('response',{}).get('upload_url'):raise RuntimeError('VK вернул неполный ответ')
        return True,'VK доступен. Проверены токен, получатель и доступ к загрузке фото. Сообщение не отправлялось.'
    except Exception as exc:return False,provider_error(exc,settings)
