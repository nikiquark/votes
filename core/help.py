import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from django.conf import settings

def send_to_user(to, name, title, url):
    body = f"""\
Добрый день, {name}!<br/>
<br/>
Вы участвуете в опросе '{title}'. <br/>
Пожалуйста, перейдите по ссылке <a target="_blank" href="{url}">{url}</a>, выберите варианты ответов и нажмите кнопку 'Отправить голос'."""
    send_email(to, title, body)


def html_to_plain_text(html_text):
    """Конвертирует HTML текст в plain text"""
    # Заменяем <br/> на переносы строк
    text = re.sub(r'<br\s*/?>', '\n', html_text, flags=re.IGNORECASE)
    # Извлекаем текст из ссылок: <a href="url">text</a> -> text (url)
    text = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>([^<]*)</a>', r'\2 (\1)', text)
    # Удаляем все остальные HTML теги
    text = re.sub(r'<[^>]+>', '', text)
    # Декодируем HTML entities (базовые)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    # Убираем лишние пробелы и переносы
    text = re.sub(r'\n\s*\n', '\n\n', text)
    return text.strip()



def send_email(to, title, text):
    
    if settings.DEBUG:
        print(to, title, text)
        return
    email = 'no-reply@inp.nsk.su'
    reply_to = 'N.V.Okhotnikov@inp.nsk.su'
    unsubscribe = 'N.V.Okhotnikov@inp.nsk.su'

    # Создаем multipart сообщение
    msg = MIMEMultipart('alternative')
    msg['From'] = email
    msg['To'] = to
    msg['Subject'] = title
    msg['Reply-To'] = reply_to
    msg['List-Unsubscribe'] = f'<mailto:{unsubscribe}>'

    # Создаем plain text версию
    plain_text = html_to_plain_text(text)
    part1 = MIMEText(plain_text, 'plain', 'utf-8')
    
    # Создаем HTML версию
    part2 = MIMEText(text, 'html', 'utf-8')

    # Прикрепляем части к сообщению
    msg.attach(part1)
    msg.attach(part2)

    # Set up the SMTP server
    server = smtplib.SMTP(settings.EMAIL_HOST)
    server.sendmail(email, to, msg.as_string())
    server.quit()