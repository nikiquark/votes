import smtplib
from django.conf import settings

def send_to_user(to, name, title, url):
    body = f"""\
Добрый день, {name}!<br/>
<br/>
Вы участвуете в опросе '{title}'. <br/>
Пожалуйста, перейдите по ссылке <a target="_blank" href="{url}">{url}</a>, выберите варианты ответов и нажмите кнопку 'Отправить голос'."""
    send_email(to, title, body)



def send_email(to, title, text):
    
    if settings.DEBUG:
        print(to, title, text)
        return
    email = 'no-reply@inp.nsk.su'

    body = text

    # Set up the SMTP server
    server = smtplib.SMTP(settings.EMAIL_HOST)

    msg = f"""\
From: {email}
To: {to}
Subject: {title}
Content-Type: text/html; charset="UTF-8";

{body}
"""
    server.sendmail(email, to, msg.encode('utf-8'))
    server.quit()